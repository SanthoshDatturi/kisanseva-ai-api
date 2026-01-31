from typing import Union

from azure.cosmos.container import ContainerProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from fastapi import HTTPException

from app.core.azure_cosmos_config import get_crop_recommendation_container
from app.models.crop_recommendation import (
    CropRecommendationResponse,
    InterCropRecommendation,
    MonoCrop,
)


async def get_crop_recommendation_from_farm_id(
    farm_id: str,
) -> CropRecommendationResponse:
    container: ContainerProxy = get_crop_recommendation_container()
    try:
        query = "SELECT * FROM c WHERE c.farm_id = @farm_id"
        parameters = [{"name": "@farm_id", "value": farm_id}]
        items = container.query_items(query=query, parameters=parameters)
        async for item in items:
            return CropRecommendationResponse.model_validate(item)
        return None
    except CosmosResourceNotFoundError:
        return None
    except Exception as e:
        raise e


async def get_recommended_crop_from_id(
    recommendation_id: str,
    crop_id: str,
) -> Union[MonoCrop, InterCropRecommendation]:
    container: ContainerProxy = get_crop_recommendation_container()
    """
    Fetches a recommended crop from Cosmos DB based on recommendation_id and crop_id.
    
    - For mono crops, crop_id refers to MonoCrop.id
    - For inter crops, crop_id refers to InterCropRecommendation.id
    Returns the matching MonoCrop or InterCropRecommendation object.
    Raises HTTPException(404) if not found.
    """
    try:
        # 1️⃣ Check in mono_crops
        mono_query = """
        SELECT m AS crop
        FROM c
        JOIN m IN c.mono_crops
        WHERE c.id = @recommendation_id AND m.id = @crop_id
        """
        params = [
            {"name": "@recommendation_id", "value": recommendation_id},
            {"name": "@crop_id", "value": crop_id},
        ]
        result = [
            item
            async for item in container.query_items(
                query=mono_query, parameters=params, partition_key=recommendation_id
            )
        ]

        if result:
            return MonoCrop(**result[0]["crop"])

        # 2️⃣ Check in inter_crops (InterCropRecommendation.id)
        inter_query = """
        SELECT i AS inter_crop
        FROM c
        JOIN i IN c.inter_crops
        WHERE c.id = @recommendation_id AND i.id = @crop_id
        """
        result = [
            item
            async for item in container.query_items(
                query=inter_query, parameters=params
            )
        ]

        if result:
            return InterCropRecommendation(**result[0]["inter_crop"])

        # 3️⃣ Not found
        raise HTTPException(
            status_code=404,
            detail=f"Crop with id {crop_id} not found in recommendation {recommendation_id}",
        )

    except CosmosResourceNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Recommendation {recommendation_id} not found"
        )
    except Exception as e:
        raise e


async def get_recommendation_from_id(
    recommendation_id: str,
) -> CropRecommendationResponse:
    container: ContainerProxy = get_crop_recommendation_container()
    try:
        response = await container.read_item(
            item=recommendation_id, partition_key=recommendation_id
        )
        return CropRecommendationResponse.model_validate(response)
    except CosmosResourceNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Recommendation {recommendation_id} not found"
        )
    except Exception as e:
        raise e


async def save_crop_recommendation(
    crop_recommendation: CropRecommendationResponse,
) -> CropRecommendationResponse:
    container: ContainerProxy = get_crop_recommendation_container()
    try:
        response = await container.upsert_item(
            crop_recommendation.model_dump(mode="json", exclude_none=True)
        )
        saved_recommendation = CropRecommendationResponse.model_validate(response)
        return saved_recommendation
    except Exception as e:
        raise e
