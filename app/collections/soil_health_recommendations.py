from typing import List

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.mongodb import get_soil_health_recommendations_collection
from app.models.soil_health_recommendations import SoilHealthRecommendations


async def get_soil_health_recommendations_from_id(
    soil_health_recommendations_id: str,
) -> SoilHealthRecommendations:
    collection: AsyncIOMotorCollection = get_soil_health_recommendations_collection()
    try:
        response = await collection.find_one({"_id": soil_health_recommendations_id})
        if not response:
            raise HTTPException(
                status_code=404,
                detail=f"Soil health recommendation {soil_health_recommendations_id} not found",
            )
        return SoilHealthRecommendations.model_validate(response)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def save_soil_health_recommendations(
    soil_health_recommendations: SoilHealthRecommendations,
) -> SoilHealthRecommendations:
    collection: AsyncIOMotorCollection = get_soil_health_recommendations_collection()
    try:
        payload = soil_health_recommendations.model_dump(mode="json", exclude_none=True, by_alias=True)
        await collection.replace_one(
            {"_id": soil_health_recommendations.id}, payload, upsert=True
        )
        response = await collection.find_one({"_id": soil_health_recommendations.id})
        return SoilHealthRecommendations.model_validate(response)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error saving soil health recommendation: {e}"
        )


async def get_soil_health_recommendations_from_crop_id(
    crop_id: str,
) -> List[SoilHealthRecommendations]:
    collection: AsyncIOMotorCollection = get_soil_health_recommendations_collection()
    try:
        items = collection.find({"crop_id": crop_id})
        return [SoilHealthRecommendations.model_validate(item) async for item in items]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def delete_soil_health_recommendations(
    soil_health_recommendations_id: str,
) -> bool:
    collection: AsyncIOMotorCollection = get_soil_health_recommendations_collection()
    try:
        await collection.delete_one({"_id": soil_health_recommendations_id})
        return True
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error deleting recommendation: {e}"
        )
