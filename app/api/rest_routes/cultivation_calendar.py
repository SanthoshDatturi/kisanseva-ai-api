from fastapi import APIRouter, Depends, HTTPException, status

from app.collections.cultivation_calendar import (
    delete_cultivation_calendar,
    get_cultivation_calendar_from_crop_id,
    get_cultivation_calendar_from_id,
)
from app.core.security import verify_jwt
from app.models.cultivation_calendar import CultivationCalendar

router = APIRouter(
    prefix="/cultivation-calendars",
    tags=["Cultivation Calendar"],
    dependencies=[Depends(verify_jwt)],
)


@router.get(
    "/{cultivation_calendar_id}",
    response_model=CultivationCalendar,
    summary="Get a cultivation calendar by its ID",
    response_model_exclude_none=True,
)
async def get_calendar_by_id(cultivation_calendar_id: str):
    """
    Retrieve a specific cultivation calendar by its unique ID.
    """
    calendar = await get_cultivation_calendar_from_id(cultivation_calendar_id)
    if not calendar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cultivation calendar not found.",
        )
    return calendar


@router.get(
    "/crop/{crop_id}",
    response_model=CultivationCalendar,
    summary="Get a cultivation calendar by crop ID",
    response_model_exclude_none=True,
)
async def get_calendar_by_crop_id(crop_id: str):
    """
    Retrieve the cultivation calendar for a specific crop ID.
    Note: This assumes a one-to-one relationship between a crop and a calendar.
    """
    calendar = await get_cultivation_calendar_from_crop_id(crop_id)
    if not calendar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cultivation calendar for crop ID '{crop_id}' not found.",
        )
    return calendar


@router.delete(
    "/{cultivation_calendar_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a cultivation calendar",
)
async def delete_calendar(cultivation_calendar_id: str):
    """
    Delete a cultivation calendar by its ID. This operation is idempotent.
    """
    await delete_cultivation_calendar(cultivation_calendar_id)
    return
