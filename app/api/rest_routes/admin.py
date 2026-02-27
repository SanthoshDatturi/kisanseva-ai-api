from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response

from app.collections.crop_images import get_crop_images_by_name
from app.core.security import verify_admin
from app.services.azure_blob import get_blob_service_client
from app.services.files import upload_crop_images as upload_crop_images_service

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get("/login")
async def admin_login():
    template_path = (
        Path(__file__).parent.parent.parent / "templates" / "admin_login.html"
    )
    return HTMLResponse(content=template_path.read_text(encoding="utf-8"))


@router.get("/theme.css")
async def admin_theme_css():
    css_path = Path(__file__).parent.parent.parent / "templates" / "admin_theme.css"
    return Response(content=css_path.read_text(encoding="utf-8"), media_type="text/css")


@router.get("/handle-crop-images")
async def handle_crop_images():
    template_path = (
        Path(__file__).parent.parent.parent / "templates" / "crop_images.html"
    )
    return HTMLResponse(content=template_path.read_text(encoding="utf-8"))


@router.post("/crop-images")
async def upload_crop_images(
    images: List[UploadFile] = File(...),
    crop_names: List[str] = Form(...),
    _user_payload: dict = Depends(verify_admin),
):
    if len(images) != len(crop_names):
        raise HTTPException(
            status_code=400,
            detail=f"Number of images ({len(images)}) and crop names ({len(crop_names)}) must match",
        )
    try:
        urls = await upload_crop_images_service(
            file_streams=[image.file for image in images],
            crop_names=crop_names,
            mime_types=[image.content_type for image in images],
        )
        return {
            "message": "Crop images uploaded and documents inserted successfully",
            "urls": urls,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/crop-images")
async def get_crop_images(
    crop_name: str,
    _user_payload: dict = Depends(verify_admin),
):
    try:
        crop_images = await get_crop_images_by_name(crop_name)
        service_url = get_blob_service_client().url.rstrip("/")

        images = [
            {
                "crop_name": image.crop_name,
                "image_url": image.image_url.lstrip("/"),
                "blob_reference": image.image_url.lstrip("/"),
            }
            for image in crop_images
        ]

        return {
            "crop_name": crop_name,
            "service_url": service_url,
            "images": images,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
