import asyncio
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from pymongo.collection import Collection

from app.core.genai_client import get_embeddings_model
from app.core.mongodb import get_crop_image_collection
from app.models.crop_image import EMBEDDING_DIMENSION, CropImageDocument


async def insert_crop_document(document: CropImageDocument) -> None:

    collection = get_crop_image_collection()

    await collection.insert_one(document.model_dump(by_alias=True))


async def insert_crop_documents(documents: List[CropImageDocument]) -> None:
    collection = get_crop_image_collection()
    if not documents:
        return
    await collection.insert_many([doc.model_dump(by_alias=True) for doc in documents])


class VectorImageSearchResult(BaseModel):
    id: Optional[str] = Field(alias="_id")
    crop_name: str
    image_url: str
    embedding: Optional[List[float]] = Field(default=None)
    created_at: Optional[datetime] = Field(default=None)


async def vector_image_search(
    query_embedding: List[float],
    limit: int = 1,
    num_candidates: int = 100,
    projection: Dict[str, int] = {
        "_id": 1,
        "crop_name": 1,
        "image_url": 1,
        "created_at": 1,
    },
) -> List[Dict]:
    """
    Performs vector similarity search.
    Returns matching documents.
    """
    if len(query_embedding) != EMBEDDING_DIMENSION:
        raise ValueError("Query embedding dimension mismatch")

    collection: Collection = get_crop_image_collection()

    pipeline = [
        {
            "$vectorSearch": {
                "queryVector": query_embedding,
                "path": "embedding",
                "numCandidates": num_candidates,
                "limit": limit,
            }
        },
        {"$project": projection},
    ]

    cursor = collection.aggregate(pipeline)

    results = []
    async for doc in cursor:
        results.append(doc)

    return results


async def get_crop_images_by_name(crop_name: str) -> List[VectorImageSearchResult]:
    embeddings = get_embeddings_model(model="gemini-embedding-001")

    query_embedding = await embeddings.aembed_query(
        crop_name,
        task_type="SEMANTIC_SIMILARITY",
        output_dimensionality=EMBEDDING_DIMENSION,
    )

    search_results = await vector_image_search(query_embedding=query_embedding, limit=3)

    return [VectorImageSearchResult.model_validate(result) for result in search_results]


async def get_crop_image_urls_by_crop_names(
    crop_names: List[str],
) -> Dict[str, Optional[str]]:
    """Retrieves crop image URLs for a list of crop names.

    Generates embeddings for the provided crop names and performs a vector search
    to find matching crop images.

    Args:
        crop_names: A list of crop names to search for.

    Returns:
        A dictionary where keys are crop names and values are image URLs.
        If no image is found for a crop name, the value will be None.
    """
    if not crop_names:
        return {}

    embeddings = get_embeddings_model(model="gemini-embedding-001")
    query_embeddings = await embeddings.aembed_documents(
        crop_names,
        task_type="SEMANTIC_SIMILARITY",
        output_dimensionality=EMBEDDING_DIMENSION,
    )

    vector_search_tasks = [
        vector_image_search(
            query_embedding=emb,
            limit=1,
            projection={
                "crop_name": 1,
                "image_url": 1,
            },
        )
        for emb in query_embeddings
    ]

    all_search_results = await asyncio.gather(*vector_search_tasks)

    crop_image_urls = {}

    for crop_name, search_results in zip(crop_names, all_search_results):
        if search_results:
            crop_image_urls[crop_name] = search_results[0]["image_url"]
        else:
            crop_image_urls[crop_name] = None

    return crop_image_urls
