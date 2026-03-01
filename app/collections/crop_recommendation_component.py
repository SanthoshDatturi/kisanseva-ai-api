from typing import List

from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.mongodb import get_crop_recommendation_component_collection
from app.models.crop_recommendation import CropRecommendationComponent


async def save_crop_recommendation_component(
    component: CropRecommendationComponent,
) -> CropRecommendationComponent:
    collection: AsyncIOMotorCollection = get_crop_recommendation_component_collection()
    payload = component.model_dump(mode="json", exclude_none=True, by_alias=True)
    await collection.replace_one({"_id": component.id}, payload, upsert=True)
    stored = await collection.find_one({"_id": component.id})
    return CropRecommendationComponent.model_validate(stored)


async def get_crop_recommendation_components(
    recommendation_id: str,
) -> List[CropRecommendationComponent]:
    collection: AsyncIOMotorCollection = get_crop_recommendation_component_collection()
    cursor = collection.find({"recommendation_id": recommendation_id}).sort("order", 1)
    return [CropRecommendationComponent.model_validate(item) async for item in cursor]


async def delete_crop_recommendation_components(
    recommendation_id: str,
) -> bool:
    collection: AsyncIOMotorCollection = get_crop_recommendation_component_collection()
    await collection.delete_many({"recommendation_id": recommendation_id})
    return True
