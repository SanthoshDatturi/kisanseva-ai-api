from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.mongodb import get_cultivation_calendar_collection
from app.models.cultivation_calendar import CultivationCalendar


async def get_cultivation_calendar_from_id(
    cultivation_calendar_id: str,
) -> CultivationCalendar:
    try:
        collection: AsyncIOMotorCollection = get_cultivation_calendar_collection()
        response = await collection.find_one({"_id": cultivation_calendar_id})
        return CultivationCalendar.model_validate(response) if response else None
    except Exception as e:
        raise e


async def get_cultivation_calendar_from_crop_id(
    crop_id: str,
) -> CultivationCalendar:
    try:
        collection: AsyncIOMotorCollection = get_cultivation_calendar_collection()
        item = await collection.find_one({"crop_id": crop_id})
        return CultivationCalendar.model_validate(item) if item else None
    except Exception as e:
        raise e


async def save_cultivation_calendar(
    cultivation_calendar: CultivationCalendar,
) -> CultivationCalendar:
    try:
        collection: AsyncIOMotorCollection = get_cultivation_calendar_collection()
        payload = cultivation_calendar.model_dump(mode="json", exclude_none=True, by_alias=True)
        await collection.replace_one({"_id": cultivation_calendar.id}, payload, upsert=True)
        response = await collection.find_one({"_id": cultivation_calendar.id})
        return CultivationCalendar.model_validate(response)
    except Exception as e:
        raise e


async def delete_cultivation_calendar(cultivation_calendar_id: str) -> bool:
    try:
        collection: AsyncIOMotorCollection = get_cultivation_calendar_collection()
        await collection.delete_one({"_id": cultivation_calendar_id})
        return True
    except Exception as e:
        raise e


async def delete_cultivation_calendar_by_crop_id(crop_id: str) -> bool:
    try:
        collection: AsyncIOMotorCollection = get_cultivation_calendar_collection()
        await collection.delete_many({"crop_id": crop_id})
        return True
    except Exception as e:
        raise e
