import asyncio

from fastapi import HTTPException, status
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

from app.collections.chat_session import (
    get_messages_from_chat_session_id,
    save_message,
)
from app.collections.farm_profile import save_farm_profile
from app.core.genai_client import get_chat_model
from app.core.langchain_message_adapter import (
    coerce_message_content,
    message_content_to_langchain_message,
    message_content_with_audio,
)
from app.models.chat_session import (
    Command,
    Message,
    MessageContent,
    MessagePart,
    Role,
)
from app.models.farm_survey_agent_response import (
    FarmSurveyAgentMappedResponse,
    FarmSurveyAgentResponse,
)
from app.prompts.farm_survey_agent_system_prompt import (
    FARM_SURVEY_AGENT_SYSTEM_PROMPT,
)

from .files import convert_file_uri, text_to_speech_url


def _extract_ai_text(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content

    if isinstance(message.content, list):
        text_values = []
        for block in message.content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_values.append(block.get("text") or "")
        return "\n".join([text for text in text_values if text]).strip()

    return ""


async def _convert_content_for_model(
    content: MessageContent, skip_audio_when_text_exists: bool = False
) -> MessageContent:
    normalized = coerce_message_content(content, default_role=Role.USER)
    has_text = any(part.text is not None for part in normalized.parts)

    converted_parts: list[MessagePart] = []
    conversion_tasks = []
    task_indexes: list[int] = []

    for part in normalized.parts:
        if part.file_data:
            if (
                skip_audio_when_text_exists
                and has_text
                and part.file_data.mime_type.startswith("audio/")
            ):
                continue

            task_indexes.append(len(converted_parts))
            conversion_tasks.append(convert_file_uri(part.file_data.file_uri))
            converted_parts.append(MessagePart())
        elif part.text is not None:
            converted_parts.append(MessagePart(text=part.text))

    if conversion_tasks:
        converted_results = await asyncio.gather(*conversion_tasks)
        for idx, (uri, mime) in zip(task_indexes, converted_results):
            converted_parts[idx] = MessagePart.model_validate(
                {"file_data": {"file_uri": uri, "mime_type": mime}}
            )

    return MessageContent(role=normalized.role, parts=converted_parts)


async def _generate_model_response_content(
    message_text: str,
    language: str,
    audio_response: bool,
    blob_name_prefix: str,
    path_prefix: str | None = None,
) -> MessageContent:
    audio_url = None

    if audio_response:
        audio_url = await text_to_speech_url(
            text_or_data=message_text,
            blob_name=blob_name_prefix,
            path_prefix=path_prefix,
            language=language,
        )

    return message_content_with_audio(
        text=message_text,
        audio_url=audio_url,
        role=Role.MODEL,
    )


def _build_system_messages(language: str):
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "{system_prompt}\n\nUser specified language: {language}",
            )
        ]
    )
    return prompt.format_messages(
        system_prompt=FARM_SURVEY_AGENT_SYSTEM_PROMPT,
        language=language,
    )


async def farm_survey_agent(
    user_id: str,
    language: str,
    content: MessageContent,
    chat_id: str,
    audio_response: bool = False,
) -> FarmSurveyAgentMappedResponse:
    try:
        messages = await get_messages_from_chat_session_id(chat_id=chat_id)

        converted_history_contents = await asyncio.gather(
            *[
                _convert_content_for_model(m.content, skip_audio_when_text_exists=True)
                for m in messages
            ]
        )
        chat_history = [
            message_content_to_langchain_message(
                converted_content,
                fallback_role=converted_content.role or Role.USER,
            )
            for converted_content in converted_history_contents
        ]

        converted_current_content = await _convert_content_for_model(
            content=content,
            skip_audio_when_text_exists=True,
        )
        user_message_for_model = message_content_to_langchain_message(
            converted_current_content,
            fallback_role=Role.USER,
        )

        model = (
            get_chat_model(model="gemini-2.5-flash")
            .bind_tools([{"google_search": {}}, {"google_maps": {}}])
            .with_structured_output(FarmSurveyAgentResponse, method="json_schema")
        )

        response_message: FarmSurveyAgentResponse = await model.ainvoke(
            _build_system_messages(language) + chat_history + [user_message_for_model]
        )

        user_content = coerce_message_content(content, default_role=Role.USER)
        if not any(part.text is not None for part in user_content.parts):
            user_content.parts.append(
                MessagePart(text=response_message.user_query or "")
            )

        user_message = await save_message(
            message=Message(content=user_content, chat_id=chat_id)
        )

        if response_message.command == Command.EXIT and response_message.farm_profile:
            response_message.farm_profile.farmer_id = user_id
            await save_farm_profile(response_message.farm_profile)

        farm_assistant_content = await _generate_model_response_content(
            response_message.message_to_user,
            language,
            audio_response,
            user_message.id,
            path_prefix=f"{user_id}/{chat_id}",
        )

        model_message = await save_message(
            Message(content=farm_assistant_content, chat_id=chat_id)
        )

        mapped_response: FarmSurveyAgentMappedResponse = FarmSurveyAgentMappedResponse(
            command=response_message.command,
            farm_profile=response_message.user_language_farm_profile,
            user_message=user_message,
            model_message=model_message,
        )

        return mapped_response

    except (ValidationError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error validating data. Please try again later.",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e).lower()
        if "error calling model" in error_message or "api" in error_message:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"GenAI service error: {str(e)}",
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error. Please try again later.",
        )
