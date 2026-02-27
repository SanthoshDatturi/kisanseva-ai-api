from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.collections.user import (
    delete_user as db_delete_user,
)
from app.collections.user import get_user_from_id, get_user_from_phone, save_user
from app.core.security import (
    create_access_token,
    get_otp,
    validate_otp,
    verify_jwt,
)
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


class OTPStatusResponse(BaseModel):
    message: str
    phone: str


class Token(BaseModel):
    access_token: str
    user: User


class OTPSendRequest(BaseModel):
    phone: str
    name: str | None = None
    language: str | None = None


class OTPVerifyRequest(BaseModel):
    phone: str
    otp: str


@router.post("/send-otp", response_model=OTPStatusResponse)
async def send_otp(request_data: OTPSendRequest):
    """
    Sends an OTP to the user's phone. If the user doesn't exist, it creates a
    new user record. This endpoint is used for both signup and login.
    """
    user = await get_user_from_phone(request_data.phone)
    message = "OTP sent successfully."

    if user and request_data.name and request_data.language:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists.",
        )

    if not user:
        # This is a new user (signup)
        if not request_data.name or not request_data.language:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name and language are required for new users.",
            )
        new_user = User(
            phone=request_data.phone,
            name=request_data.name,
            language=request_data.language,
        )
        await save_user(new_user)
        message = "User created. OTP sent successfully."

    await get_otp(request_data.phone)
    return OTPStatusResponse(message=message, phone=request_data.phone)


@router.post("/verify-otp", response_model=Token)
async def verify_otp(verify_data: OTPVerifyRequest):
    """
    Verifies the OTP and returns a JWT access token upon success.
    """

    user = await get_user_from_phone(verify_data.phone)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )

    if not await validate_otp(verify_data.phone, verify_data.otp):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OTP"
        )

    if not user.is_verified:
        user.is_verified = True
        await save_user(user)

    access_token = create_access_token(
        data={"sub": user.id, "role": user.role, "language": user.language}
    )
    return {"access_token": access_token, "user": user}


@router.delete("/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_current_user(user_payload: dict = Depends(verify_jwt)):
    """
    Deletes the currently authenticated user. Requires a valid JWT token.
    """
    await db_delete_user(user_payload.get("sub"))
    return


@router.get("/user", status_code=status.HTTP_200_OK, response_model=User)
async def get_current_user(user_payload: dict = Depends(verify_jwt)):
    """
    Retrieves the currently authenticated user's information.
    """
    user = await get_user_from_id(user_payload.get("sub"))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )
    return user
