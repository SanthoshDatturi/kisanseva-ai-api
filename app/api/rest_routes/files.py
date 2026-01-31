from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

from app.core.security import verify_jwt
from app.services.files import (
    FileType,
    VoiceModulation,
    VoiceName,
    delete_file_from_blob_storage,
    file_upload_to_blob_storage,
    text_to_speech_url,
)

router = APIRouter(prefix="/files", tags=["Files"])


class FileUploadResponse(BaseModel):
    url: str


@router.post("/upload", response_model=FileUploadResponse, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    blob_name: str = Form(...),
    file_type: FileType = Form(...),
    user_payload: dict = Depends(verify_jwt),
) -> FileUploadResponse:
    """
    Uploads a file as multipart/form-data to Azure Blob Storage and returns the URL.
    """
    url = await file_upload_to_blob_storage(
        file_stream=file.file,
        blob_name=blob_name,
        file_type=file_type,
        mime_type=file.content_type,
    )

    return FileUploadResponse(url=url)


class FileDeleteRequest(BaseModel):
    url: str
    file_type: FileType


@router.delete("/", status_code=204)
async def delete_file(
    request: FileDeleteRequest,
    user_payload: dict = Depends(verify_jwt),
):
    """
    Deletes a file from Azure Blob Storage given its URL.
    """
    await delete_file_from_blob_storage(
        blob_url=request.url, file_type=request.file_type
    )
    return


class TextToSpeechRequest(BaseModel):
    text: str
    blob_name: str
    modulation: VoiceModulation = VoiceModulation.GENERAL
    voice_name: VoiceName = VoiceName.KORE


@router.post("/text-to-speech", response_model=FileUploadResponse, status_code=201)
async def text_to_speech(
    request: TextToSpeechRequest,
    user_payload: dict = Depends(verify_jwt),
) -> FileUploadResponse:
    """
    Converts text to speech, uploads the audio file to Azure Blob Storage,
    and returns the URL.
    """
    url = await text_to_speech_url(
        text_or_data=request.text,
        blob_name=request.blob_name,
        modulation=request.modulation,
        language=user_payload.get("language", "as used in text"),
        voice_name=request.voice_name,
    )

    return FileUploadResponse(url=url)
