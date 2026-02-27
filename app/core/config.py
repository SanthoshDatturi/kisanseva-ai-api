import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    AZURE_STORAGE_CONNECTION_STRING: str = os.environ.get(
        "AZURE_STORAGE_CONNECTION_STRING", ""
    )
    AZURE_STORAGE_USER_CONTENT_CONTAINER_NAME: str = "user-content"
    AZURE_STORAGE_AI_CHAT_CONTAINER_NAME: str = "ai-chat"
    AZURE_STORAGE_SYSTEM_DATA_CONTAINER_NAME: str = "system-data"
    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "")
    MONGO_URI: str = os.environ.get("MONGO_URI", "")
    MONGO_DIRECT_URI: str = os.environ.get("MONGO_DIRECT_URI", "")
    MONGO_DB_NAME: str = "main"


settings = Settings()
