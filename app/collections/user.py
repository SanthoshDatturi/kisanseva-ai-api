from azure.cosmos.container import ContainerProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.core.azure_cosmos_config import get_user_container
from app.models.user import User


async def get_user_from_id(
    user_id: str,
) -> User:
    user_container: ContainerProxy = get_user_container()
    try:
        response = await user_container.read_item(item=user_id, partition_key=user_id)
        return User.model_validate(response)
    except CosmosResourceNotFoundError:
        return None
    except Exception:
        raise


async def get_user_from_phone(phone: str) -> User:
    user_container: ContainerProxy = get_user_container()
    try:
        query = "SELECT * FROM c WHERE c.phone = @phone"
        params = [{"name": "@phone", "value": phone}]
        async for item in user_container.query_items(
            query=query, parameters=params, max_item_count=1
        ):
            # Since phone is unique, we can return the first item found.
            return User.model_validate(item)
        return None  # Return None if the loop completes without finding a user.
    except CosmosResourceNotFoundError:
        return None
    except Exception:
        raise


async def save_user(
    user: User,
) -> User:
    user_container: ContainerProxy = get_user_container()
    try:
        response = await user_container.upsert_item(body=user.model_dump())
        return User.model_validate(response)
    except Exception:
        raise


async def delete_user(
    user_id: str,
) -> bool:
    user_container: ContainerProxy = get_user_container()
    try:
        await user_container.delete_item(item=user_id, partition_key=user_id)
        return True
    except CosmosResourceNotFoundError:
        # Item not found is not an error in a delete operation, it's already gone.
        return True
    except Exception:
        raise
