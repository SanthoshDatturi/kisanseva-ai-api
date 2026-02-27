import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from app.collections import cultivating_crop as cultivating_crop_collection
from app.collections.cultivation_calendar import delete_cultivation_calendar_by_crop_id
from app.collections.investment_breakdown import delete_investment_breakdown_by_crop_id
from app.collections.pesticide_recommendation import (
    delete_pesticide_recommendations_by_crop_id,
)
from app.core.security import verify_jwt
from app.models.cultivating_crop import CultivatingCrop, IntercroppingDetails

router = APIRouter(
    prefix="/cultivating-crops",
    tags=["Cultivating Crops"],
    dependencies=[Depends(verify_jwt)],
)


@router.get(
    "/farm/{farm_id}",
    response_model=list[CultivatingCrop],
    response_model_exclude_none=True,
)
async def get_cultivating_crops_by_farm_id(farm_id: str) -> list[CultivatingCrop]:
    """
    Retrieves all cultivating crops for a given farm ID.
    """
    return await cultivating_crop_collection.get_cultivating_crops_from_farm_id(farm_id)


@router.get(
    "/{cultivating_crop_id}",
    response_model=CultivatingCrop,
    response_model_exclude_none=True,
)
async def get_cultivating_crop_by_id(cultivating_crop_id: str) -> CultivatingCrop:
    """
    Retrieves a specific cultivating crop by its ID.
    """
    crop = await cultivating_crop_collection.get_cultivating_crop_from_id(
        cultivating_crop_id
    )
    if not crop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cultivating crop with id {cultivating_crop_id} not found.",
        )
    return crop


@router.delete("/{cultivating_crop_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cultivating_crop(cultivating_crop_id: str):
    """
    Deletes a cultivating crop by its ID and all its associated data, including
    cultivation calendar, investment breakdown, and pesticide recommendations.
    """
    # First, ensure the crop exists. This also fetches the crop details.
    crop_to_delete = await cultivating_crop_collection.get_cultivating_crop_from_id(
        cultivating_crop_id
    )
    if not crop_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cultivating crop with id {cultivating_crop_id} not found.",
        )

    # Concurrently delete all associated data.
    await asyncio.gather(
        delete_cultivation_calendar_by_crop_id(cultivating_crop_id),
        delete_investment_breakdown_by_crop_id(cultivating_crop_id),
        delete_pesticide_recommendations_by_crop_id(cultivating_crop_id),
    )

    # Finally, delete the crop itself.
    await cultivating_crop_collection.delete_cultivating_crop(cultivating_crop_id)
    return None


@router.get(
    "/intercropping/{intercropping_details_id}",
    response_model=IntercroppingDetails,
    response_model_exclude_none=True,
)
async def get_intercropping_details_by_id(
    intercropping_details_id: str,
) -> IntercroppingDetails:
    """
    Retrieves specific intercropping details by its ID.
    """
    details = await cultivating_crop_collection.get_intercropping_details_from_id(
        intercropping_details_id
    )
    if not details:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Intercropping details with id {intercropping_details_id} not found.",
        )
    return details
