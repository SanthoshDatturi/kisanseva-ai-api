from uuid import uuid4
from pydantic import AliasChoices, BaseModel, Field
from typing import List


class Investment(BaseModel):
    """Represents a single line-item of investment."""

    reason: str = Field(description="Reason of the investment.")
    amount: float = Field(
        description="Estimated cost in rupees for this investment item.",
    )


class Profitability(BaseModel):
    """Summarizes the financial profitability forecast."""

    gross_income: float = Field(
        description="Expected total revenue in rupees from the chosen crop."
    )
    total_cost: float = Field(description="Sum of all investments.")
    net_profit: float = Field(description="Gross income minus total cost.")
    roi_percentage: float = Field(
        description="Return on investment: (net_profit / total_cost) * 100."
    )
    break_even_yield: str = Field(
        description="Yield needed per acre to cover total costs.",
    )


class InvestmentBreakdown(BaseModel):
    """Provides a detailed financial breakdown for a recommended crop."""

    id: str = Field(
        description="UUID of the investment breakdown, AI should ignore, given by system.",
        default_factory=lambda: uuid4().hex,
        validation_alias=AliasChoices("id", "_id"),
        serialization_alias="_id",
    )
    crop_id: str = Field(
        description="uuid of the particular crop this investment breakdown belongs to, given as input should be in output"
    )
    investments: List[Investment] = Field(
        description="A list of all anticipated investment items."
    )
    profitability: Profitability = Field(
        description="The overall profitability forecast."
    )
