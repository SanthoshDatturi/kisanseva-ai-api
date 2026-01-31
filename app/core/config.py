import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    AZURE_STORAGE_CONNECTION_STRING: str = os.environ.get(
        "AZURE_STORAGE_CONNECTION_STRING", ""
    )
    AZURE_STORAGE_AUDIO_CONTAINER_NAME: str = "audio"
    AZURE_STORAGE_IMAGE_CONTAINER_NAME: str = "images"
    COSMOS_ENDPOINT: str = os.environ.get("AZURE_COSMOS_ENDPOINT", "")
    COSMOS_KEY: str = os.environ.get("AZURE_COSMOS_KEY", "")
    UNSPLASH_ACCESS_KEY: str = os.environ.get("UNSPLASH_ACCESS_KEY", "")
    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "")
    HUGGINGFACE_API_KEY: str = os.environ.get("HUGGINGFACE_API_KEY", "")
    HUGGINGFACE_API_URL: str = os.environ.get("HUGGINGFACE_API_URL", "")


settings = Settings()
