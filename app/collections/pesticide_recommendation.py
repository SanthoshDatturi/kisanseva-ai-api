from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.mongodb import get_pesticide_recommendation_collection
from app.models.pesticide_recommendation import (
    PesticideRecommendationResponse,
    PesticideStage,
)


async def save_pesticide_recommendation(
    recommendation: PesticideRecommendationResponse,
) -> PesticideRecommendationResponse:
    collection: AsyncIOMotorCollection = get_pesticide_recommendation_collection()
    try:
        payload = recommendation.model_dump(mode="json", exclude_none=True, by_alias=True)
        await collection.replace_one({"_id": recommendation.id}, payload, upsert=True)
        response = await collection.find_one({"_id": recommendation.id})
        return PesticideRecommendationResponse.model_validate(response)
    except Exception:
        raise HTTPException(
            status_code=500, detail="Error saving pesticide recommendation"
        )


async def get_pesticide_recommendation_from_id(
    recommendation_id: str,
) -> PesticideRecommendationResponse:
    collection: AsyncIOMotorCollection = get_pesticide_recommendation_collection()
    response = await collection.find_one({"_id": recommendation_id})
    if not response:
        raise HTTPException(
            status_code=404, detail=f"Recommendation {recommendation_id} not found"
        )
    return PesticideRecommendationResponse.model_validate(response)


async def get_pesticide_recommendations_from_crop_id(
    crop_id: str,
) -> List[PesticideRecommendationResponse]:
    collection: AsyncIOMotorCollection = get_pesticide_recommendation_collection()
    try:
        items = collection.find({"crop_id": crop_id})
        return [
            PesticideRecommendationResponse.model_validate(item) async for item in items
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error getting pesticide recommendations: {e}"
        )


async def delete_pesticide_recommendation(
    recommendation_id: str,
) -> bool:
    collection: AsyncIOMotorCollection = get_pesticide_recommendation_collection()
    try:
        await collection.delete_one({"_id": recommendation_id})
        return True
    except Exception:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting pesticide recommendation {recommendation_id}",
        )


async def delete_pesticide_recommendations_by_crop_id(crop_id: str) -> bool:
    """Deletes all pesticide recommendations associated with a crop_id."""
    collection: AsyncIOMotorCollection = get_pesticide_recommendation_collection()
    try:
        await collection.delete_many({"crop_id": crop_id})
        return True
    except Exception:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting pesticide recommendations for crop {crop_id}",
        )


async def update_pesticide_stage_in_db(
    recommendation_id: str,
    pesticide_id: str,
    stage: PesticideStage,
    applied_date: Optional[datetime] = None,
) -> bool:
    collection: AsyncIOMotorCollection = get_pesticide_recommendation_collection()
    try:
        item = await collection.find_one({"_id": recommendation_id})
        if not item:
            raise HTTPException(
                status_code=404, detail=f"Recommendation {recommendation_id} not found"
            )

        recommendation = PesticideRecommendationResponse.model_validate(item)

        updated = False
        for pesticide in recommendation.recommendations:
            if pesticide.id == pesticide_id:
                pesticide.stage = stage
                pesticide.applied_date = applied_date
                updated = True
                break

        if updated:
            payload = recommendation.model_dump(mode="json", exclude_none=True, by_alias=True)
            await collection.replace_one({"_id": recommendation.id}, payload, upsert=True)
            return True
        return False
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error updating pesticide stage: {e}"
        )
