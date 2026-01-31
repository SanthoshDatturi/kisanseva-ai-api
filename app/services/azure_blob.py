from azure.storage.blob.aio import BlobServiceClient, ContainerClient
from functools import lru_cache
from app.core.config import settings


@lru_cache()
def get_blob_service_client() -> BlobServiceClient:
    """
    Returns a BlobServiceClient using the connection string from settings.
    Uses lru_cache to return a cached client instance.
    """
    if not settings.AZURE_STORAGE_CONNECTION_STRING:
        raise ValueError(
            "AZURE_STORAGE_CONNECTION_STRING environment variable not set."
        )
    return BlobServiceClient.from_connection_string(
        settings.AZURE_STORAGE_CONNECTION_STRING
    )


async def get_container_client(container_name: str) -> ContainerClient:
    """
    Returns a ContainerClient for the specified container.
    Creates the container if it does not exist.
    """
    blob_service_client = get_blob_service_client()
    container_client = blob_service_client.get_container_client(container_name)
    if not await container_client.exists():
        await container_client.create_container()
    return container_client


async def get_audio_container_client() -> ContainerClient:
    """Returns a client for the 'audio' blob container."""
    return await get_container_client(settings.AZURE_STORAGE_AUDIO_CONTAINER_NAME)


async def get_image_container_client() -> ContainerClient:
    """Returns a client for the 'images' blob container."""
    return await get_container_client(settings.AZURE_STORAGE_IMAGE_CONTAINER_NAME)
