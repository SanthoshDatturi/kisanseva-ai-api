import asyncio
import json
import uuid
from shlex import quote
from typing import Optional

import aiohttp
from fastapi import HTTPException, status
from google.genai import Client, types

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
from app.core.config import settings
from app.core.genai_client import get_client
from app.core.model_validator import get_validated_model_from_text
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

from .files import FileType, file_upload_to_blob_storage
from .weather_service import get_5_day_3_hour_forecast, get_current_weather


async def attach_crop_image_urls(
    crop_recommendation_response: CropRecommendationResponse,
) -> CropRecommendationResponse:
    """
    Fetch crop images using Hugging Face Router API (async, raw bytes).
    Falls back to Pollinations if Hugging Face fails.
    """

    # 1️⃣ Collect crop names (FIXED)
    all_crop_names = [c.crop_name for c in crop_recommendation_response.mono_crops]
    for intercrop in crop_recommendation_response.inter_crops:
        all_crop_names.extend([c.crop_name for c in intercrop.crops])

    hf_token = settings.HUGGINGFACE_API_KEY
    if not hf_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="HuggingFace API key is not configured.",
        )

    hf_headers = {
        "Authorization": f"Bearer {hf_token}",
        "Accept": "image/png",
        "Content-Type": "application/json",
    }

    async def generate_image_pollinations(prompt: str) -> bytes:
        """Fallback image generation using Pollinations"""
        url = f"https://text.pollinations.ai/{quote(prompt)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError("Pollinations image generation failed")
                return await resp.read()

    async def fetch_image_url(crop_name: str) -> Optional[str]:
        prompt = (
            f"High quality realistic agricultural photograph of {crop_name} crop, "
            f"natural lighting, sharp focus, no text, no watermark"
        )

        image_bytes = None

        # 1️⃣ Try Hugging Face (NO RAISES HERE)
        try:
            async with aiohttp.ClientSession(headers=hf_headers) as session:
                async with session.post(
                    settings.HUGGINGFACE_API_URL,
                    json={
                        "inputs": prompt,
                        "parameters": {
                            "width": 1024,
                            "height": 576,
                            "guidance_scale": 7.5,
                            "num_inference_steps": 30,
                        },
                    },
                    timeout=aiohttp.ClientTimeout(total=180),
                ) as resp:
                    raw = await resp.read()

                    # ✅ Validate image bytes ONLY
                    if raw.startswith(b"\x89PNG") or raw.startswith(b"\xff\xd8"):
                        image_bytes = raw

        except Exception:
            # ❗ swallow ALL HF errors
            image_bytes = None

        # 2️⃣ Pollinations fallback (ALWAYS REACHED IF HF FAILED)
        if image_bytes is None:
            image_bytes = await generate_image_pollinations(prompt)

        # 3️⃣ Final failure (ONLY PLACE YOU MAY RAISE)
        if image_bytes is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Image generation failed for crop: {crop_name}",
            )

        mime_type = "image/png" if image_bytes.startswith(b"\x89PNG") else "image/jpeg"

        image_url = await file_upload_to_blob_storage(
            file_stream=image_bytes,
            blob_name=f"{uuid.uuid4().hex}.jpg",
            file_type=FileType.IMAGE,
            mime_type=mime_type,
        )

        return image_url

    # 6️⃣ Run all image generations in parallel
    tasks = [fetch_image_url(name) for name in all_crop_names]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    image_urls = dict(zip(all_crop_names, results))

    # 7️⃣ Attach URLs back to crop objects
    all_crops = crop_recommendation_response.mono_crops + [
        c for ic in crop_recommendation_response.inter_crops for c in ic.crops
    ]

    for crop in all_crops:
        crop.image_url = image_urls.get(crop.crop_name)

    return crop_recommendation_response


async def crop_recommendation(
    farm_id: str, language: str
) -> CropRecommendationResponse:
    try:
        prev_crop_recommendation = await get_crop_recommendation_from_farm_id(farm_id)
        if prev_crop_recommendation:
            crop_recommendation_response = await attach_crop_image_urls(
                prev_crop_recommendation
            )
            return await save_crop_recommendation(crop_recommendation_response)

        client: Client = get_client()
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

        grounding_tools = [
            types.Tool(google_search=types.GoogleSearch()),
            types.Tool(google_maps=types.GoogleMaps()),
        ]

        config = types.GenerateContentConfig(
            system_instruction=CROP_RECOMMENDATION_SYSTEM_PROMPT,
            safety_settings=[
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                )
            ],
            tools=grounding_tools,
            tool_config=types.ToolConfig(
                retrieval_config=types.RetrievalConfig(
                    lat_lng=types.LatLng(
                        latitude=farm_profile.location.latitude,
                        longitude=farm_profile.location.longitude,
                    )
                )
            ),
        )

        input_data = {
            "farm_profile": farm_profile.model_dump(mode="json"),
            "language": language,
            "5_d_3_h_weather_forecast": weather_forecast.model_dump(mode="json"),
        }

        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash", contents=[json.dumps(input_data)], config=config
        )

        crop_recommendation_response = get_validated_model_from_text(
            response.text, CropRecommendationResponse
        )

        if not crop_recommendation_response:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER,
                detail="Error generating crop recommendations. Please try again later.",
            )

        crop_recommendation_response.farm_id = farm_id
        await save_crop_recommendation(crop_recommendation_response)

        crop_recommendation_response = await attach_crop_image_urls(
            crop_recommendation_response
        )

        await save_crop_recommendation(crop_recommendation_response)

        return crop_recommendation_response
    except HTTPException as e:
        raise e  # Re-raise HTTPException to be handled by FastAPI
    except Exception:
        # Log the exception here if you have a logger configured
        # logger.error(f"Error in crop_recommendation: {e}")
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
        client: Client = get_client()
        farm_profile: FarmProfile = await get_farm_profile_from_id(farm_id)

        if not farm_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Farm profile not found.",
            )

        # Run data fetches concurrently
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

        grounding_tools = [
            types.Tool(google_search=types.GoogleSearch()),
            types.Tool(google_maps=types.GoogleMaps()),
        ]

        config = types.GenerateContentConfig(
            system_instruction=SELECTED_CROP_DETAILER_SYSTEM_PROMPT,
            thinking_config=types.ThinkingConfig(
                thinking_budget=-1, include_thoughts=True
            ),
            safety_settings=[
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                )
            ],
            tools=grounding_tools,
            tool_config=types.ToolConfig(
                retrieval_config=types.RetrievalConfig(
                    lat_lng=types.LatLng(
                        latitude=farm_profile.location.latitude,
                        longitude=farm_profile.location.longitude,
                    )
                )
            ),
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

        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash", contents=[json.dumps(input_data)], config=config
        )

        details: CropSelectionResponse = get_validated_model_from_text(
            response.text, CropSelectionResponse
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
    except HTTPException as e:
        raise e  # Re-raise HTTPException to be handled by FastAPI
    except Exception:
        # Log the exception here if you have a logger configured
        # logger.error(f"Error in select_crop_from_recommendation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error. Please try again later.",
        )
