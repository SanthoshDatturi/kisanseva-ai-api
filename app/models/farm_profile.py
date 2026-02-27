from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, Field


class SoilTexturePercentage(BaseModel):
    sand: float = Field(ge=0, le=100)
    silt: float = Field(ge=0, le=100)
    clay: float = Field(ge=0, le=100)


class SoilTestProperties(BaseModel):
    """Represents the detailed soil properties of a farm, from a soil test."""

    soil_texture: SoilTexturePercentage = Field(description="Texture of the soil.")
    ph_level: float = Field(ge=0, le=14, description="pH level of the soil.")
    electrical_conductivity_ds_m: float = Field(
        ge=0, description="Electrical Conductivity (EC) in dS/m."
    )
    organic_carbon_percent: float = Field(
        ge=0, le=100, description="Organic Carbon (OC) content in percentage."
    )

    # Macronutrients
    nitrogen_kg_per_acre: float = Field(
        ge=0, description="Available Nitrogen (N) in kg/acre."
    )
    phosphorus_kg_per_acre: float = Field(
        ge=0, description="Available Phosphorus (P) in kg/acre."
    )
    potassium_kg_per_acre: float = Field(
        ge=0, description="Available Potassium (K) in kg/acre."
    )

    # Secondary Nutrients
    sulphur_ppm: Optional[float] = Field(
        ge=0,
        default=None,
        description="Sulphur (S) content in parts per million (ppm).",
    )

    # Micronutrients
    zinc_ppm: Optional[float] = Field(
        ge=0, default=None, description="Zinc (Zn) content in parts per million (ppm)."
    )
    boron_ppm: Optional[float] = Field(
        ge=0, default=None, description="Boron (B) content in parts per million (ppm)."
    )
    iron_ppm: Optional[float] = Field(
        ge=0, default=None, description="Iron (Fe) content in parts per million (ppm)."
    )


class WaterSource(str, Enum):
    """Enumeration for types of water sources."""

    WELL = "Well"
    BOREWELL = "Borewell"
    CANAL = "Canal"
    RIVER = "River"
    LAKE = "Lake"
    RAINWATER_HARVESTING = "Rainwater Harvesting"
    MUNICIPAL_SUPPLY = "Municipal Supply"
    OTHER = "Other"


class IrrigationSystem(str, Enum):
    """Enumeration for types of irrigation systems."""

    DRIP = "Drip"
    SPRINKLER = "Sprinkler"
    FLOOD = "Flood"
    FURROW = "Furrow"
    OTHER = "Other"


class SoilType(str, Enum):
    """Enum for broad soil types recognizable from SoilGrids + visual classification."""

    BLACK = "Black soil"  # Regur, clayey, fertile
    RED = "Red soil"  # Iron-rich, low organic matter
    ALLUVIAL = "Alluvial soil"  # River plains, fertile, loamy
    LATERITE = "Laterite soil"  # Acidic, leached, brick-red
    DESERT = "Desert soil"  # Sandy, arid, low organic matter
    FOREST = "Forest soil"  # High humus, dark, acidic
    SALINE = "Saline/Alkaline soil"  # White crust, high pH
    SANDY = "Sandy soil"  # Gritty, drains fast
    CLAY = "Clay soil"  # Sticky, high clay content
    SILTY = "Silty soil"  # Smooth, fertile
    LOAMY = "Loamy soil"  # Balanced mix, ideal for crops


class Location(BaseModel):
    """Represents the geographical location of the farm."""

    latitude: float = Field(description="Latitude of the farm.")
    longitude: float = Field(description="Longitude of the farm.")
    village: str = Field(description="Village where the farm is located.")
    mandal: str = Field(description="Mandal where the farm is located.")
    district: str = Field(description="District where the farm is located.")
    state: str = Field(description="State where the farm is located.")
    zip_code: str = Field(description="Zip code of the farm's location.")


class PreviousCrops(BaseModel):
    """Represents information about crops previously grown on the farm."""

    crop_name: str = Field(description="Name of the crop grown.")
    year: int = Field(description="Year in which the crop was grown.")
    season: str = Field(description="The indian season this crop planted.")
    yield_per_acre: Optional[str] = Field(
        description="Yield obtained for the crop in that year (e.g., '20 quintals/acre')."
    )
    fertilizers_used: Optional[List[str]] = Field(
        description="List of fertilizers used for the crop."
    )
    pesticides_used: Optional[List[str]] = Field(
        description="List of pesticides used for the crop."
    )


class FarmProfile(BaseModel):
    """
    Detailed information about the farm's physical and operational aspects.
    All the values should be in user specified language.
    """

    id: str = Field(
        description="UUID of the farm profile",
        default_factory=lambda: uuid4().hex,
        validation_alias=AliasChoices("id", "_id"),
        serialization_alias="_id",
    )
    farmer_id: str = Field(description="UUID user_id of the user with role farmer")
    name: str = Field(description="Name of the farm any nick name they have.")
    location: Location = Field(description="Location of the farm")
    soil_type: SoilType = Field(
        description="Type of soil in the farm, can get by asking farmer or specified by AI with images"
    )
    crops: Optional[List[PreviousCrops]] = Field(
        description="List of crops grown on the farm"
    )
    total_area_acres: float = Field(description="Total area of the farm in acres.")
    cultivated_area_acres: float = Field(
        description="Area currently under cultivation in acres."
    )
    soil_test_properties: Optional[SoilTestProperties] = Field(
        description="Detailed soil properties of the farm.",
        default=None,
    )
    water_source: WaterSource = Field(description="Type of water source.")
    irrigation_system: Optional[IrrigationSystem] = Field(
        description="Type of irrigation system, Only asked if applicable for water resource",
        default=None,
    )
