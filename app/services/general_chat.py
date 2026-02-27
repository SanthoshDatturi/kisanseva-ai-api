import asyncio

from fastapi import HTTPException, status
from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

from app.collections.chat_session import (
    get_messages_from_chat_session_id,
    save_message,
)
from app.core.genai_client import get_chat_model
from app.core.langchain_message_adapter import (
    coerce_message_content,
    message_content_to_langchain_message,
    message_content_with_audio,
)
from app.models.chat_session import (
    GeneralChatModelResponse,
    GeneralChatResponse,
    Message,
    MessageContent,
    MessagePart,
    Role,
)
from app.prompts.general_chat_system_prompt import GENERAL_CHAT_SYSTEM_PROMPT
from app.services.files import (
    convert_file_uri,
    text_to_speech_url,
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
        system_prompt=GENERAL_CHAT_SYSTEM_PROMPT,
        language=language,
    )


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


async def general_chat_service(
    user_id: str,
    language: str,
    content: MessageContent,
    chat_id: str,
    audio_response: bool = False,
) -> GeneralChatResponse:
    structured_model = get_chat_model(model="gemini-2.5-flash").with_structured_output(
        GeneralChatModelResponse,
        method="json_schema",
    )

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

        model_response_data: GeneralChatModelResponse = await structured_model.ainvoke(
            _build_system_messages(language) + chat_history + [user_message_for_model]
        )

        original_user_content = coerce_message_content(content, default_role=Role.USER)
        if not any(part.text is not None for part in original_user_content.parts):
            original_user_content.parts.append(
                MessagePart(text=model_response_data.user_query or "")
            )

        user_message = await save_message(
            message=Message(content=original_user_content, chat_id=chat_id)
        )

        audio_url = None
        if audio_response:
            audio_url = await text_to_speech_url(
                text_or_data=model_response_data.message_to_user,
                blob_name=user_message.id,
                path_prefix=f"{user_id}/{chat_id}",
                language=language,
            )

        model_message = await save_message(
            Message(
                content=message_content_with_audio(
                    text=model_response_data.message_to_user,
                    audio_url=audio_url,
                    role=Role.MODEL,
                ),
                chat_id=chat_id,
            )
        )

        return GeneralChatResponse(
            command=model_response_data.command,
            user_message=user_message,
            model_message=model_message,
        )
    except (ValidationError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Received an invalid response from the AI service.",
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
            detail="An internal error occurred. Please try again.",
        )
