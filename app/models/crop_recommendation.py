from datetime import date, datetime
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, Field, model_validator

from .cultivating_crop import SpecificArrangement
from .cultivation_calendar import CultivationCalendar
from .investment_breakdown import InvestmentBreakdown
from .soil_health_recommendations import SoilHealthRecommendations

RECOMMENDATION_VALIDITY_DAYS = 7


class SowingWindow(BaseModel):
    start_date: date
    end_date: date
    optimal_date: date


class FinancialForecasting(BaseModel):
    total_estimated_investment: str = Field(description="e.g. '₹15,000 per acre'")
    market_price_current: str = Field(description="e.g. '₹5,500 per quintal'")
    price_trend: str = Field(description="e.g. 'Increasing (+8% in 3 months)'")
    total_revenue_estimate: str = Field(description="e.g. '₹1,10,000 for 2 acres'")


class RiskImpact(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskFactor(BaseModel):
    risk: str = Field(description="Identified risk")
    probability: float = Field(ge=0, le=1, description="Probability of risk, 0-1")
    impact: RiskImpact
    mitigation: str = Field(description="Simple prevention tip")


class MonoCrop(BaseModel):
    """Describes a single crop recommendation."""

    id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="UUID of the crop, will be given by backend, don't produce it at time of recommendation.",
        validation_alias=AliasChoices("id", "_id"),
        serialization_alias="_id",
    )
    rank: Optional[int] = Field(
        default=None,
        description="1 = best recommendation for mono crop, dont specify if inside intercropping.",
    )
    crop_name: str = Field(description="Name of the crop in specified language")
    crop_name_english: str = Field(
        description="Full crop name in English only (for image lookup), e.g. 'Pearl Millet'."
    )
    variety: str = Field(description="Variety of the crop")
    image_url: Optional[str] = Field(
        default=None,
        description="URL of the crop image. Do not put crop name in this field.",
    )
    suitability_score: float = Field(
        ge=0, le=1, description="0-1 score for soil & weather fit"
    )
    confidence: float = Field(ge=0, le=1, description="Model confidence 0-1")
    expected_yield_per_acre: str = Field(description="e.g. '20-25 quintals per acre'")
    sowing_window: SowingWindow
    growing_period_days: int = Field(description="Growing period in days")
    financial_forecasting: FinancialForecasting
    reasons: List[str]
    risk_factors: List[RiskFactor]
    description: str = Field(
        description="Farmer-friendly explanation of the recommendation"
    )

    @model_validator(mode="before")
    @classmethod
    def _backfill_crop_name_english(cls, values):
        if not isinstance(values, dict):
            return values

        english_name = values.get("crop_name_english")
        if isinstance(english_name, str) and english_name.strip():
            return values

        crop_name = values.get("crop_name")
        if isinstance(crop_name, str) and crop_name.strip():
            values["crop_name_english"] = crop_name.strip()
        return values


class InterCropRecommendation(BaseModel):
    """Describes a complete intercropping recommendation."""

    id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="UUID of inter crop. produced by backend not to be produced by AI at time of recommendation.",
        validation_alias=AliasChoices("id", "_id"),
        serialization_alias="_id",
    )
    rank: int = Field(description="1 = best recommendation.")
    intercrop_type: str = Field(
        description="The type of intercropping (e.g., 'Row Intercropping')."
    )
    no_of_crops: int = Field(description="The number of different crops involved.")
    arrangement: str = Field(
        description="The overall spacing or pattern (e.g., '6:2 pattern')."
    )
    specific_arrangement: List[SpecificArrangement] = Field(
        description="The arrangement details for each crop in the intercrop system."
    )
    crops: List[MonoCrop] = Field(
        description="A list of detailed recommendations for each crop in the mix."
    )
    description: str = Field(
        description="Clear and farmer-friendly explanation of, intercropping recommendation, telling why those crops are good, All benefits of this intercropping system."
    )
    benefits: List[str] = Field(
        description="A list of benefits for adopting this intercropping system."
    )


class RecommendationStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"


class CropRecommendationResponse(BaseModel):
    """Contains lists of recommendations for both mono-cropping and intercropping."""

    id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="UUID of the recommendation. Generated by program.",
        validation_alias=AliasChoices("id", "_id"),
        serialization_alias="_id",
    )
    farm_id: Optional[str] = Field(
        description="UUID of the farm, will be given by backend.",
        default=None,
    )
    timestamp: datetime = Field(
        description="Timestamp of recommendation generation",
        default_factory=datetime.now,
    )
    expiration_date: date = Field(
        description="Date after which this recommendation is considered expired.",
    )
    status: RecommendationStatus = Field(
        description="The status of the recommendation to the crop by AI (e.g., 'success')."
    )
    mono_crops: List[MonoCrop] = Field(
        description="A list of crop recommendations for single-crop cultivation 2 items."
    )
    inter_crops: List[InterCropRecommendation] = Field(
        description="A list of crop recommendations for intercropping systems 2 items."
    )


class CropSelectionResponse(BaseModel):
    """
    For Mono crop there should be single item in the list,
    For Inter crop there should be multiple items in the list for each crop.
    """

    cultivation_calendar: List[CultivationCalendar] = Field(
        description="Cultivation calendars for each crop."
    )
    investment_breakdown: List[InvestmentBreakdown] = Field(
        description="Investment breakdown for each crop."
    )
    soil_health_recommendations: SoilHealthRecommendations = Field(
        description="Soil health recommendations for the selected crop/intercrop."
    )
