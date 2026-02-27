from datetime import date
from typing import Optional, Union

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.mongodb import get_crop_recommendation_collection
from app.models.crop_recommendation import (
    CropRecommendationResponse,
    InterCropRecommendation,
    MonoCrop,
)


def _is_recommendation_expired(recommendation: CropRecommendationResponse) -> bool:
    if recommendation.expiration_date is None:
        return False
    return recommendation.expiration_date < date.today()


async def get_crop_recommendation_from_farm_id(
    farm_id: str,
    include_expired: bool = False,
) -> Optional[CropRecommendationResponse]:
    collection: AsyncIOMotorCollection = get_crop_recommendation_collection()
    try:
        item = await collection.find_one({"farm_id": farm_id}, sort=[("timestamp", -1)])
        if not item:
            return None

        recommendation = CropRecommendationResponse.model_validate(item)
        if not include_expired and _is_recommendation_expired(recommendation):
            return None
        return recommendation
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

        recommendation_obj = CropRecommendationResponse.model_validate(recommendation)
        if _is_recommendation_expired(recommendation_obj):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail=f"Recommendation {recommendation_id} has expired",
            )

        for mono_crop in recommendation_obj.mono_crops:
            if mono_crop.id == crop_id:
                return mono_crop

        for inter_crop in recommendation_obj.inter_crops:
            if inter_crop.id == crop_id:
                return inter_crop

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
        recommendation = CropRecommendationResponse.model_validate(response)
        if _is_recommendation_expired(recommendation):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail=f"Recommendation {recommendation_id} has expired",
            )
        return recommendation
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
