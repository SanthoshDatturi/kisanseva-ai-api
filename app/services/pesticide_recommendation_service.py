import asyncio
import json
from datetime import datetime
from typing import List, Literal, Optional, Union

from fastapi import HTTPException, status
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from app.collections.cultivating_crop import get_cultivating_crop_from_id
from app.collections.farm_profile import get_farm_profile_from_id
from app.collections.pesticide_recommendation import (
    save_pesticide_recommendation,
    update_pesticide_stage_in_db,
)
from app.collections.pesticide_recommendation_component import (
    delete_pesticide_recommendation_components,
    save_pesticide_recommendation_component,
)
from app.core.genai_client import get_chat_model
from app.models.ai_workflow import WorkflowType
from app.models.pesticide_recommendation import (
    PesticideRecommendationComponent,
    PesticideRecommendationComponentType,
    PesticideRecommendationError,
    PesticideRecommendationResponse,
    PesticideStage,
)
from app.prompts.pesticide_recommendation_system_prompt import (
    PESTICIDE_RECOMMENDATION_SYSTEM_PROMPT,
)
from app.services.ai_workflow_runtime import (
    StreamEmitter,
    WorkflowRuntime,
    sanitize_http_error_message,
)
from app.services.files import convert_file_uri


class PesticideRecommendationEnvelope(BaseModel):
    result_type: Literal["success", "error"]
    success: Optional[PesticideRecommendationResponse] = None
    error: Optional[PesticideRecommendationError] = None


async def pesticide_recommendation(
    crop_id: str,
    farm_id: str,
    pest_or_disease_description: str,
    language: str,
    files: Optional[List[str]] = None,
    *,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    stream_emitter: Optional[StreamEmitter] = None,
) -> Union[PesticideRecommendationResponse, PesticideRecommendationError]:
    workflow = WorkflowRuntime(
        action="pesticide_recommendation",
        workflow_type=WorkflowType.PESTICIDE_RECOMMENDATION,
        emitter=stream_emitter,
        user_id=user_id,
        request_id=request_id,
        farm_id=farm_id,
        crop_id=crop_id,
        metadata={"language": language},
    )
    await workflow.start()

    try:
        files = files or []
        await workflow.start_step("load_crop_and_farm_context")
        cultivating_crop_task = get_cultivating_crop_from_id(crop_id)
        farm_profile_task = get_farm_profile_from_id(farm_id)

        cultivating_crop, farm_profile = await asyncio.gather(
            cultivating_crop_task, farm_profile_task
        )

        if not cultivating_crop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cultivating crop with id {crop_id} not found.",
            )
        crop_name = cultivating_crop.name

        if not farm_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Farm profile not found.",
            )
        await workflow.complete_step("load_crop_and_farm_context")

        input_data = {
            "farm_profile": farm_profile.model_dump(mode="json"),
            "crop_name": crop_name,
            "pest_or_disease_description": pest_or_disease_description,
            "language": language,
            "response_contract": {
                "result_type": "success|error",
                "success": "Populate when result_type is success",
                "error": "Populate when result_type is error",
            },
        }

        await workflow.start_step("prepare_input_media")
        media_blocks = []
        for file_url in files:
            uri, mime_type = await convert_file_uri(file_url)
            media_blocks.append(
                {"type": "media", "file_uri": uri, "mime_type": mime_type}
            )
        await workflow.emit_chunk(
            step="prepare_input_media",
            chunk_type="media_ready",
            data={"file_count": len(media_blocks)},
        )
        await workflow.complete_step("prepare_input_media")

        await workflow.start_step("generate_pesticide_recommendation")
        prompt = ChatPromptTemplate.from_messages([("system", "{system_prompt}")])
        messages = prompt.format_messages(system_prompt=PESTICIDE_RECOMMENDATION_SYSTEM_PROMPT)
        user_content = [{"type": "text", "text": json.dumps(input_data)}] + media_blocks
        messages.append(HumanMessage(content=user_content))

        model = (
            get_chat_model(model="gemini-2.5-flash")
            .bind_tools([{"google_search": {}}, {"google_maps": {}}])
            .with_structured_output(PesticideRecommendationEnvelope, method="json_schema")
        )
        envelope: PesticideRecommendationEnvelope = await model.ainvoke(messages)

        if envelope.result_type == "success":
            recommendation_response = envelope.success
            if recommendation_response is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="AI returned success response without payload.",
                )

            recommendation_response.crop_id = crop_id
            recommendation_response.farm_id = farm_id
            await workflow.complete_step(
                "generate_pesticide_recommendation",
                {"recommendation_count": len(recommendation_response.recommendations)},
            )

            await workflow.start_step("persist_recommendation_components")
            await delete_pesticide_recommendation_components(recommendation_response.id)

            if recommendation_response.diagnostic_report is not None:
                await save_pesticide_recommendation_component(
                    PesticideRecommendationComponent(
                        recommendation_id=recommendation_response.id,
                        farm_id=farm_id,
                        crop_id=crop_id,
                        component_type=PesticideRecommendationComponentType.DIAGNOSTIC,
                        order=0,
                        diagnostic_report=recommendation_response.diagnostic_report,
                    )
                )
                await workflow.emit_chunk(
                    step="persist_recommendation_components",
                    chunk_type="diagnostic_ready",
                    data=recommendation_response.diagnostic_report.model_dump(
                        mode="json", exclude_none=True
                    ),
                )

            for idx, recommendation in enumerate(
                recommendation_response.recommendations, start=1
            ):
                await save_pesticide_recommendation_component(
                    PesticideRecommendationComponent(
                        recommendation_id=recommendation_response.id,
                        farm_id=farm_id,
                        crop_id=crop_id,
                        component_type=PesticideRecommendationComponentType.RECOMMENDATION_ITEM,
                        order=idx,
                        recommendation=recommendation,
                    )
                )
                await workflow.emit_chunk(
                    step="persist_recommendation_components",
                    chunk_type="pesticide_item_ready",
                    data={
                        "pesticide_id": recommendation.id,
                        "pesticide_name": recommendation.pesticide_name,
                        "pesticide_type": recommendation.pesticide_type.value,
                        "rank": recommendation.rank,
                    },
                )

            await workflow.complete_step("persist_recommendation_components")
            await workflow.start_step("save_final_recommendation")
            await save_pesticide_recommendation(recommendation_response)
            await workflow.complete_step(
                "save_final_recommendation",
                {"recommendation_id": recommendation_response.id},
            )
            await workflow.emit_result(
                recommendation_response.model_dump(
                    mode="json", exclude_none=True, by_alias=True
                )
            )
            await workflow.complete({"recommendation_id": recommendation_response.id})
            return recommendation_response

        error_response = envelope.error
        if error_response is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI returned error response without payload.",
            )
        await workflow.complete_step("generate_pesticide_recommendation")
        await workflow.emit_result(error_response.model_dump(mode="json", exclude_none=True))
        await workflow.complete({"result_type": "error"})
        return error_response

    except HTTPException as exc:
        await workflow.fail(
            error_message=sanitize_http_error_message(exc.detail),
            step=workflow.current_step,
            payload={"status_code": exc.status_code},
        )
        raise
    except Exception:
        await workflow.fail(
            error_message="Internal server error in pesticide recommendation",
            step=workflow.current_step,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error in pesticide recommendation",
        )


async def update_pesticide_stage(
    recommendation_id: str,
    pesticide_id: str,
    stage: PesticideStage,
    applied_date: Optional[datetime] = None,
) -> bool:
    if stage != PesticideStage.APPLIED:
        applied_date = None

    if stage == PesticideStage.APPLIED and applied_date is None:
        raise HTTPException(
            status_code=400,
            detail="Applied date must be provided when stage is 'applied'",
        )

    return await update_pesticide_stage_in_db(
        recommendation_id=recommendation_id,
        pesticide_id=pesticide_id,
        stage=stage,
        applied_date=applied_date,
    )
