from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.collections.soil_health_recommendations import (
    delete_soil_health_recommendations,
    get_soil_health_recommendations_from_crop_id,
    get_soil_health_recommendations_from_id,
)
from app.core.security import verify_jwt
from app.models.soil_health_recommendations import SoilHealthRecommendations

router = APIRouter(
    prefix="/soil-health-recommendations",
    tags=["Soil Health Recommendations"],
    dependencies=[Depends(verify_jwt)],
)


@router.get(
    "/{recommendation_id}",
    response_model=SoilHealthRecommendations,
    response_model_exclude_none=True,
)
async def get_recommendation_by_id(recommendation_id: str):
    """Get a single soil health recommendation by its ID."""
    return await get_soil_health_recommendations_from_id(recommendation_id)


@router.get(
    "/crop/{crop_id}",
    response_model=List[SoilHealthRecommendations],
    response_model_exclude_none=True,
)
async def get_recommendations_by_crop_id(crop_id: str):
    """Get all soil health recommendations for a given crop ID."""
    return await get_soil_health_recommendations_from_crop_id(crop_id)


@router.delete("/{recommendation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recommendation(recommendation_id: str):
    """Delete a soil health recommendation by its ID."""
    success = await delete_soil_health_recommendations(recommendation_id)
    if not success:
        # This case is already handled in the collection function, but as a safeguard:
        raise HTTPException(
            status_code=500, detail="Failed to delete soil health recommendation"
        )
    return
