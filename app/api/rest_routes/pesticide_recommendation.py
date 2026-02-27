from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.collections.pesticide_recommendation import (
    delete_pesticide_recommendation,
    get_pesticide_recommendation_from_id,
    get_pesticide_recommendations_from_crop_id,
)
from app.core.security import verify_jwt
from app.models.pesticide_recommendation import (
    PesticideRecommendationResponse,
    PesticideStage,
)
from app.services.pesticide_recommendation_service import update_pesticide_stage

router = APIRouter(
    prefix="/pesticide-recommendations",
    tags=["Pesticide Recommendations"],
    dependencies=[Depends(verify_jwt)],
)


class PesticideStageUpdateRequest(BaseModel):
    pesticide_id: str
    stage: PesticideStage
    applied_date: Optional[datetime] = None


@router.get(
    "/{recommendation_id}",
    response_model=PesticideRecommendationResponse,
    response_model_exclude_none=True,
)
async def get_recommendation_by_id(recommendation_id: str):
    """Get a single pesticide recommendation by its ID."""
    return await get_pesticide_recommendation_from_id(recommendation_id)


@router.get(
    "/crop/{crop_id}",
    response_model=List[PesticideRecommendationResponse],
    response_model_exclude_none=True,
)
async def get_recommendations_by_crop_id(crop_id: str):
    """Get all pesticide recommendations for a given crop ID."""
    return await get_pesticide_recommendations_from_crop_id(crop_id)


@router.delete("/{recommendation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recommendation(recommendation_id: str):
    """Delete a pesticide recommendation by its ID."""
    success = await delete_pesticide_recommendation(recommendation_id)
    if not success:
        # This case is already handled in the collection function, but as a safeguard:
        raise HTTPException(status_code=500, detail="Failed to delete recommendation")
    return


@router.patch("/{recommendation_id}/stage", status_code=status.HTTP_200_OK)
async def update_stage(recommendation_id: str, request: PesticideStageUpdateRequest):
    """Update the stage of a specific pesticide in a recommendation."""
    success = await update_pesticide_stage(
        recommendation_id=recommendation_id,
        pesticide_id=request.pesticide_id,
        stage=request.stage,
        applied_date=request.applied_date,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recommendation or pesticide not found",
        )
    return {"message": "Pesticide stage updated successfully"}
