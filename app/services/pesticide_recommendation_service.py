import asyncio
import json
from datetime import datetime
from typing import List, Optional, Union

from fastapi import HTTPException, status
from google.genai import Client, types
from pydantic import ValidationError

from app.collections.cultivating_crop import get_cultivating_crop_from_id
from app.collections.farm_profile import get_farm_profile_from_id
from app.collections.pesticide_recommendation import (
    save_pesticide_recommendation,
    update_pesticide_stage_in_db,
)
from app.core.genai_client import get_client
from app.core.model_validator import get_validated_model_from_text
from app.models.pesticide_recommendation import (
    PesticideRecommendationError,
    PesticideRecommendationResponse,
    PesticideStage,
)
from app.prompts.pesticide_recommendation_system_prompt import (
    PESTICIDE_RECOMMENDATION_SYSTEM_PROMPT,
)
from app.services.files import convert_file_uri


async def pesticide_recommendation(
    crop_id: str,
    farm_id: str,
    pest_or_disease_description: str,
    language: str,
    files: List[str] = [],
) -> Union[PesticideRecommendationResponse, PesticideRecommendationError]:
    """
    Generates pesticide recommendations based on crop, farm data, pest/disease, and files.

    Args:
        crop_id (str): The ID of the cultivating crop.
        pest_or_disease_description (str): A description of the pest or disease.
        language (str): The language for the response.
        files (List[str]): A list of image/audio URLs showing the pest or disease.

    Returns:
        PesticideRecommendationResponse: The validated pesticide recommendations.
    """
    try:
        client: Client = get_client()
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

        grounding_tools = [
            types.Tool(google_search=types.GoogleSearch()),
            types.Tool(google_maps=types.GoogleMaps()),
        ]

        config = types.GenerateContentConfig(
            system_instruction=PESTICIDE_RECOMMENDATION_SYSTEM_PROMPT,
            tools=grounding_tools,
        )

        parts = []
        for file_url in files:
            uri, mime_type = await convert_file_uri(file_url)
            parts.append(types.Part.from_uri(file_uri=uri, mime_type=mime_type))

        input_data = {
            "farm_profile": farm_profile.model_dump(mode="json"),
            "crop_name": crop_name,
            "pest_or_disease_description": pest_or_disease_description,
            "language": language,
        }

        parts.append(types.Part(text=json.dumps(input_data)))

        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=types.Content(parts=parts, role="user"),
            config=config,
        )

        try:
            recommendation_response = get_validated_model_from_text(
                response.text, PesticideRecommendationResponse
            )

            recommendation_response.crop_id = crop_id
            recommendation_response.farm_id = farm_id
            await save_pesticide_recommendation(recommendation_response)

            return recommendation_response
        except ValidationError:
            error_response = get_validated_model_from_text(
                response.text, PesticideRecommendationError
            )
            return error_response

    except HTTPException as e:
        raise e
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
