from fastapi import HTTPException, status
from pydantic import ValidationError

from app.core.genai_client import get_chat_model
from app.models.chat_session import (
    GeneralChatModelResponse,
    GeneralChatResponse,
    MessageContent,
)
from app.prompts.general_chat_system_prompt import GENERAL_CHAT_SYSTEM_PROMPT
from app.services.chat import (
    prepare_model_input_messages,
    save_model_response_message,
    save_user_message_with_fallback,
)

async def general_chat_service(
    user_id: str,
    language: str,
    content: MessageContent,
    chat_id: str,
    request_id: str,
    audio_response: bool = False,
) -> GeneralChatResponse:
    structured_model = get_chat_model(model="gemini-2.5-flash").with_structured_output(
        GeneralChatModelResponse,
        method="json_schema",
    )

    try:
        model_input_messages = await prepare_model_input_messages(
            chat_id=chat_id,
            content=content,
            system_prompt=GENERAL_CHAT_SYSTEM_PROMPT,
            language=language,
        )

        model_response_data: GeneralChatModelResponse = await structured_model.ainvoke(
            model_input_messages
        )

        user_message = await save_user_message_with_fallback(
            chat_id=chat_id,
            content=content,
            request_id=request_id,
            fallback_text=model_response_data.user_query or "",
        )

        model_message = await save_model_response_message(
            chat_id=chat_id,
            text=model_response_data.message_to_user,
            request_id=request_id,
            language=language,
            audio_response=audio_response,
            blob_name=user_message.id,
            path_prefix=f"{user_id}/{chat_id}",
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
