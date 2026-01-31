from azure.cosmos.container import ContainerProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.core.azure_cosmos_config import get_user_language_farm_profile_container as get_farm_profile_container
from app.models.farm_profile import FarmProfile


async def get_farm_profile_from_id(farm_id: str) -> FarmProfile:
    farm_profile_container: ContainerProxy = get_farm_profile_container()
    try:
        print(farm_id)
        response = await farm_profile_container.read_item(
            item=farm_id, partition_key=farm_id
        )
        return FarmProfile.model_validate(response)
    except CosmosResourceNotFoundError:
        return None
    except Exception:
        raise


async def get_farm_profiles_from_user_id(user_id: str) -> list[FarmProfile]:
    farm_profile_container: ContainerProxy = get_farm_profile_container()
    query = "SELECT * FROM c WHERE c.farmer_id = @farmer_id"
    parameters = [{"name": "@farmer_id", "value": user_id}]
    try:
        items = farm_profile_container.query_items(query=query, parameters=parameters)
        farm_profiles = [FarmProfile.model_validate(item) async for item in items]
        return farm_profiles
    except CosmosResourceNotFoundError:
        return []  # Return an empty list if the container is not found, though unlikely for a query.
    except Exception:
        raise


async def save_farm_profile(farm_profile: FarmProfile) -> FarmProfile:
    farm_profile_container: ContainerProxy = get_farm_profile_container()
    try:
        response = await farm_profile_container.upsert_item(
            body=farm_profile.model_dump()
        )
        return FarmProfile.model_validate(response)
    except Exception:
        raise


async def delete_farm_profile(farm_id: str) -> bool:
    farm_profile_container: ContainerProxy = get_farm_profile_container()
    try:
        await farm_profile_container.delete_item(item=farm_id, partition_key=farm_id)
        return True
    except CosmosResourceNotFoundError:
        return True
    except Exception:
        raise
