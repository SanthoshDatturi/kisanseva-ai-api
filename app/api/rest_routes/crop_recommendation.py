from fastapi import APIRouter, Depends, HTTPException, status

from app.collections import crop_recommendation as crop_recommendation_collection
from app.core.security import verify_jwt
from app.models.crop_recommendation import (
    CropRecommendationResponse,
)

router = APIRouter(
    prefix="/crop-recommendations",
    tags=["Crop Recommendation"],
    dependencies=[Depends(verify_jwt)],
)


@router.get(
    "/farm/{farm_id}",
    response_model=CropRecommendationResponse,
    response_model_exclude_none=True,
)
async def get_crop_recommendation_by_farm_id(
    farm_id: str,
) -> CropRecommendationResponse:
    """
    Retrieves crop recommendations for a given farm ID.
    """
    response = await crop_recommendation_collection.get_crop_recommendation_from_farm_id(
        farm_id
    )
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No crop recommendation found for farm {farm_id}.",
        )
    return response


@router.get(
    "/{recommendation_id}",
    response_model=CropRecommendationResponse,
    response_model_exclude_none=True,
)
async def get_crop_recommendation_by_id(
    recommendation_id: str,
) -> CropRecommendationResponse:
    """
    Retrieves a specific crop recommendation by its ID.
    """
    response = await crop_recommendation_collection.get_recommendation_from_id(
        recommendation_id
    )
    return response
