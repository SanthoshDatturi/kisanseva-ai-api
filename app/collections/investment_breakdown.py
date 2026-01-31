from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.core.azure_cosmos_config import get_investment_breakdown_container
from app.models.investment_breakdown import InvestmentBreakdown


async def get_investment_breakdown_from_id(
    investment_breakdown_id: str,
) -> InvestmentBreakdown:
    try:
        container = get_investment_breakdown_container()
        item_response = await container.read_item(
            item=investment_breakdown_id, partition_key=investment_breakdown_id
        )
        return InvestmentBreakdown.model_validate(item_response)
    except CosmosResourceNotFoundError:
        return None
    except Exception as e:
        raise e


async def get_investment_breakdown_from_crop_id(
    crop_id: str,
) -> InvestmentBreakdown:
    try:
        container = get_investment_breakdown_container()
        query = "SELECT * FROM c WHERE c.crop_id = @crop_id"
        parameters = [{"name": "@crop_id", "value": crop_id}]
        items = container.query_items(query=query, parameters=parameters)
        async for item in items:
            return InvestmentBreakdown.model_validate(item)
    except CosmosResourceNotFoundError:
        return None
    except Exception as e:
        raise e


async def save_investment_breakdown(
    investment_breakdown: InvestmentBreakdown,
) -> InvestmentBreakdown:
    try:
        container = get_investment_breakdown_container()
        response = await container.upsert_item(
            investment_breakdown.model_dump(exclude_none=True)
        )
        return InvestmentBreakdown.model_validate(response)
    except Exception as e:
        raise e


async def delete_investment_breakdown(investment_breakdown_id: str) -> bool:
    try:
        container = get_investment_breakdown_container()
        await container.delete_item(
            item=investment_breakdown_id, partition_key=investment_breakdown_id
        )
        return True
    except CosmosResourceNotFoundError:
        return True
    except Exception as e:
        raise e


async def delete_investment_breakdown_by_crop_id(crop_id: str) -> bool:
    try:
        container = get_investment_breakdown_container()
        query = "SELECT * FROM c WHERE c.crop_id = @crop_id"
        parameters = [{"name": "@crop_id", "value": crop_id}]
        items = container.query_items(query=query, parameters=parameters)
        async for item in items:
            await container.delete_item(item=item["id"], partition_key=item["id"])
        return True
    except Exception as e:
        raise e
