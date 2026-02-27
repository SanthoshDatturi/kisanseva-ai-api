from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, Field


class PesticideStage(str, Enum):
    RECOMMENDED = "recommended"
    SELECTED = "selected"
    APPLIED = "applied"


class PesticideType(str, Enum):
    CHEMICAL = "chemical"
    ORGANIC = "organic"
    BIOLOGICAL = "biological"


class PesticideInfo(BaseModel):
    id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="UUID of the info. Dont give this field",
        validation_alias=AliasChoices("id", "_id"),
        serialization_alias="_id",
    )
    pesticide_name: str = Field(..., description="Name of the recommended pesticide.")
    pesticide_type: PesticideType = Field(
        ..., description="Type of pesticide (e.g., chemical, organic, biological)."
    )
    dosage: str = Field(
        ..., description="Recommended dosage per unit area (e.g., ml/acre)."
    )
    application_method: str = Field(..., description="How to apply the pesticide.")
    precautions: List[str] = Field(
        ..., description="Safety precautions to take during application."
    )
    explanation: str = Field(
        ...,
        description="Justification for recommending this pesticide for the specific pest/disease and crop.",
    )
    rank: int = Field(..., description="Suitability rank of the pesticide (1 = best).")
    stage: PesticideStage = Field(
        default=PesticideStage.RECOMMENDED,
        description="The stage of the pesticide application.",
    )
    applied_date: Optional[datetime] = Field(
        default=None, description="The date when the pesticide was applied."
    )


class PesticideRecommendationResponse(BaseModel):
    id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="UUID of the recommendation. Dont give this field",
        validation_alias=AliasChoices("id", "_id"),
        serialization_alias="_id",
    )
    farm_id: Optional[str] = Field(
        description="UUID of the farm, will be given by backend.",
        default=None,
    )
    crop_id: Optional[str] = Field(
        default=None,
        description="UUID of the crop this recommendation is for, given by backend.",
    )
    timestamp: float = Field(
        description="Timestamp of recommendation generation",
        default_factory=lambda: datetime.now().timestamp(),
    )
    disease_details: str = Field(description="Details about the disease.")
    recommendations: List[PesticideInfo] = Field(
        ...,
        description="List of pesticide recommendations. One for each Pesticide Type (if any type not present give only the type that present).",
    )
    general_advice: str = Field(
        ..., description="General advice for pest management and prevention."
    )


class PesticideRecommendationError(BaseModel):
    """ "Used when AI was unable to identify the disease"""

    reason: str = Field(description="Reason for failure")
    suggest_input_changes: str = Field(
        description=(
            "What can farmer provide more or in different way"
            " so that you will be able to identify the disease e.g. if photo is not showing the"
            " disease properly you can ask to upload again clearly or change the angle"
        )
    )
