from enum import Enum
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, Field


class UserRole(str, Enum):
    FARMER = "farmer"
    ADMIN = "admin"


class User(BaseModel):
    id: str = Field(
        default_factory=lambda: uuid4().hex,
        validation_alias=AliasChoices("id", "_id"),
        serialization_alias="_id",
    )
    phone: str = Field(...)
    name: str = Field(...)
    language: str = Field(...)
    role: str = Field(default=UserRole.FARMER)
    is_verified: bool = Field(default=False)
