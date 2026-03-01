from typing import Optional

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.core.genai_client import get_chat_model
from app.models.ai_workflow import WorkflowType
from app.models.chat_session import (
    GeneralChatModelResponse,
    GeneralChatResponse,
    MessageContent,
)
from app.prompts.general_chat_system_prompt import GENERAL_CHAT_SYSTEM_PROMPT
from app.services.ai_workflow_runtime import (
    StreamEmitter,
    WorkflowRuntime,
    sanitize_http_error_message,
)
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
    *,
    stream_emitter: Optional[StreamEmitter] = None,
) -> GeneralChatResponse:
    workflow = WorkflowRuntime(
        action="general_chat",
        workflow_type=WorkflowType.GENERAL_CHAT,
        emitter=stream_emitter,
        user_id=user_id,
        request_id=request_id,
        chat_id=chat_id,
        metadata={"language": language},
    )
    await workflow.start()

    structured_model = get_chat_model(model="gemini-2.5-flash").with_structured_output(
        GeneralChatModelResponse,
        method="json_schema",
    )

    try:
        await workflow.start_step("prepare_chat_context")
        model_input_messages = await prepare_model_input_messages(
            chat_id=chat_id,
            content=content,
            system_prompt=GENERAL_CHAT_SYSTEM_PROMPT,
            language=language,
        )
        await workflow.complete_step("prepare_chat_context")

        await workflow.start_step("generate_chat_response")
        model_response_data: GeneralChatModelResponse = await structured_model.ainvoke(
            model_input_messages
        )
        await workflow.emit_chunk(
            step="generate_chat_response",
            chunk_type="chat_reasoning",
            data={
                "command": model_response_data.command.value,
                "user_intent": model_response_data.user_intent,
                "response_plan": model_response_data.response_plan or [],
            },
        )
        await workflow.complete_step("generate_chat_response")

        await workflow.start_step("persist_chat_messages")
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
        await workflow.complete_step("persist_chat_messages")

        response = GeneralChatResponse(
            command=model_response_data.command,
            user_message=user_message,
            model_message=model_message,
        )
        await workflow.emit_result(
            response.model_dump(mode="json", exclude_none=True, by_alias=True)
        )
        await workflow.complete({"chat_id": chat_id})
        return response

    except (ValidationError, TypeError):
        await workflow.fail(
            error_message="Received an invalid response from the AI service.",
            step=workflow.current_step,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Received an invalid response from the AI service.",
        )
    except HTTPException as exc:
        await workflow.fail(
            error_message=sanitize_http_error_message(exc.detail),
            step=workflow.current_step,
            payload={"status_code": exc.status_code},
        )
        raise
    except Exception as e:
        error_message = str(e).lower()
        if "error calling model" in error_message or "api" in error_message:
            await workflow.fail(
                error_message=f"GenAI service error: {str(e)}",
                step=workflow.current_step,
                payload={"status_code": status.HTTP_503_SERVICE_UNAVAILABLE},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"GenAI service error: {str(e)}",
            )

        await workflow.fail(
            error_message="An internal error occurred. Please try again.",
            step=workflow.current_step,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred. Please try again.",
        )
