from uuid import uuid4
from pydantic import AliasChoices, BaseModel, Field
from typing import List


class ImmediateAction(BaseModel):
    """Defines a specific, immediate action to improve soil health."""

    parameter: str = Field(description="The soil issue that needs to be addressed.")
    recommendation: str = Field(description="The recommended action to take.")
    product: str = Field(
        description="A specific product recommended to address the issue."
    )
    cost: str = Field(description="The approximate cost of the product or action.")


class SoilHealthRecommendations(BaseModel):
    """Provides a set of recommendations for improving soil health."""

    id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="Unique identifier for the soil health recommendation, AI should ignore, given by system.",
        validation_alias=AliasChoices("id", "_id"),
        serialization_alias="_id",
    )
    crop_id: str = Field(
        description="Crop ID for which this is recommended, either single or intercrop."
    )
    immediate_actions: List[ImmediateAction] = Field(
        description="Actions to be taken immediately for soil improvement."
    )
    description: str = Field(
        description="A farmer-friendly explanation of the immediate actions."
    )
    long_term_improvements: List[str] = Field(
        description="A list of practices for long-term soil health improvement."
    )
