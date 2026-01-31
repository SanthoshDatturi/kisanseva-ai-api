from azure.cosmos.container import ContainerProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.core.azure_cosmos_config import (
    get_cultivating_crop_container,
    get_intercropping_details_container,
)
from app.models.cultivating_crop import CultivatingCrop, IntercroppingDetails


async def get_cultivating_crop_from_id(
    cultivating_crop_id: str,
) -> CultivatingCrop:
    cultivating_crop_container: ContainerProxy = get_cultivating_crop_container()
    try:
        response = await cultivating_crop_container.read_item(
            item=cultivating_crop_id, partition_key=cultivating_crop_id
        )
        return CultivatingCrop.model_validate(response)
    except CosmosResourceNotFoundError:
        return None
    except Exception:
        raise


async def get_cultivating_crops_from_farm_id(
    farm_id: str,
) -> list[CultivatingCrop]:
    cultivating_crop_container: ContainerProxy = get_cultivating_crop_container()
    query = "SELECT * FROM c WHERE c.farm_id = @farm_id"
    parameters = [{"name": "@farm_id", "value": farm_id}]
    cultivating_crops: list[CultivatingCrop] = []
    try:
        items = cultivating_crop_container.query_items(
            query=query, parameters=parameters
        )
        async for item in items:
            cultivating_crops.append(CultivatingCrop.model_validate(item))
        return cultivating_crops
    except Exception:
        raise


async def save_cultivating_crop(
    cultivating_crop: CultivatingCrop,
) -> CultivatingCrop:
    cultivating_crop_container: ContainerProxy = get_cultivating_crop_container()
    try:
        response = await cultivating_crop_container.upsert_item(
            body=cultivating_crop.model_dump(exclude_none=True)
        )
        return CultivatingCrop.model_validate(response)
    except Exception:
        raise


async def delete_cultivating_crop(
    cultivating_crop_id: str,
) -> bool:
    cultivating_crop_container: ContainerProxy = get_cultivating_crop_container()
    try:
        await cultivating_crop_container.delete_item(
            item=cultivating_crop_id, partition_key=cultivating_crop_id
        )
        return True
    except CosmosResourceNotFoundError:
        return False
    except Exception:
        raise


async def save_intercropping_details(
    intercropping_details: IntercroppingDetails,
) -> IntercroppingDetails:
    intercropping_details_container: ContainerProxy = (
        get_intercropping_details_container()
    )
    try:
        response = await intercropping_details_container.upsert_item(
            body=intercropping_details.model_dump(exclude_none=True)
        )
        return IntercroppingDetails.model_validate(response)
    except Exception:
        raise


async def delete_intercropping_details(
    intercropping_details_id: str,
) -> bool:
    intercropping_details_container: ContainerProxy = (
        get_intercropping_details_container()
    )
    try:
        await intercropping_details_container.delete_item(
            item=intercropping_details_id, partition_key=intercropping_details_id
        )
        return True
    except CosmosResourceNotFoundError:
        return False
    except Exception:
        raise


async def get_intercropping_details_from_id(
    intercropping_details_id: str,
) -> IntercroppingDetails:
    intercropping_details_container: ContainerProxy = (
        get_intercropping_details_container()
    )
    try:
        response = await intercropping_details_container.read_item(
            item=intercropping_details_id, partition_key=intercropping_details_id
        )
        return IntercroppingDetails.model_validate(response)
    except CosmosResourceNotFoundError:
        return None
    except Exception:
        raise
