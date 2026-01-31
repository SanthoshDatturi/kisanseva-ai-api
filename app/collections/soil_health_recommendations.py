from typing import List

from azure.cosmos.container import ContainerProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from fastapi import HTTPException

from app.core.azure_cosmos_config import get_soil_health_recommendations_container
from app.models.soil_health_recommendations import SoilHealthRecommendations


async def get_soil_health_recommendations_from_id(
    soil_health_recommendations_id: str,
) -> SoilHealthRecommendations:
    container: ContainerProxy = get_soil_health_recommendations_container()
    try:
        response = await container.read_item(
            item=soil_health_recommendations_id,
            partition_key=soil_health_recommendations_id,
        )
        return SoilHealthRecommendations.model_validate(response)
    except CosmosResourceNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Soil health recommendation {soil_health_recommendations_id} not found",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def save_soil_health_recommendations(
    soil_health_recommendations: SoilHealthRecommendations,
) -> SoilHealthRecommendations:
    container: ContainerProxy = get_soil_health_recommendations_container()
    try:
        response = await container.upsert_item(
            soil_health_recommendations.model_dump(exclude_none=True)
        )
        return SoilHealthRecommendations.model_validate(response)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error saving soil health recommendation: {e}"
        )


async def get_soil_health_recommendations_from_crop_id(
    crop_id: str,
) -> List[SoilHealthRecommendations]:
    container: ContainerProxy = get_soil_health_recommendations_container()
    try:
        query = "SELECT * FROM c WHERE c.crop_id = @crop_id"
        parameters = [{"name": "@crop_id", "value": crop_id}]
        items = container.query_items(query=query, parameters=parameters)
        return [SoilHealthRecommendations.model_validate(item) async for item in items]
    except CosmosResourceNotFoundError:
        # This exception is unlikely here, but good to handle.
        # A query that returns no items is not an error.
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def delete_soil_health_recommendations(
    soil_health_recommendations_id: str,
) -> bool:
    container: ContainerProxy = get_soil_health_recommendations_container()
    try:
        await container.delete_item(
            item=soil_health_recommendations_id,
            partition_key=soil_health_recommendations_id,
        )
        return True
    except CosmosResourceNotFoundError:
        # If the item is not found, it's already deleted. This is a success.
        return True
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error deleting recommendation: {e}"
        )
