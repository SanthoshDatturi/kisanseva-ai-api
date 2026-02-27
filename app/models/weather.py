from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# --- Geocoding API Models ---


class LocalNames(BaseModel):
    """Language-specific names for the location."""

    ascii: Optional[str] = None
    feature_name: Optional[str] = None


class GeocodingResponse(BaseModel):
    """Model for the response from the Reverse Geocoding API."""

    name: str
    local_names: Optional[LocalNames] = None
    lat: float
    lon: float
    country: str
    state: Optional[str] = None


# --- Current Weather & Forecast Models ---


class WeatherCondition(BaseModel):
    """Describes the weather condition (e.g., 'Clouds', 'Rain')."""

    id: int
    main: str
    description: str
    icon: str


class MainWeatherData(BaseModel):
    """Core weather metrics like temperature and humidity."""

    temp: float
    feels_like: float
    temp_min: float
    temp_max: float
    pressure: int
    humidity: int
    sea_level: Optional[int] = None
    grnd_level: Optional[int] = None


class Wind(BaseModel):
    """Wind speed and direction."""

    speed: float
    deg: int
    gust: Optional[float] = None


class Clouds(BaseModel):
    """Cloudiness percentage."""

    all: int


class Rain(BaseModel):
    """Rain volume."""

    one_hour: Optional[float] = Field(None, alias="1h")
    three_hours: Optional[float] = Field(None, alias="3h")


class Snow(BaseModel):
    """Snow volume."""

    one_hour: Optional[float] = Field(None, alias="1h")
    three_hours: Optional[float] = Field(None, alias="3h")


class Sys(BaseModel):
    """System data like sunrise and sunset times."""

    type: Optional[int] = None
    id: Optional[int] = None
    country: Optional[str] = None
    sunrise: Optional[datetime] = None
    sunset: Optional[datetime] = None


class CurrentWeatherResponse(BaseModel):
    """Model for the complete Current Weather API response."""

    weather: List[WeatherCondition]
    main: MainWeatherData
    visibility: int
    wind: Wind
    clouds: Clouds
    rain: Optional[Rain] = None
    snow: Optional[Snow] = None
    dt: datetime
    sys: Sys
    timezone: int
    id: int
    name: str


# --- 5-Day / 3-Hour Forecast Models ---


class ForecastListItem(BaseModel):
    """A single forecast entry for a specific timestamp."""

    dt: datetime
    main: MainWeatherData
    weather: List[WeatherCondition]
    clouds: Clouds
    wind: Wind
    visibility: int
    pop: float = Field(description="Probability of precipitation")
    rain: Optional[Rain] = None
    snow: Optional[Snow] = None
    dt_txt: str


class Coordinates(BaseModel):
    """Latitude and Longitude."""

    lat: float
    lon: float


class City(BaseModel):
    """Information about the city in the forecast."""

    id: int
    name: str
    coord: Coordinates
    country: str
    population: int
    timezone: int
    sunrise: datetime
    sunset: datetime


class ForecastResponse(BaseModel):
    """Model for the complete 5-day/3-hour Forecast API response."""

    list: List[ForecastListItem]
    city: City


# --- Air Pollution Models ---


class AirQualityIndex(BaseModel):
    """Air Quality Index (AQI)."""

    main: dict = Field(description="{'aqi': 1|2|3|4|5}")

    @property
    def aqi(self) -> int:
        return self.main.get("aqi", 0)


class PollutantConcentration(BaseModel):
    """Concentration of various air pollutants."""

    co: float
    no: float
    no2: float
    o3: float
    so2: float
    pm2_5: float
    pm10: float
    nh3: float


class AirPollutionListItem(BaseModel):
    """A single air pollution data entry."""

    dt: datetime
    main: AirQualityIndex
    components: PollutantConcentration


class AirPollutionResponse(BaseModel):
    """Model for the complete Air Pollution API response."""

    list: List[AirPollutionListItem]


# --- Weather Map Models ---


class WeatherMapLayer(BaseModel):
    """Model representing a weather map layer URL."""

    layer: str = Field(
        description="The name of the weather layer (e.g., 'temp_new', 'clouds_new')."
    )
    url: str = Field(
        description="The URL template for the map tile. Replace {z}, {x}, and {y} with tile coordinates."
    )


class WeatherMapResponse(BaseModel):
    """A collection of URLs for different weather map layers."""

    precipitation: WeatherMapLayer
    clouds: WeatherMapLayer
    pressure: WeatherMapLayer
    temperature: WeatherMapLayer
    wind: WeatherMapLayer
