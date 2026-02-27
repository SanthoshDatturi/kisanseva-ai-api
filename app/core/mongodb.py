from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.core.config import settings

_client: AsyncIOMotorClient = None
_database: AsyncIOMotorDatabase = None


async def init_mongo_client() -> None:
    global _client, _database
    if _client is None:
        mongo_uri = settings.MONGO_DIRECT_URI or settings.MONGO_URI
        _client = AsyncIOMotorClient(mongo_uri, uuidRepresentation="standard")
    if _database is None:
        _database = _client[settings.MONGO_DB_NAME]


async def close_mongo_client() -> None:
    global _client, _database
    if _client is not None:
        _client.close()
    _client = None
    _database = None


def _get_collection(collection_name: str) -> AsyncIOMotorCollection:
    global _client, _database
    if _client is None:
        mongo_uri = settings.MONGO_DIRECT_URI or settings.MONGO_URI
        _client = AsyncIOMotorClient(mongo_uri, uuidRepresentation="standard")
    if _database is None:
        _database = _client[settings.MONGO_DB_NAME]
    return _database[collection_name]


def get_user_collection() -> AsyncIOMotorCollection:
    return _get_collection("user")


def get_farm_profile_collection() -> AsyncIOMotorCollection:
    return _get_collection("farm_profile")


def get_user_language_farm_profile_collection() -> AsyncIOMotorCollection:
    return _get_collection("user_language_farm_profile")


def get_crop_recommendation_collection() -> AsyncIOMotorCollection:
    return _get_collection("crop_recommendation_response")


def get_chat_session_collection() -> AsyncIOMotorCollection:
    return _get_collection("chat_session")


def get_message_collection() -> AsyncIOMotorCollection:
    return _get_collection("messages")


def get_cultivation_calendar_collection() -> AsyncIOMotorCollection:
    return _get_collection("cultivation_calendar")


def get_investment_breakdown_collection() -> AsyncIOMotorCollection:
    return _get_collection("investment_breakdown")


def get_soil_health_recommendations_collection() -> AsyncIOMotorCollection:
    return _get_collection("soil_health_recommendations")


def get_cultivating_crop_collection() -> AsyncIOMotorCollection:
    return _get_collection("cultivating_crop")


def get_intercropping_details_collection() -> AsyncIOMotorCollection:
    return _get_collection("intercropping_details")


def get_pesticide_recommendation_collection() -> AsyncIOMotorCollection:
    return _get_collection("pesticide_recommendation")


def get_crop_image_collection() -> AsyncIOMotorCollection:
    return _get_collection("crop_images")
