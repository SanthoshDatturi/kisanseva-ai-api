from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.mongodb import (
    get_cultivating_crop_collection,
    get_intercropping_details_collection,
)
from app.models.cultivating_crop import CultivatingCrop, IntercroppingDetails


async def get_cultivating_crop_from_id(
    cultivating_crop_id: str,
) -> CultivatingCrop:
    cultivating_crop_collection: AsyncIOMotorCollection = get_cultivating_crop_collection()
    try:
        response = await cultivating_crop_collection.find_one({"_id": cultivating_crop_id})
        return CultivatingCrop.model_validate(response) if response else None
    except Exception:
        raise


async def get_cultivating_crops_from_farm_id(
    farm_id: str,
) -> list[CultivatingCrop]:
    cultivating_crop_collection: AsyncIOMotorCollection = get_cultivating_crop_collection()
    try:
        items = cultivating_crop_collection.find({"farm_id": farm_id})
        return [CultivatingCrop.model_validate(item) async for item in items]
    except Exception:
        raise


async def save_cultivating_crop(
    cultivating_crop: CultivatingCrop,
) -> CultivatingCrop:
    cultivating_crop_collection: AsyncIOMotorCollection = get_cultivating_crop_collection()
    try:
        payload = cultivating_crop.model_dump(mode="json", exclude_none=True, by_alias=True)
        await cultivating_crop_collection.replace_one(
            {"_id": cultivating_crop.id}, payload, upsert=True
        )
        response = await cultivating_crop_collection.find_one({"_id": cultivating_crop.id})
        return CultivatingCrop.model_validate(response)
    except Exception:
        raise


async def delete_cultivating_crop(
    cultivating_crop_id: str,
) -> bool:
    cultivating_crop_collection: AsyncIOMotorCollection = get_cultivating_crop_collection()
    try:
        result = await cultivating_crop_collection.delete_one({"_id": cultivating_crop_id})
        return result.deleted_count > 0
    except Exception:
        raise


async def save_intercropping_details(
    intercropping_details: IntercroppingDetails,
) -> IntercroppingDetails:
    intercropping_details_collection: AsyncIOMotorCollection = (
        get_intercropping_details_collection()
    )
    try:
        payload = intercropping_details.model_dump(mode="json", exclude_none=True, by_alias=True)
        await intercropping_details_collection.replace_one(
            {"_id": intercropping_details.id}, payload, upsert=True
        )
        response = await intercropping_details_collection.find_one(
            {"_id": intercropping_details.id}
        )
        return IntercroppingDetails.model_validate(response)
    except Exception:
        raise


async def delete_intercropping_details(
    intercropping_details_id: str,
) -> bool:
    intercropping_details_collection: AsyncIOMotorCollection = (
        get_intercropping_details_collection()
    )
    try:
        result = await intercropping_details_collection.delete_one(
            {"_id": intercropping_details_id}
        )
        return result.deleted_count > 0
    except Exception:
        raise


async def get_intercropping_details_from_id(
    intercropping_details_id: str,
) -> IntercroppingDetails:
    intercropping_details_collection: AsyncIOMotorCollection = (
        get_intercropping_details_collection()
    )
    try:
        response = await intercropping_details_collection.find_one(
            {"_id": intercropping_details_id}
        )
        return IntercroppingDetails.model_validate(response) if response else None
    except Exception:
        raise
