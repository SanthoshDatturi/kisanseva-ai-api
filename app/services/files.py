import asyncio
import mimetypes
import os
import re
import tempfile
import traceback
from enum import Enum
from typing import IO, List, Union

import httpx
from azure.storage.blob import ContentSettings
from fastapi import HTTPException
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate

from app.collections.crop_images import insert_crop_documents
from app.core.genai_client import (
    get_chat_model,
    get_embeddings_model,
    get_raw_google_client,
)
from app.models.crop_image import EMBEDDING_DIMENSION, CropImageDocument
from app.services.azure_blob import (
    get_ai_chat_container_client,
    get_blob_service_client,
    get_system_data_container_client,
    get_user_content_container_client,
)


class FileType(str, Enum):
    USER_CONTENT = "user-content"
    AI_CHAT = "ai-chat"
    SYSTEM_DATA = "system-data"


CONTAINER_PREFIXES = {file_type.value for file_type in FileType}
USER_SCOPED_FILE_TYPES = {FileType.USER_CONTENT, FileType.AI_CHAT}


def _clean_path_segment(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().strip("/")


def _split_clean_path_segments(value: str | None) -> list[str]:
    cleaned = _clean_path_segment(value)
    if not cleaned:
        return []
    return [segment.strip() for segment in cleaned.split("/") if segment.strip()]


def build_user_scoped_path_prefix(user_id: str | None, path_prefix: str | None) -> str:
    """
    Normalizes a user-provided path prefix so uploads are scoped to:
    '<user_id>/<data_id>[/*]'.
    """
    cleaned_user_id = _clean_path_segment(user_id)
    if not cleaned_user_id:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    path_segments = _split_clean_path_segments(path_prefix)
    if not path_segments:
        raise HTTPException(
            status_code=400,
            detail="path_prefix is required and must include data_id.",
        )

    if path_segments[0] == cleaned_user_id:
        data_segments = path_segments[1:]
    else:
        data_segments = path_segments

    if not data_segments:
        raise HTTPException(
            status_code=400,
            detail="path_prefix must include data_id after user_id.",
        )

    return "/".join([cleaned_user_id, *data_segments])


def _normalize_upload_path_prefix(
    file_type: FileType,
    path_prefix: str | None,
) -> str | None:
    cleaned_path_prefix = _clean_path_segment(path_prefix)
    if file_type in USER_SCOPED_FILE_TYPES:
        segments = _split_clean_path_segments(cleaned_path_prefix)
        if len(segments) < 2:
            raise HTTPException(
                status_code=400,
                detail=(
                    "For 'ai-chat' and 'user-content', path_prefix must be "
                    "'<user_id>/<data_id>' (or a deeper path under it)."
                ),
            )
    return cleaned_path_prefix or None


def is_blob_reference(value: str | None) -> bool:
    if not value:
        return False
    cleaned = _clean_path_segment(value)
    if "/" not in cleaned:
        return False
    container = cleaned.split("/", 1)[0]
    return container in CONTAINER_PREFIXES


def build_blob_url(blob_reference: str) -> str:
    cleaned = _clean_path_segment(blob_reference)
    if not is_blob_reference(cleaned):
        return cleaned
    service_url = get_blob_service_client().url.rstrip("/")
    return f"{service_url}/{cleaned}"


def normalize_blob_reference(blob_reference: str) -> str:
    value = _clean_path_segment(blob_reference)
    if not value:
        raise HTTPException(status_code=400, detail="Blob reference is required.")

    if is_blob_reference(value):
        return value

    raise HTTPException(
        status_code=400,
        detail="Blob value must be in '<container>/<path>' format.",
    )


def _split_blob_reference(blob_reference: str) -> tuple[str, str]:
    normalized = normalize_blob_reference(blob_reference)
    container_name, blob_name = normalized.split("/", 1)
    return container_name, blob_name


async def convert_file_uri(third_party_uri: str):
    try:
        normalized_reference = normalize_blob_reference(third_party_uri)
        source_uri = build_blob_url(normalized_reference)

        async with httpx.AsyncClient() as client:
            resp = await client.get(source_uri)
            resp.raise_for_status()
            content = resp.content
            mime_type = resp.headers.get("Content-Type", "application/octet-stream")

        suffix = ""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            tmp.write(content)
            tmp.flush()
            tmp_path = tmp.name
        finally:
            tmp.close()

        genai_file = await get_raw_google_client().aio.files.upload(
            file=tmp_path, config={"mime_type": mime_type}
        )

        try:
            os.remove(tmp_path)
        except Exception:
            raise HTTPException(
                status_code=500, detail="Failed to delete temporary file."
            )

        return genai_file.uri, genai_file.mime_type

    except HTTPException as he:
        raise he
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{str(e)} (convert_file_uri)")


class VoiceModulation(str, Enum):
    GENERAL = "general"
    DATA_EXPLANATION = "data_explanation"


voice_modulations = {
    VoiceModulation.GENERAL: "Say clearly little faster",
    VoiceModulation.DATA_EXPLANATION: "Explain the given data clearly to a layman",
}


class VoiceName(str, Enum):
    KORE = "Kore"


def _extract_ai_text(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content

    if isinstance(message.content, list):
        text_values = []
        for block in message.content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_values.append(block.get("text") or "")
        return "\n".join([text for text in text_values if text]).strip()

    return ""


container_map = {
    FileType.USER_CONTENT: get_user_content_container_client,
    FileType.AI_CHAT: get_ai_chat_container_client,
    FileType.SYSTEM_DATA: get_system_data_container_client,
}


def _guess_mime_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "audio/wav"
    return "application/octet-stream"


def _build_blob_reference(
    file_type: FileType,
    blob_name: str,
    path_prefix: str | None = None,
) -> tuple[str, str]:
    cleaned_blob_name = _clean_path_segment(blob_name)
    if not cleaned_blob_name:
        raise HTTPException(status_code=400, detail="blob_name cannot be empty.")

    parts = [
        _clean_path_segment(path_prefix),
        cleaned_blob_name,
    ]
    blob_name_in_container = "/".join([part for part in parts if part])

    if not blob_name_in_container:
        raise HTTPException(status_code=400, detail="Invalid blob path.")

    return f"{file_type.value}/{blob_name_in_container}", blob_name_in_container


def _normalize_blob_name(blob_name: str) -> str:
    cleaned = _clean_path_segment(blob_name)
    if not cleaned:
        return ""

    # Normalize whitespace inside each path segment without altering separators.
    segments = [segment.strip() for segment in cleaned.split("/") if segment.strip()]
    normalized_segments = [re.sub(r"\s+", "-", segment) for segment in segments]
    return "/".join(normalized_segments)


async def text_to_speech_url(
    text_or_data: str,
    blob_name: str,
    modulation: VoiceModulation = VoiceModulation.GENERAL,
    language: str = "same as text",
    voice_name: VoiceName = VoiceName.KORE,
    file_type: FileType = FileType.AI_CHAT,
    path_prefix: str | None = None,
) -> str:
    try:
        system_instruction = (
            f"Explain the given data clearly to a layman clearly, fully in language {language}."
            "The generated text will be used for TTS."
            "If data is not provided return nothing."
        )

        if modulation == VoiceModulation.DATA_EXPLANATION:
            explainer_prompt = ChatPromptTemplate.from_messages(
                [("system", "{system_instruction}"), ("human", "{input_text}")]
            )
            text_response = await get_chat_model(model="gemini-2.0-flash").ainvoke(
                explainer_prompt.format_messages(
                    system_instruction=system_instruction,
                    input_text=text_or_data,
                )
            )
            text = _extract_ai_text(text_response)
        else:
            text = text_or_data

        tts_prompt = (
            f"{voice_modulations.get(modulation, voice_modulations[VoiceModulation.GENERAL])} "
            f"in the language {language}: {text}"
        )
        tts_response = await get_chat_model(
            model="gemini-2.5-flash-preview-tts",
            response_modalities=["AUDIO"],
        ).ainvoke(
            tts_prompt,
            speech_config={
                "voice_config": {
                    "prebuilt_voice_config": {"voice_name": voice_name.value}
                }
            },
        )
        data = tts_response.additional_kwargs.get("audio")
        if not data:
            raise HTTPException(
                status_code=500, detail="TTS response has no audio data."
            )

        return await file_upload_to_blob_storage(
            file_stream=data,
            blob_name=blob_name,
            file_type=file_type,
            path_prefix=path_prefix,
            mime_type="audio/wav",
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"{str(e)} (text_to_speech_url)")
        raise HTTPException(status_code=500, detail="Text to speech conversion failed.")


async def file_upload_to_blob_storage(
    file_stream: Union[bytes, IO[bytes]],
    blob_name: str,
    file_type: FileType,
    path_prefix: str | None = None,
    mime_type: str | None = None,
) -> str:
    """
    Uploads a file stream or bytes to Azure Blob Storage and returns
    '<container>/<path>/<file.ext>' blob reference.
    """
    try:
        blob_name = _normalize_blob_name(blob_name)
        if not blob_name:
            raise HTTPException(status_code=400, detail="blob_name cannot be empty.")

        if mime_type is None:
            header = b""
            if isinstance(file_stream, bytes):
                header = file_stream[:2048]
            elif (
                hasattr(file_stream, "read")
                and hasattr(file_stream, "seek")
                and hasattr(file_stream, "tell")
            ):
                pos = file_stream.tell()
                header = file_stream.read(2048)
                file_stream.seek(pos)
            mime_type = _guess_mime_type(header)

        ext = mimetypes.guess_extension(mime_type) if mime_type else None
        if ext:
            if mime_type == "image/jpeg" and ext in [".jpe", ".jpeg"]:
                ext = ".jpg"
            if not blob_name.lower().endswith(ext):
                blob_name = f"{blob_name}{ext}"

        if file_type not in container_map:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: '{file_type}'. Supported types are: {list(container_map.keys())}",
            )

        normalized_path_prefix = _normalize_upload_path_prefix(
            file_type=file_type,
            path_prefix=path_prefix,
        )

        blob_reference, blob_name_in_container = _build_blob_reference(
            file_type=file_type,
            blob_name=blob_name,
            path_prefix=normalized_path_prefix,
        )

        container_client = await container_map[file_type]()
        blob_client = container_client.get_blob_client(blob_name_in_container)

        if mime_type:
            settings = ContentSettings(content_type=mime_type)
            await blob_client.upload_blob(
                file_stream,
                overwrite=True,
                content_settings=settings,
            )
        else:
            await blob_client.upload_blob(file_stream, overwrite=True)

        return blob_reference
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload file to blob storage: {str(e)}",
        )


async def upload_crop_images(
    file_streams: List[Union[bytes, IO[bytes]]],
    crop_names: List[str],
    mime_types: List[str] = None,
) -> List[str]:
    if not crop_names:
        return []

    upload_tasks = [
        file_upload_to_blob_storage(
            file_stream=fs,
            blob_name=cn,
            file_type=FileType.SYSTEM_DATA,
            path_prefix="crops",
            mime_type=mt,
        )
        for fs, cn, mt in zip(
            file_streams, crop_names, mime_types or [None] * len(crop_names)
        )
    ]

    embeddings = get_embeddings_model(model="gemini-embedding-001")

    embedding_task = embeddings.aembed_documents(
        crop_names,
        task_type="SEMANTIC_SIMILARITY",
        output_dimensionality=EMBEDDING_DIMENSION,
    )

    results = await asyncio.gather(*upload_tasks, embedding_task)
    blob_references = results[:-1]
    batch_response = results[-1]

    documents = [
        CropImageDocument(
            crop_name=cn,
            embedding=emb,
            image_url=blob_reference,
        )
        for cn, blob_reference, emb in zip(crop_names, blob_references, batch_response)
    ]
    await insert_crop_documents(documents)

    return blob_references


async def delete_file_from_blob_storage(
    blob_reference: str,
    file_type: FileType | None = None,
) -> None:
    """
    Deletes a file from Azure Blob Storage using
    '<container>/<path>' blob reference.
    """
    try:
        container_name, blob_name = _split_blob_reference(blob_reference)

        if file_type and file_type.value != container_name:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Container mismatch: expected '{file_type.value}', got '{container_name}'."
                ),
            )

        try:
            container_type = FileType(container_name)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported container '{container_name}'.",
            ) from exc

        container_client = await container_map[container_type]()
        blob_client = container_client.get_blob_client(blob_name)
        await blob_client.delete_blob()
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete file from blob storage: {str(e)} (delete_file_from_blob_storage)",
        )


async def delete_multiple_files(
    file_type: FileType,
    user_id: str,
    data_id: str,
) -> int:
    """
    Deletes multiple blobs from a container using required user/data filters.
    Returns the number of deleted blobs.
    """
    try:
        cleaned_user_id = _clean_path_segment(user_id)
        cleaned_data_id = _clean_path_segment(data_id)
        if not cleaned_user_id or not cleaned_data_id:
            raise HTTPException(
                status_code=400,
                detail="file_type, user_id and data_id are required.",
            )

        container_client = await container_map[file_type]()
        blob_names: set[str] = set()
        prefix = f"{cleaned_user_id}/{cleaned_data_id}/"
        async for blob in container_client.list_blobs(name_starts_with=prefix):
            blob_name = getattr(blob, "name", "")
            if blob_name:
                blob_names.add(blob_name)

        blob_name_list = list(blob_names)
        deleted_count = 0
        batch_size = 256
        for i in range(0, len(blob_name_list), batch_size):
            batch = blob_name_list[i : i + batch_size]
            await container_client.delete_blobs(*batch)
            deleted_count += len(batch)

        return deleted_count
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Failed to delete files from blob storage: {str(e)} "
                f"(delete_multiple_files: file_type={file_type}, "
                f"user_id={user_id}, data_id={data_id})"
            ),
        )
