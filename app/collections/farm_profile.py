from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.mongodb import get_farm_profile_collection
from app.models.farm_profile import FarmProfile


async def get_farm_profile_from_id(farm_id: str) -> FarmProfile:
    farm_profile_collection: AsyncIOMotorCollection = get_farm_profile_collection()
    try:
        response = await farm_profile_collection.find_one({"_id": farm_id})
        return FarmProfile.model_validate(response) if response else None
    except Exception:
        raise


async def get_farm_profiles_from_user_id(user_id: str) -> list[FarmProfile]:
    farm_profile_collection: AsyncIOMotorCollection = get_farm_profile_collection()
    try:
        items = farm_profile_collection.find({"farmer_id": user_id})
        return [FarmProfile.model_validate(item) async for item in items]
    except Exception:
        raise


async def save_farm_profile(farm_profile: FarmProfile) -> FarmProfile:
    farm_profile_collection: AsyncIOMotorCollection = get_farm_profile_collection()
    try:
        payload = farm_profile.model_dump(mode="json", exclude_none=True, by_alias=True)
        await farm_profile_collection.replace_one(
            {"_id": farm_profile.id}, payload, upsert=True
        )
        response = await farm_profile_collection.find_one({"_id": farm_profile.id})
        return FarmProfile.model_validate(response)
    except Exception:
        raise


async def delete_farm_profile(farm_id: str) -> bool:
    farm_profile_collection: AsyncIOMotorCollection = get_farm_profile_collection()
    try:
        await farm_profile_collection.delete_one({"_id": farm_id})
        return True
    except Exception:
        raise


async def delete_farm_profiles_from_user_id(user_id: str) -> bool:
    farm_profile_collection: AsyncIOMotorCollection = get_farm_profile_collection()
    try:
        await farm_profile_collection.delete_many({"farmer_id": user_id})
        return True
    except Exception:
        raise
