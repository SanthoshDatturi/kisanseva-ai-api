from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.mongodb import get_investment_breakdown_collection
from app.models.investment_breakdown import InvestmentBreakdown


async def get_investment_breakdown_from_id(
    investment_breakdown_id: str,
) -> InvestmentBreakdown:
    try:
        collection: AsyncIOMotorCollection = get_investment_breakdown_collection()
        item_response = await collection.find_one({"_id": investment_breakdown_id})
        return InvestmentBreakdown.model_validate(item_response) if item_response else None
    except Exception as e:
        raise e


async def get_investment_breakdown_from_crop_id(
    crop_id: str,
) -> InvestmentBreakdown:
    try:
        collection: AsyncIOMotorCollection = get_investment_breakdown_collection()
        item = await collection.find_one({"crop_id": crop_id})
        return InvestmentBreakdown.model_validate(item) if item else None
    except Exception as e:
        raise e


async def save_investment_breakdown(
    investment_breakdown: InvestmentBreakdown,
) -> InvestmentBreakdown:
    try:
        collection: AsyncIOMotorCollection = get_investment_breakdown_collection()
        payload = investment_breakdown.model_dump(mode="json", exclude_none=True, by_alias=True)
        await collection.replace_one({"_id": investment_breakdown.id}, payload, upsert=True)
        response = await collection.find_one({"_id": investment_breakdown.id})
        return InvestmentBreakdown.model_validate(response)
    except Exception as e:
        raise e


async def delete_investment_breakdown(investment_breakdown_id: str) -> bool:
    try:
        collection: AsyncIOMotorCollection = get_investment_breakdown_collection()
        await collection.delete_one({"_id": investment_breakdown_id})
        return True
    except Exception as e:
        raise e


async def delete_investment_breakdown_by_crop_id(crop_id: str) -> bool:
    try:
        collection: AsyncIOMotorCollection = get_investment_breakdown_collection()
        await collection.delete_many({"crop_id": crop_id})
        return True
    except Exception as e:
        raise e
