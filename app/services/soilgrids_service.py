import httpx
from typing import Optional
from pydantic import ValidationError
import os


async def get_soilgrids_data(lat: float, lon: float) -> Optional[str]:
    """
    Fetches soil properties data from the SoilGrids API for a given location.

    Args:
        lat: Latitude of the location.
        lon: Longitude of the location.

    Returns:
        A list of SoilProperty objects if the request is successful and
        the data is valid, otherwise None.
    """
    # For dev purpose, store data locally
    cache_dir = os.path.join(os.path.dirname(__file__), ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"get_soilgrids_data_lat_{lat}_lon_{lon}.json")

    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            return f.read()

    url = "https://rest.isric.org/soilgrids/v2.0/properties/query"
    params = {"lat": lat, "lon": lon}

    async with httpx.AsyncClient() as client:
        try:
            print(f"Fetching SoilGrids data from: {url}?lat={lat}&lon={lon}")
            response = await client.get(url, params=params, timeout=30.0)
            response.raise_for_status()  # Raise an exception for bad status
            data = response.text
            with open(cache_file, "w") as f:
                f.write(data)
            return data
        except httpx.HTTPStatusError as e:
            print(
                f"HTTP error occurred while fetching SoilGrids data: {e.response.status_code} - {e.response.text}"
            )
            return None
        except httpx.RequestError as e:
            print(
                f"Request error details:\nType: {type(e)}\nMessage: {e}\nRequest: {e.request.url if e.request else 'N/A'}"
            )
            return None
        except ValidationError as e:
            print(f"Error validating SoilGrids data: {e}")
            return e
        except Exception as e:
            print(f"An unexpected error occurred during SoilGrids data processing: {e}")
            raise e
    return None
