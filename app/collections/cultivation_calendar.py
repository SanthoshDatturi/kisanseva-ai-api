from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.core.azure_cosmos_config import get_cultivation_calendar_container
from app.models.cultivation_calendar import CultivationCalendar


async def get_cultivation_calendar_from_id(
    cultivation_calendar_id: str,
) -> CultivationCalendar:
    try:
        container = get_cultivation_calendar_container()
        response = await container.read_item(
            item=cultivation_calendar_id, partition_key=cultivation_calendar_id
        )
        return CultivationCalendar.model_validate(response)
    except CosmosResourceNotFoundError:
        return None
    except Exception as e:
        raise e


async def get_cultivation_calendar_from_crop_id(
    crop_id: str,
) -> CultivationCalendar:
    try:
        container = get_cultivation_calendar_container()
        query = f'SELECT * FROM c WHERE c.crop_id = "{crop_id}"'
        items = container.query_items(query=query)
        async for item in items:
            return CultivationCalendar.model_validate(item)
    except CosmosResourceNotFoundError:
        return None
    except Exception as e:
        raise e


async def save_cultivation_calendar(
    cultivation_calendar: CultivationCalendar,
) -> CultivationCalendar:
    try:
        container = get_cultivation_calendar_container()
        response = await container.upsert_item(
            cultivation_calendar.model_dump(mode="json", exclude_none=True)
        )
        saved_cultivation_calendar = CultivationCalendar.model_validate(response)
        return saved_cultivation_calendar
    except Exception as e:
        raise e


async def delete_cultivation_calendar(cultivation_calendar_id: str) -> bool:
    try:
        container = get_cultivation_calendar_container()
        await container.delete_item(
            item=cultivation_calendar_id, partition_key=cultivation_calendar_id
        )
        return True
    except CosmosResourceNotFoundError:
        return True
    except Exception as e:
        raise e


async def delete_cultivation_calendar_by_crop_id(crop_id: str) -> bool:
    try:
        container = get_cultivation_calendar_container()
        query = "SELECT c.id FROM c WHERE c.crop_id = @crop_id"
        parameters = [{"name": "@crop_id", "value": crop_id}]
        items = container.query_items(query=query, parameters=parameters)
        async for item in items:
            await container.delete_item(item=item["id"], partition_key=item["id"])
        return True
    except CosmosResourceNotFoundError:
        return True
    except Exception as e:
        raise e
