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
from app.core.genai_client import get_chat_model
from app.models.pesticide_recommendation import (
    PesticideRecommendationError,
    PesticideRecommendationResponse,
    PesticideStage,
)
from app.prompts.pesticide_recommendation_system_prompt import (
    PESTICIDE_RECOMMENDATION_SYSTEM_PROMPT,
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
    files: List[str] = [],
) -> Union[PesticideRecommendationResponse, PesticideRecommendationError]:
    try:
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

        media_blocks = []
        for file_url in files:
            uri, mime_type = await convert_file_uri(file_url)
            media_blocks.append(
                {"type": "media", "file_uri": uri, "mime_type": mime_type}
            )

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
            await save_pesticide_recommendation(recommendation_response)
            return recommendation_response

        error_response = envelope.error
        if error_response is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI returned error response without payload.",
            )
        return error_response

    except HTTPException:
        raise
    except Exception:
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
