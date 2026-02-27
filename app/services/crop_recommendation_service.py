import asyncio
import json

from fastapi import HTTPException, status
from langchain_core.prompts import ChatPromptTemplate

from app.collections.crop_images import (
    get_crop_image_urls_by_crop_names,
)
from app.collections.crop_recommendation import (
    get_crop_recommendation_from_farm_id,
    get_recommended_crop_from_id,
    save_crop_recommendation,
)
from app.collections.cultivating_crop import (
    save_cultivating_crop,
    save_intercropping_details,
)
from app.collections.cultivation_calendar import save_cultivation_calendar
from app.collections.farm_profile import get_farm_profile_from_id
from app.collections.investment_breakdown import save_investment_breakdown
from app.collections.soil_health_recommendations import save_soil_health_recommendations
from app.core.genai_client import get_chat_model
from app.models.crop_recommendation import (
    CropRecommendationResponse,
    CropSelectionResponse,
    InterCropRecommendation,
    MonoCrop,
)
from app.models.cultivating_crop import CropState, CultivatingCrop, IntercroppingDetails
from app.models.farm_profile import FarmProfile
from app.prompts.crop_recommendation_system_prompt import (
    CROP_RECOMMENDATION_SYSTEM_PROMPT,
)
from app.prompts.selected_crop_detailer_system_prompt import (
    SELECTED_CROP_DETAILER_SYSTEM_PROMPT,
)

from .weather_service import get_5_day_3_hour_forecast, get_current_weather


def _build_structured_chain(model, schema):
    prompt = ChatPromptTemplate.from_messages(
        [("system", "{system_prompt}"), ("human", "{input_json}")]
    )
    return prompt | model.with_structured_output(schema, method="json_schema")


async def _populate_crop_image_urls(
    crop_recommendation_response: CropRecommendationResponse,
) -> None:
    crop_names: list[str] = []

    crop_names.extend(
        [
            crop.image_url if crop.image_url else crop.crop_name
            for crop in crop_recommendation_response.mono_crops
        ]
    )
    for inter_crop in crop_recommendation_response.inter_crops:
        crop_names.extend([crop.crop_name for crop in inter_crop.crops])

    if not crop_names:
        return

    unique_crop_names = list(dict.fromkeys(crop_names))
    crop_image_urls = await get_crop_image_urls_by_crop_names(unique_crop_names)

    for crop in crop_recommendation_response.mono_crops:
        crop.image_url = crop_image_urls.get(crop.crop_name)

    for inter_crop in crop_recommendation_response.inter_crops:
        for crop in inter_crop.crops:
            crop.image_url = crop_image_urls.get(crop.crop_name)


async def crop_recommendation(
    farm_id: str, language: str
) -> CropRecommendationResponse:
    try:
        prev_crop_recommendation = await get_crop_recommendation_from_farm_id(farm_id)
        if prev_crop_recommendation:
            await _populate_crop_image_urls(prev_crop_recommendation)
            return await save_crop_recommendation(prev_crop_recommendation)

        farm_profile: FarmProfile = await get_farm_profile_from_id(farm_id)

        if not farm_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Farm profile not found.",
            )

        weather_forecast = await get_5_day_3_hour_forecast(
            farm_profile.location.latitude, farm_profile.location.longitude
        )

        if not weather_forecast:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not retrieve weather forecast. Please try again later.",
            )

        grounded_model = get_chat_model(model="gemini-2.5-flash").bind_tools(
            [{"google_search": {}}, {"google_maps": {}}],
            tool_config={
                "retrieval_config": {
                    "lat_lng": {
                        "latitude": farm_profile.location.latitude,
                        "longitude": farm_profile.location.longitude,
                    }
                }
            },
        )
        chain = _build_structured_chain(
            model=grounded_model,
            schema=CropRecommendationResponse,
        )

        input_data = {
            "farm_profile": farm_profile.model_dump(mode="json"),
            "language": language,
            "5_d_3_h_weather_forecast": weather_forecast.model_dump(mode="json"),
        }

        crop_recommendation_response: CropRecommendationResponse = await chain.ainvoke(
            {
                "system_prompt": CROP_RECOMMENDATION_SYSTEM_PROMPT,
                "input_json": json.dumps(input_data),
            }
        )

        crop_recommendation_response.farm_id = farm_id
        await save_crop_recommendation(crop_recommendation_response)

        try:
            await _populate_crop_image_urls(crop_recommendation_response)
            await save_crop_recommendation(crop_recommendation_response)
        except Exception:
            pass

        return crop_recommendation_response
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error. Please try again later.",
        )


async def select_crop_from_recommendation(
    farm_id: str,
    crop_recommendation_response_id: str,
    selected_crop_id: str,
    language: str,
) -> CropSelectionResponse:
    try:
        farm_profile: FarmProfile = await get_farm_profile_from_id(farm_id)

        if not farm_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Farm profile not found.",
            )

        weather_task = get_5_day_3_hour_forecast(
            farm_profile.location.latitude, farm_profile.location.longitude
        )
        current_weather_task = get_current_weather(
            farm_profile.location.latitude, farm_profile.location.longitude
        )
        recommended_crop_details_task = get_recommended_crop_from_id(
            crop_recommendation_response_id, selected_crop_id
        )

        (
            weather_forecast,
            current_weather,
            recommended_crop_details,
        ) = await asyncio.gather(
            weather_task,
            current_weather_task,
            recommended_crop_details_task,
        )

        if not weather_forecast:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not retrieve weather forecast. Please try again later.",
            )

        grounded_model = get_chat_model(
            model="gemini-2.5-flash",
            thinking_budget=-1,
            include_thoughts=True,
        ).bind_tools(
            [{"google_search": {}}, {"google_maps": {}}],
            tool_config={
                "retrieval_config": {
                    "lat_lng": {
                        "latitude": farm_profile.location.latitude,
                        "longitude": farm_profile.location.longitude,
                    }
                }
            },
        )
        chain = _build_structured_chain(
            model=grounded_model,
            schema=CropSelectionResponse,
        )

        input_data = {
            "farm_profile": farm_profile.model_dump(mode="json"),
            "language": language,
            "weather_forecast": weather_forecast.model_dump(mode="json"),
            "current_weather": current_weather.model_dump(mode="json"),
            "recommended_crop_details": recommended_crop_details.model_dump(
                mode="json"
            ),
        }

        details: CropSelectionResponse = await chain.ainvoke(
            {
                "system_prompt": SELECTED_CROP_DETAILER_SYSTEM_PROMPT,
                "input_json": json.dumps(input_data),
            }
        )

        if isinstance(recommended_crop_details, MonoCrop):
            await save_cultivation_calendar(details.cultivation_calendar[0])
            await save_investment_breakdown(details.investment_breakdown[0])
            cultivating_crop: CultivatingCrop = CultivatingCrop(
                id=selected_crop_id,
                farm_id=farm_id,
                name=recommended_crop_details.crop_name,
                variety=recommended_crop_details.variety,
                image_url=recommended_crop_details.image_url,
                crop_state=CropState.SELECTED,
                description=recommended_crop_details.description,
            )

            await save_cultivating_crop(cultivating_crop)

        if isinstance(recommended_crop_details, InterCropRecommendation):
            for i, crop in enumerate(recommended_crop_details.crops):
                await save_cultivation_calendar(details.cultivation_calendar[i])
                await save_investment_breakdown(details.investment_breakdown[i])
                cultivating_crop: CultivatingCrop = CultivatingCrop(
                    id=crop.id,
                    farm_id=farm_id,
                    name=crop.crop_name,
                    variety=crop.variety,
                    image_url=crop.image_url,
                    crop_state=CropState.SELECTED,
                    description=crop.description,
                    intercropping_id=recommended_crop_details.id,
                )
                await save_cultivating_crop(cultivating_crop)
            await save_intercropping_details(
                IntercroppingDetails(
                    id=recommended_crop_details.id,
                    intercrop_type=recommended_crop_details.intercrop_type,
                    arrangement=recommended_crop_details.arrangement,
                    no_of_crops=recommended_crop_details.no_of_crops,
                    specific_arrangement=recommended_crop_details.specific_arrangement,
                    benefits=recommended_crop_details.benefits,
                )
            )

        details.soil_health_recommendations.crop_id = selected_crop_id
        await save_soil_health_recommendations(details.soil_health_recommendations)

        return details
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error. Please try again later.",
        )
