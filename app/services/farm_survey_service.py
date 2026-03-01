from typing import Optional

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.collections.farm_profile import save_farm_profile
from app.core.genai_client import get_chat_model
from app.models.ai_workflow import WorkflowType
from app.models.chat_session import (
    Command,
    MessageContent,
)
from app.models.farm_survey_agent_response import (
    FarmSurveyAgentMappedResponse,
    FarmSurveyAgentResponse,
)
from app.prompts.farm_survey_agent_system_prompt import (
    FARM_SURVEY_AGENT_SYSTEM_PROMPT,
)
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


async def farm_survey_agent(
    user_id: str,
    language: str,
    content: MessageContent,
    chat_id: str,
    request_id: str,
    audio_response: bool = False,
    *,
    stream_emitter: Optional[StreamEmitter] = None,
) -> FarmSurveyAgentMappedResponse:
    workflow = WorkflowRuntime(
        action="farm_survey_agent",
        workflow_type=WorkflowType.FARM_SURVEY,
        emitter=stream_emitter,
        user_id=user_id,
        request_id=request_id,
        chat_id=chat_id,
        metadata={"language": language},
    )
    await workflow.start()

    try:
        await workflow.start_step("prepare_survey_context")
        model_input_messages = await prepare_model_input_messages(
            chat_id=chat_id,
            content=content,
            system_prompt=FARM_SURVEY_AGENT_SYSTEM_PROMPT,
            language=language,
        )
        await workflow.complete_step("prepare_survey_context")

        await workflow.start_step("generate_survey_response")
        model = (
            get_chat_model(model="gemini-2.5-flash")
            .bind_tools([{"google_search": {}}, {"google_maps": {}}])
            .with_structured_output(FarmSurveyAgentResponse, method="json_schema")
        )

        response_message: FarmSurveyAgentResponse = await model.ainvoke(
            model_input_messages
        )
        await workflow.emit_chunk(
            step="generate_survey_response",
            chunk_type="survey_progress",
            data={
                "command": response_message.command.value,
                "collected_fields": response_message.collected_fields or [],
                "missing_fields": response_message.missing_fields or [],
            },
        )
        await workflow.complete_step("generate_survey_response")

        await workflow.start_step("persist_survey_messages")
        user_message = await save_user_message_with_fallback(
            chat_id=chat_id,
            content=content,
            request_id=request_id,
            fallback_text=response_message.user_query or "",
        )

        if response_message.command == Command.EXIT and response_message.farm_profile:
            response_message.farm_profile.farmer_id = user_id
            await save_farm_profile(response_message.farm_profile)
            await workflow.emit_chunk(
                step="persist_survey_messages",
                chunk_type="farm_profile_saved",
                data={"farm_id": response_message.farm_profile.id},
            )

        model_message = await save_model_response_message(
            chat_id=chat_id,
            text=response_message.message_to_user,
            request_id=request_id,
            language=language,
            audio_response=audio_response,
            blob_name=user_message.id,
            path_prefix=f"{user_id}/{chat_id}",
        )
        await workflow.complete_step("persist_survey_messages")

        mapped_response: FarmSurveyAgentMappedResponse = FarmSurveyAgentMappedResponse(
            command=response_message.command,
            farm_profile=response_message.user_language_farm_profile,
            user_message=user_message,
            model_message=model_message,
        )
        await workflow.emit_result(
            mapped_response.model_dump(mode="json", exclude_none=True, by_alias=True)
        )
        await workflow.complete({"chat_id": chat_id})
        return mapped_response

    except (ValidationError, TypeError):
        await workflow.fail(
            error_message="Error validating data. Please try again later.",
            step=workflow.current_step,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error validating data. Please try again later.",
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
            error_message="Internal server error. Please try again later.",
            step=workflow.current_step,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error. Please try again later.",
        )
