import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    AZURE_STORAGE_CONNECTION_STRING: str = os.environ.get(
        "AZURE_STORAGE_CONNECTION_STRING", ""
    )
    COSMOS_ENDPOINT: str = os.environ.get("AZURE_COSMOS_ENDPOINT", "")
    COSMOS_KEY: str = os.environ.get("AZURE_COSMOS_KEY", "")
    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "")


settings = Settings()
