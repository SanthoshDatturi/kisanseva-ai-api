import httpx
from typing import List, Optional
import json
from app.models.weather import (
    CurrentWeatherResponse,
    ForecastResponse,
    AirPollutionResponse,
    GeocodingResponse,
    WeatherMapResponse,
    WeatherMapLayer,
)

# It's highly recommended to use an environment variable for your API key.
import os

API_KEY = os.getenv("OPENWEATHERMAP_API_KEY", "your_default_api_key")

BASE_URL = "https://api.openweathermap.org/data/2.5"
GEO_BASE_URL = "http://api.openweathermap.org/geo/1.0"
MAP_BASE_URL = "https://tile.openweathermap.org/map"


async def get_current_weather(
    lat: float, lon: float
) -> Optional[CurrentWeatherResponse]:
    """
    Fetches the current weather for a given latitude and longitude.

    Args:
        lat: Latitude.
        lon: Longitude.

    Returns:
        A CurrentWeatherResponse object or None if the request fails.
    """
    # For dev purpose, store data locally
    cache_dir = os.path.join(os.path.dirname(__file__), ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(
        cache_dir, f"get_current_weather_lat_{lat}_lon_{lon}.json"
    )

    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            return CurrentWeatherResponse(**json.load(f))

    params = {"lat": lat, "lon": lon, "appid": API_KEY, "units": "metric"}
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/weather", params=params)
        if response.status_code == 200:
            data = response.json()
            with open(cache_file, "w") as f:
                json.dump(data, f)
            return CurrentWeatherResponse(**data)
    return None


async def get_5_day_3_hour_forecast(
    lat: float, lon: float
) -> Optional[ForecastResponse]:
    """
    Fetches the 5-day forecast (with 3-hour intervals) for a given location.

    Args:
        lat: Latitude.
        lon: Longitude.

    Returns:
        A ForecastResponse object or None if the request fails.
    """
    # For dev purpose, store data locally
    cache_dir = os.path.join(os.path.dirname(__file__), ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(
        cache_dir, f"get_5_day_3_hour_forecast_lat_{lat}_lon_{lon}.json"
    )

    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            return ForecastResponse(**json.load(f))

    params = {"lat": lat, "lon": lon, "appid": API_KEY, "units": "metric"}
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/forecast", params=params)
        if response.status_code == 200:
            data = response.json()
            with open(cache_file, "w") as f:
                json.dump(data, f)
            return ForecastResponse(**data)
    return None


async def get_air_pollution(lat: float, lon: float) -> Optional[AirPollutionResponse]:
    """
    Fetches air pollution data for a given latitude and longitude.

    Args:
        lat: Latitude.
        lon: Longitude.

    Returns:
        An AirPollutionResponse object or None if the request fails.
    """
    params = {"lat": lat, "lon": lon, "appid": API_KEY}
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/air_pollution", params=params)
        if response.status_code == 200:
            return AirPollutionResponse(**response.json())
    return None


async def get_reverse_geocoding(
    lat: float, lon: float
) -> Optional[List[GeocodingResponse]]:
    """
    Performs reverse geocoding to find location names from coordinates.

    Args:
        lat: Latitude.
        lon: Longitude.

    Returns:
        A list of GeocodingResponse objects or None if the request fails.
    """
    params = {"lat": lat, "lon": lon, "limit": 5, "appid": API_KEY}
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{GEO_BASE_URL}/reverse", params=params)
        if response.status_code == 200:
            return [GeocodingResponse(**item) for item in response.json()]
    return None


def get_weather_map_urls() -> WeatherMapResponse:
    """
    Generates tile URL templates for various weather map layers.
    Note: This function does not make an API call but constructs the URLs
    based on the OpenWeatherMap tile server structure. The API key is
    embedded in the URL.

    Returns:
        A WeatherMapResponse object containing URLs for different layers.
    """
    layers = {
        "precipitation": "precipitation_new",
        "clouds": "clouds_new",
        "pressure": "pressure_new",
        "temperature": "temp_new",
        "wind": "wind_new",
    }

    map_layers = {}
    for name, layer_code in layers.items():
        url = f"{MAP_BASE_URL}/{layer_code}/{{z}}/{{x}}/{{y}}.png?appid={API_KEY}"
        map_layers[name] = WeatherMapLayer(layer=layer_code, url=url)

    return WeatherMapResponse(**map_layers)


# Example of how to use the map URL function:
#
# map_urls = get_weather_map_urls()
# print(f"Temperature Map URL: {map_urls.temperature.url}")
#
# # To get a specific tile, you would replace {z}, {x}, and {y}
# # e.g., for zoom level 1, x=0, y=0
# specific_tile_url = map_urls.temperature.url.format(z=1, x=0, y=0)
# print(f"Specific Tile URL: {specific_tile_url}")
