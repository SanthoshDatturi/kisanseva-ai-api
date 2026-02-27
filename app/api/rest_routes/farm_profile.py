import asyncio
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.collections import farm_profile
from app.collections.user_language_specific.farm_profile import (
    delete_farm_profile,
    get_farm_profile_from_id,
    get_farm_profiles_from_user_id,
    save_farm_profile,
)
from app.core.security import verify_jwt
from app.models.farm_profile import FarmProfile

router = APIRouter(prefix="/farm-profiles", tags=["Farm Profile"])


@router.post(
    "/",
    response_model=FarmProfile,
    status_code=status.HTTP_201_CREATED,
    summary="Create or Update a Farm Profile",
    response_model_exclude_none=True,
)
async def create_or_update_farm_profile(
    profile: FarmProfile, user_payload=Depends(verify_jwt)
):
    """
    Create a new farm profile or update an existing one (upsert).
    The profile ID in the body will be used to identify an existing profile.
    If the ID exists, it will be updated; otherwise, a new one will be created.
    """
    saved_profile = await save_farm_profile(profile)
    return saved_profile


@router.get(
    "/{farm_id}",
    response_model=FarmProfile,
    summary="Get a farm profile by its ID",
    response_model_exclude_none=True,
)
async def get_farm_profile_by_id(farm_id: str, user_payload=Depends(verify_jwt)):
    """
    Retrieve a specific farm profile by its unique ID.
    """
    profile = await get_farm_profile_from_id(farm_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm profile with ID '{farm_id}' not found.",
        )
    return profile


@router.get(
    "/",
    response_model=List[FarmProfile],
    summary="Get all farm profiles for a user",
    response_model_exclude_none=True,
)
async def get_farm_profiles(user_payload=Depends(verify_jwt)):
    """
    Retrieve all farm profiles associated with a specific user ID.
    Returns an empty list if the user has no farm profiles.
    """
    user_id = user_payload["sub"]
    profiles = await get_farm_profiles_from_user_id(user_id)
    return profiles


@router.delete(
    "/{farm_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a farm profile",
)
async def delete_profile(farm_id: str, user_payload=Depends(verify_jwt)):
    """
    Delete a farm profile by its ID.
    """
    user_language_specific_task = delete_farm_profile(farm_id)
    english_task = farm_profile.delete_farm_profile(farm_id)
    task1, task2 = asyncio.gather(user_language_specific_task, english_task)
    success = await task1 and await task2
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Farm profile with ID '{farm_id}' not found for deletion.",
        )
    return
