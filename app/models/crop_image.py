from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMBEDDING_DIMENSION: int = 512


class CropImageDocument(BaseModel):
    id: str = Field(..., alias="_id", default_factory=lambda: str(uuid4()))
    embedding: List[float]
    image_url: str
    crop_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

    @field_validator("embedding")
    @classmethod
    def validate_embedding(cls, v: List[float]) -> List[float]:
        if len(v) != EMBEDDING_DIMENSION:
            raise ValueError("Embedding dimension mismatch")
        return v

    model_config = ConfigDict(populate_by_name=True)
