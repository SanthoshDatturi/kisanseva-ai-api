from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import verify_jwt
from app.models.weather import (
    AirPollutionResponse,
    CurrentWeatherResponse,
    ForecastResponse,
    GeocodingResponse,
)
from app.services.weather_service import (
    get_5_day_3_hour_forecast,
    get_air_pollution,
    get_current_weather,
    get_reverse_geocoding,
)

router = APIRouter(prefix="/weather", tags=["Weather"], dependencies=[Depends(verify_jwt)])


@router.get(
    "/current",
    response_model=CurrentWeatherResponse,
    response_model_exclude_none=True,
)
async def get_current_weather_data(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    """
    Get current weather data for a specific location.
    """
    weather = await get_current_weather(lat, lon)
    if not weather:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not fetch weather data",
        )
    return weather


@router.get(
    "/forecast",
    response_model=ForecastResponse,
    response_model_exclude_none=True,
)
async def get_weather_forecast(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    """
    Get 5-day / 3-hour forecast data for a specific location.
    """
    forecast = await get_5_day_3_hour_forecast(lat, lon)
    if not forecast:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not fetch forecast data",
        )
    return forecast


@router.get(
    "/air-pollution",
    response_model=AirPollutionResponse,
    response_model_exclude_none=True,
)
async def get_air_pollution_data(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    """
    Get air pollution data for a specific location.
    """
    pollution = await get_air_pollution(lat, lon)
    if not pollution:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not fetch air pollution data",
        )
    return pollution


@router.get(
    "/reverse-geocoding",
    response_model=List[GeocodingResponse],
    response_model_exclude_none=True,
)
async def get_location_name(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    """
    Get location names from coordinates (Reverse Geocoding).
    """
    locations = await get_reverse_geocoding(lat, lon)
    if locations is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not fetch geocoding data",
        )
    return locations