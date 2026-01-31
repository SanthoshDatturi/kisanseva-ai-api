import asyncio

from fastapi import HTTPException, status
from google.genai import Client, types
from google.genai.errors import ClientError
from google.genai.types import Content, Part
from pydantic import (
    ValidationError,
)  # Import ValidationError for specific error handling

from app.collections.chat_session import (
    get_messages_from_chat_session_id,
    save_chat_session,
    save_message,
)
from app.core.genai_client import get_client
from app.models.chat_session import (
    ChatSession,
    ChatType,
    GeneralChatModelResponse,
    GeneralChatResponse,
    Message,
    Role,
)
from app.prompts.general_chat_system_prompt import GENERAL_CHAT_SYSTEM_PROMPT
from app.services.files import convert_file_uri, text_to_speech_url


async def general_chat_service(
    user_id: str,
    language: str,
    content: Content,
    chat_id: str,
    audio_response: bool = False,
) -> GeneralChatResponse:
    client: Client = get_client()
    try:
        if chat_id.startswith("temp-"):
            # This is the first message of a new chat.
            chat_session = ChatSession(chat_type=ChatType.GENERAL, user_id=user_id)

            # The first message from the user is a greeting or initial query.
            # We'll save it and then generate the model's first response.
            chat_session = await save_chat_session(chat=chat_session)
            # The client sends a temporary ID. We create a permanent one and send
            # a combined ID back so the client can map it.
            new_chat_id = chat_id + "-perm-" + chat_session.id

            converted_parts = []
            for part in content.parts:
                if part.file_data:
                    uri, mime = await convert_file_uri(part.file_data.file_uri)
                    converted_parts.append(Part.from_uri(file_uri=uri, mime_type=mime))
                else:
                    converted_parts.append(part)

            converted_content = Content(role=Role.USER, parts=converted_parts)

            # Now, let the model respond to the user's first message.
            # This is slightly different from farm_survey, which starts with a greeting.
            # Here, we respond to the user's initiation.
            config = types.GenerateContentConfig(
                system_instruction=GENERAL_CHAT_SYSTEM_PROMPT
                + f"\n\nUser specified language: {language}",
                response_schema=GeneralChatModelResponse,
                response_mime_type="application/json",
            )

            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=converted_content,
                config=config,
            )

            try:
                model_response_data: GeneralChatModelResponse = GeneralChatModelResponse.model_validate_json(
                    response.text
                )
            except (ValidationError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Received an invalid response from the AI service.",
                )
            
            user_message = Message(content=content, chat_id=chat_session.id)

            is_text_exist = False

            for part in user_message.content.parts:
                if part.text is not None:
                    is_text_exist = True
                    break

            if not is_text_exist:
                user_message.content.parts.append(Part(text=model_response_data.user_query or ""))

            user_message = await save_message(message=user_message)

            model_parts = [Part(text=model_response_data.message_to_user)]
            if audio_response:
                audio_url = await text_to_speech_url(
                    text_or_data=model_response_data.message_to_user,
                    blob_name=chat_session.id,
                    language=language,
                )
                model_parts.append(
                    Part(
                        file_data=types.FileData(
                            file_uri=audio_url, mime_type="audio/wav"
                        )
                    )
                )

            model_message = Message(
                content=Content(role=Role.MODEL, parts=model_parts),
                chat_id=chat_session.id,
            )
            model_message = await save_message(model_message)
            model_message.chat_id = new_chat_id  # Use the mapped ID for the response

            return GeneralChatResponse(
                command=model_response_data.command,
                model_message=model_message,
                user_message=user_message,
            )

        # This is an existing chat.
        messages = await get_messages_from_chat_session_id(chat_id=chat_id)
        if not messages:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No messages in this chat session.",
            )

        # Concurrently process file URIs from historical messages
        conversion_tasks = [
            convert_file_uri(part.file_data.file_uri)
            for message in messages
            for part in message.content.parts
            if part.file_data and part.file_data.file_uri
        ]
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
            system_instruction=GENERAL_CHAT_SYSTEM_PROMPT
            + f"\n\nUser specified language: {language}",
            response_schema=GeneralChatModelResponse,
            response_mime_type="application/json",
        )

        # Process current user message parts for the GenAI call
        genai_parts = []
        has_text = any(p.text is not None for p in content.parts)
        for part in content.parts:
            if part.file_data:
                if not (has_text and part.file_data.mime_type.startswith("audio/")):
                    uri, mime = await convert_file_uri(part.file_data.file_uri)
                    genai_parts.append(Part.from_uri(file_uri=uri, mime_type=mime))
            elif part.text is not None:
                genai_parts.append(part)

        user_content_for_genai = Content(role=Role.USER, parts=genai_parts)
        contents = chat_history + [user_content_for_genai]

        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash", contents=contents, config=config
        )

        model_response_data: GeneralChatModelResponse = GeneralChatModelResponse.model_validate_json(
            response.text
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
            user_message.content.parts.append(Part(text=model_response_data.user_query or ""))

        user_message = await save_message(message=user_message)

        model_parts = [Part(text=model_response_data.message_to_user)]
        if audio_response:
            audio_url = await text_to_speech_url(
                text_or_data=model_response_data.message_to_user,
                blob_name=user_message.id,
                language=language,
            )
            model_parts.append(
                Part(
                    file_data=types.FileData(file_uri=audio_url, mime_type="audio/wav")
                )
            )

        model_message = await save_message(
            Message(
                content=Content(role=Role.MODEL, parts=model_parts), chat_id=chat_id
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
    except ClientError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"GenAI Client Error: {e.message}",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred. Please try again.",
        )
