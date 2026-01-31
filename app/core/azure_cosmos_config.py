from typing import Optional

from azure.cosmos.aio import CosmosClient

from app.core.config import settings

DATABASE_NAME = "kisan-mithra-primary"


_cosmos_client: Optional[CosmosClient] = None
_database = None


async def init_cosmos_client() -> None:
    """
    Initializes the CosmosClient once during application startup.
    This follows the Singleton pattern to ensure only one instance exists.
    """
    global _cosmos_client, _database

    if _cosmos_client is None:
        _cosmos_client = CosmosClient(settings.COSMOS_ENDPOINT, settings.COSMOS_KEY)
        _database = _cosmos_client.get_database_client(DATABASE_NAME)
        print("✅ CosmosClient initialized successfully.")


def get_user_container():
    return _database.get_container_client("user")


def get_farm_profile_container():
    return _database.get_container_client("farm_profile")

def get_user_language_farm_profile_container():
    return _database.get_container_client("user_language_farm_profile")

def get_crop_recommendation_container():
    return _database.get_container_client("crop_recommendation_response")


def get_chat_session_container():
    return _database.get_container_client("chat_session")


def get_message_container():
    return _database.get_container_client("messages")


def get_cultivation_calendar_container():
    return _database.get_container_client("cultivation_calendar")


def get_investment_breakdown_container():
    return _database.get_container_client("investment_breakdown")


def get_soil_health_recommendations_container():
    return _database.get_container_client("soil_health_recommendations")


def get_cultivating_crop_container():
    return _database.get_container_client("cultivating_crop")


def get_intercropping_details_container():
    return _database.get_container_client("intercropping_details")


def get_pesticide_recommendation_container():
    return _database.get_container_client("pesticide_recommendation")


async def close_cosmos_client() -> None:
    """
    Cleans up CosmosClient references during shutdown.
    """
    global _cosmos_client, _database
    if _cosmos_client:
        await _cosmos_client.close()
    _cosmos_client = None
    _database = None
    print("🛑 CosmosClient connection closed.")
