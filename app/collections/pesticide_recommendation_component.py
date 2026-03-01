from typing import List

from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.mongodb import get_pesticide_recommendation_component_collection
from app.models.pesticide_recommendation import PesticideRecommendationComponent


async def save_pesticide_recommendation_component(
    component: PesticideRecommendationComponent,
) -> PesticideRecommendationComponent:
    collection: AsyncIOMotorCollection = get_pesticide_recommendation_component_collection()
    payload = component.model_dump(mode="json", exclude_none=True, by_alias=True)
    await collection.replace_one({"_id": component.id}, payload, upsert=True)
    stored = await collection.find_one({"_id": component.id})
    return PesticideRecommendationComponent.model_validate(stored)


async def get_pesticide_recommendation_components(
    recommendation_id: str,
) -> List[PesticideRecommendationComponent]:
    collection: AsyncIOMotorCollection = get_pesticide_recommendation_component_collection()
    cursor = collection.find({"recommendation_id": recommendation_id}).sort("order", 1)
    return [PesticideRecommendationComponent.model_validate(item) async for item in cursor]


async def delete_pesticide_recommendation_components(
    recommendation_id: str,
) -> bool:
    collection: AsyncIOMotorCollection = get_pesticide_recommendation_component_collection()
    await collection.delete_many({"recommendation_id": recommendation_id})
    return True
