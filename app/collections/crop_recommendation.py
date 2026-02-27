from typing import Union

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.mongodb import get_crop_recommendation_collection
from app.models.crop_recommendation import (
    CropRecommendationResponse,
    InterCropRecommendation,
    MonoCrop,
)


async def get_crop_recommendation_from_farm_id(
    farm_id: str,
) -> CropRecommendationResponse:
    collection: AsyncIOMotorCollection = get_crop_recommendation_collection()
    try:
        item = await collection.find_one({"farm_id": farm_id})
        return CropRecommendationResponse.model_validate(item) if item else None
    except Exception as e:
        raise e


async def get_recommended_crop_from_id(
    recommendation_id: str,
    crop_id: str,
) -> Union[MonoCrop, InterCropRecommendation]:
    collection: AsyncIOMotorCollection = get_crop_recommendation_collection()
    try:
        recommendation = await collection.find_one({"_id": recommendation_id})
        if not recommendation:
            raise HTTPException(
                status_code=404, detail=f"Recommendation {recommendation_id} not found"
            )

        for mono_crop in recommendation.get("mono_crops", []):
            if mono_crop.get("_id") == crop_id or mono_crop.get("id") == crop_id:
                return MonoCrop(**mono_crop)

        for inter_crop in recommendation.get("inter_crops", []):
            if inter_crop.get("_id") == crop_id or inter_crop.get("id") == crop_id:
                return InterCropRecommendation(**inter_crop)

        raise HTTPException(
            status_code=404,
            detail=f"Crop with id {crop_id} not found in recommendation {recommendation_id}",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise e


async def get_recommendation_from_id(
    recommendation_id: str,
) -> CropRecommendationResponse:
    collection: AsyncIOMotorCollection = get_crop_recommendation_collection()
    try:
        response = await collection.find_one({"_id": recommendation_id})
        if not response:
            raise HTTPException(
                status_code=404, detail=f"Recommendation {recommendation_id} not found"
            )
        return CropRecommendationResponse.model_validate(response)
    except HTTPException:
        raise
    except Exception as e:
        raise e


async def save_crop_recommendation(
    crop_recommendation: CropRecommendationResponse,
) -> CropRecommendationResponse:
    collection: AsyncIOMotorCollection = get_crop_recommendation_collection()
    try:
        payload = crop_recommendation.model_dump(mode="json", exclude_none=True, by_alias=True)
        await collection.replace_one({"_id": crop_recommendation.id}, payload, upsert=True)
        response = await collection.find_one({"_id": crop_recommendation.id})
        return CropRecommendationResponse.model_validate(response)
    except Exception as e:
        raise e
