from fastapi import APIRouter, Depends, HTTPException, status

from app.collections.investment_breakdown import (
    delete_investment_breakdown,
    get_investment_breakdown_from_crop_id,
    get_investment_breakdown_from_id,
)
from app.core.security import verify_jwt
from app.models.investment_breakdown import InvestmentBreakdown

router = APIRouter(
    prefix="/investment-breakdowns",
    tags=["Investment Breakdown"],
    dependencies=[Depends(verify_jwt)],
)


@router.get(
    "/{investment_breakdown_id}",
    response_model=InvestmentBreakdown,
    summary="Get an investment breakdown by its ID",
    response_model_exclude_none=True,
)
async def get_breakdown_by_id(investment_breakdown_id: str):
    """
    Retrieve a specific investment breakdown by its unique ID.
    """
    breakdown = await get_investment_breakdown_from_id(investment_breakdown_id)
    if not breakdown:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investment breakdown not found.",
        )
    return breakdown


@router.get(
    "/crop/{crop_id}",
    response_model=InvestmentBreakdown,
    summary="Get an investment breakdown by crop ID",
    response_model_exclude_none=True,
)
async def get_breakdown_by_crop_id(crop_id: str):
    """
    Retrieve the investment breakdown for a specific crop ID.
    """
    breakdown = await get_investment_breakdown_from_crop_id(crop_id)
    if not breakdown:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investment breakdown for crop ID '{crop_id}' not found.",
        )
    return breakdown


@router.delete(
    "/{investment_breakdown_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an investment breakdown",
)
async def delete_breakdown(investment_breakdown_id: str):
    """
    Delete an investment breakdown by its ID. This operation is idempotent.
    """
    await delete_investment_breakdown(investment_breakdown_id)
    return
