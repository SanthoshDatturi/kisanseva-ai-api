from datetime import datetime
from typing import List, Optional

from azure.cosmos.container import ContainerProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from fastapi import HTTPException

from app.core.azure_cosmos_config import get_pesticide_recommendation_container
from app.models.pesticide_recommendation import (
    PesticideRecommendationResponse,
    PesticideStage,
)


async def save_pesticide_recommendation(
    recommendation: PesticideRecommendationResponse,
) -> PesticideRecommendationResponse:
    container: ContainerProxy = get_pesticide_recommendation_container()
    try:
        response = await container.upsert_item(
            body=recommendation.model_dump(mode="json", exclude_none=True)
        )
        return PesticideRecommendationResponse.model_validate(response)
    except Exception:
        # Consider logging the exception for debugging purposes
        raise HTTPException(
            status_code=500, detail="Error saving pesticide recommendation"
        )


async def get_pesticide_recommendation_from_id(
    recommendation_id: str,
) -> PesticideRecommendationResponse:
    container: ContainerProxy = get_pesticide_recommendation_container()
    try:
        response = await container.read_item(
            item=recommendation_id, partition_key=recommendation_id
        )
        return PesticideRecommendationResponse.model_validate(response)
    except CosmosResourceNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Recommendation {recommendation_id} not found"
        )


async def get_pesticide_recommendations_from_crop_id(
    crop_id: str,
) -> List[PesticideRecommendationResponse]:
    container: ContainerProxy = get_pesticide_recommendation_container()
    try:
        items = container.query_items(
            query="SELECT * FROM c WHERE c.crop_id = @crop_id",
            parameters=[{"name": "@crop_id", "value": crop_id}],
        )
        return [
            PesticideRecommendationResponse.model_validate(item) async for item in items
        ]
    except CosmosResourceNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Recommendation {crop_id} not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error getting pesticide recommendations: {e}"
        )


async def delete_pesticide_recommendation(
    recommendation_id: str,
) -> bool:
    container: ContainerProxy = get_pesticide_recommendation_container()
    try:
        await container.delete_item(
            item=recommendation_id, partition_key=recommendation_id
        )
        return True
    except CosmosResourceNotFoundError:
        # If it's not found, it's already deleted. This is not an error.
        return True
    except Exception:
        # For other exceptions, it's better to let them bubble up or log them
        # and raise a 500 error, rather than returning False.
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting pesticide recommendation {recommendation_id}",
        )


async def delete_pesticide_recommendations_by_crop_id(crop_id: str) -> bool:
    """Deletes all pesticide recommendations associated with a crop_id."""
    container: ContainerProxy = get_pesticide_recommendation_container()
    try:
        # Find all documents with the given crop_id
        items_to_delete = container.query_items(
            query="SELECT c.id FROM c WHERE c.crop_id = @crop_id",
            parameters=[{"name": "@crop_id", "value": crop_id}],
            enable_cross_partition_query=True,
        )
        # The SDK does not support bulk delete directly, so we iterate.
        # This is acceptable for a small number of recommendations per crop.
        async for item in items_to_delete:
            await container.delete_item(item=item["id"], partition_key=item["id"])
        return True
    except Exception:
        # If any error occurs, it's better to raise a 500.
        # The transaction is not atomic, so some items might be left behind.
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting pesticide recommendations for crop {crop_id}",
        )


async def update_pesticide_stage_in_db(
    recommendation_id: str,
    pesticide_id: str,
    stage: PesticideStage,
    applied_date: Optional[datetime] = None,
) -> bool:
    container: ContainerProxy = get_pesticide_recommendation_container()
    try:
        item = await container.read_item(
            item=recommendation_id, partition_key=recommendation_id
        )
        recommendation = PesticideRecommendationResponse.model_validate(item)

        updated = False
        for pesticide in recommendation.recommendations:
            if pesticide.id == pesticide_id:
                pesticide.stage = stage
                pesticide.applied_date = applied_date
                updated = True
                break

        if updated:
            await container.upsert_item(
                body=recommendation.model_dump(mode="json", exclude_none=True)
            )
            return True
        return False
    except CosmosResourceNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Recommendation {recommendation_id} not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error updating pesticide stage: {e}"
        )
