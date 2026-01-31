from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    FARMER = "farmer"


class User(BaseModel):
    id: str = Field(default=uuid4().hex)
    phone: str = Field(...)
    name: str = Field(...)
    language: str = Field(...)
    role: str = Field(default=UserRole.FARMER)
    is_verified: bool = Field(default=False)
