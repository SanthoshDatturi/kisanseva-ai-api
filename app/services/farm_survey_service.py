import asyncio

from fastapi import HTTPException, status
from google.genai import Client, types
from google.genai.errors import ClientError
from google.genai.types import Content, Part
from pydantic import (
    ValidationError,
)

from app.collections.chat_session import (
    get_messages_from_chat_session_id,
    save_chat_session,
    save_message,
)
from app.collections.farm_profile import save_farm_profile
from app.core.genai_client import get_client
from app.models.chat_session import ChatSession, ChatType, Command, Message, Role
from app.models.farm_survey_agent_response import (
    FarmSurveyAgentMappedResponse,
    FarmSurveyAgentResponse,
)
from app.prompts.farm_survey_agent_system_prompt import (
    FARM_SURVEY_AGENT_SYSTEM_PROMPT,
    GREETING_SYSTEM_PROMPT,
)

from .files import convert_file_uri, text_to_speech_url


async def _generate_model_response_content(
    message_text: str,
    language: str,
    audio_response: bool,
    blob_name_prefix: str,
) -> Content:
    """
    Generates content for the model's response, including optional audio.
    """
    model_parts = [Part(text=message_text)]

    if audio_response:
        audio_url = await text_to_speech_url(
            text_or_data=message_text,
            blob_name=blob_name_prefix,
            language=language,
        )
        model_parts.append(
            Part(
                file_data=types.FileData(
                    file_uri=audio_url,
                    mime_type="audio/wav",
                )
            )
        )

    return Content(role=Role.MODEL, parts=model_parts)


async def farm_survey_agent(
    user_id: str,
    language: str,
    content: Content,
    chat_id: str,
    audio_response: bool = False,
) -> FarmSurveyAgentMappedResponse:
    client: Client = get_client()
    try:
        if chat_id.startswith("temp-"):
            chat_session = ChatSession(chat_type=ChatType.FARM_SURVEY, user_id=user_id)

            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=language,
                config=types.GenerateContentConfig(
                    system_instruction=GREETING_SYSTEM_PROMPT,
                    safety_settings=[
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                            threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                        )
                    ],
                ),
            )

            chat_session = await save_chat_session(chat=chat_session)
            # The client sends a temporary ID. We create a permanent one and send
            # a combined ID back so the client can map it.
            chat_id = chat_id + "-perm-" + chat_session.id

            model_content = await _generate_model_response_content(
                response.text, language, audio_response, chat_session.id
            )
            model_message = Message(
                content=model_content,
                chat_id=chat_session.id,
            )
            model_message = await save_message(model_message)
            model_message.chat_id = chat_id

            return FarmSurveyAgentMappedResponse(
                command=Command.CONTINUE,
                model_message=model_message,
            )

        messages = await get_messages_from_chat_session_id(chat_id=chat_id)
        if not messages:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No messages in this chat session.",
            )

        # Concurrently process file URIs from historical messages
        conversion_tasks = []
        for message in messages:
            for part in message.content.parts:
                if part.file_data and part.file_data.file_uri:
                    conversion_tasks.append(convert_file_uri(part.file_data.file_uri))

        converted_files = await asyncio.gather(*conversion_tasks)

        chat_history = []
        converted_files_iter = iter(converted_files)
        for message in messages:
            for part in message.content.parts:
                if part.file_data and part.file_data.file_uri:
                    part.file_data.file_uri, part.file_data.mime_type = next(
                        converted_files_iter
                    )
            chat_history.append(message.content)

        config = types.GenerateContentConfig(
            system_instruction=FARM_SURVEY_AGENT_SYSTEM_PROMPT
            + f"\n\nUser specified language: {language}",
            response_schema=FarmSurveyAgentResponse,
            response_mime_type="application/json",
            safety_settings=[
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                )
            ],
        )

        # Process current user message parts for the GenAI call
        genai_parts = []
        has_text = any(p.text is not None for p in content.parts)

        for part in content.parts:
            if part.file_data:
                # Ignore audio if text is also present, as GenAI handles speech-to-text
                if not (has_text and part.file_data.mime_type.startswith("audio/")):
                    uri, mime = await convert_file_uri(part.file_data.file_uri)
                    genai_parts.append(Part.from_uri(file_uri=uri, mime_type=mime))
            elif part.text is not None:
                genai_parts.append(part)
            # else: part is empty, ignore

        user_content_for_genai = Content(role=Role.USER, parts=genai_parts)
        contents = chat_history + [user_content_for_genai]

        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config,  # type: ignore
        )

        try:
            response_message: FarmSurveyAgentResponse = FarmSurveyAgentResponse.model_validate_json(
                response.text
            )
        except (ValidationError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Received an invalid response from the AI service.",
            )

        user_message = Message(
            content=Content(role=Role.USER, parts=content.parts), chat_id=chat_id
        )
        
        is_text_exist = False

        for part in user_message.content.parts:
            if part.text is not None:
                is_text_exist = True
                break

        if not is_text_exist:
            user_message.content.parts.append(Part(text=response_message.user_query or ""))

        user_message = await save_message(message=user_message)

        if response_message.command == Command.EXIT and response_message.farm_profile:
            response_message.farm_profile.farmer_id = user_id
            await save_farm_profile(response_message.farm_profile)

        farm_assistant_content = await _generate_model_response_content(
            response_message.message_to_user,
            language,
            audio_response,
            user_message.id,  # Use user message ID for a unique blob name
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

    except ValidationError as e:
        # Log the validation error for debugging
        print(f"Pydantic ValidationError in farm_survey_agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error validating data. Please try again later.",
        )
    except ClientError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"GenAI Client Error: {e.message}",
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"An unexpected error occurred in farm_survey_agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error. Please try again later.",
        )
