from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.mongodb import get_user_collection
from app.models.user import User


async def get_user_from_id(
    user_id: str,
) -> User:
    user_collection: AsyncIOMotorCollection = get_user_collection()
    try:
        response = await user_collection.find_one({"_id": user_id})
        return User.model_validate(response) if response else None
    except Exception:
        raise


async def get_user_from_phone(phone: str) -> User:
    user_collection: AsyncIOMotorCollection = get_user_collection()
    try:
        item = await user_collection.find_one({"phone": phone})
        return User.model_validate(item) if item else None
    except Exception:
        raise


async def save_user(
    user: User,
) -> User:
    user_collection: AsyncIOMotorCollection = get_user_collection()
    try:
        payload = user.model_dump(mode="json", exclude_none=True, by_alias=True)
        await user_collection.replace_one({"_id": user.id}, payload, upsert=True)
        response = await user_collection.find_one({"_id": user.id})
        return User.model_validate(response)
    except Exception:
        raise


async def delete_user(
    user_id: str,
) -> bool:
    user_collection: AsyncIOMotorCollection = get_user_collection()
    try:
        await user_collection.delete_one({"_id": user_id})
        return True
    except Exception:
        raise
