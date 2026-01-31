import os
import tempfile
import traceback
import wave
from enum import Enum
from typing import IO, Union
from urllib.parse import urlparse

import httpx
from azure.storage.blob import ContentSettings
from fastapi import HTTPException
from google.genai import types

from app.core.genai_client import get_client
from app.services.azure_blob import (
    get_audio_container_client,
    get_image_container_client,
)


async def convert_file_uri(third_party_uri: str):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(third_party_uri)
            resp.raise_for_status()
            content = resp.content
            mime_type = resp.headers.get("Content-Type", "application/octet-stream")

        # Use tempfile to write bytes to disk
        suffix = ""
        # Optionally infer extension from MIME type
        # e.g. if mime_type == "image/jpeg": suffix = ".jpg"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            tmp.write(content)
            tmp.flush()
            tmp_path = tmp.name
        finally:
            tmp.close()

        # Upload using path
        genai_file = await get_client().aio.files.upload(
            file=tmp_path, config={"mime_type": mime_type}
        )

        # Optionally delete the temp file
        try:
            os.remove(tmp_path)
        except Exception:
            raise HTTPException(
                status_code=500, detail="Failed to delete temporary file."
            )
        # Return the MIME type determined by the GenAI file service after upload
        return genai_file.uri, genai_file.mime_type

    except HTTPException as he:
        raise he
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{str(e)} (convert_file_uri)")


def wave_file_bytes(
    pcm: bytes, channels: int = 1, rate: int = 24000, sample_width: int = 2
) -> bytes:
    """Creates a WAV file in memory and returns its bytes."""
    import io

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buffer.getvalue()


class VoiceModulation(str, Enum):
    GENERAL = "general"
    DATA_EXPLANATION = "data_explanation"


voice_modulations = {
    VoiceModulation.GENERAL: "Say clearly little faster",
    VoiceModulation.DATA_EXPLANATION: "Explain the given data clearly to a layman",
}


class VoiceName(str, Enum):
    KORE = "Kore"


async def text_to_speech_url(
    text_or_data: str,
    blob_name: str,
    modulation: VoiceModulation = VoiceModulation.GENERAL,
    language: str = "same as text",
    voice_name: VoiceName = VoiceName.KORE,
) -> str:
    try:
        client = get_client()

        system_instruction = (
            f"Explain the given data clearly to a layman clearly, fully in language {language}."
            "The generated text will be used for TTS."
            "If data is not provided return nothing."
        )

        if modulation == VoiceModulation.DATA_EXPLANATION:
            text_response = await client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=text_or_data,
                config=types.GenerateContentConfig(
                    safety_settings=[
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                            threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                        )
                    ],
                    system_instruction=system_instruction,
                ),
            )

            text = text_response.text
        else:
            text = text_or_data

        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=f"{voice_modulations.get(modulation, voice_modulations[VoiceModulation.GENERAL])} in the language {language}: {text}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name.value,
                        )
                    )
                ),
            ),
        )

        data = response.candidates[0].content.parts[0].inline_data.data

        audio_container_client = await get_audio_container_client()
        blob_name = f"{blob_name}.wav"
        blob_client = audio_container_client.get_blob_client(blob_name)
        await blob_client.upload_blob(
            wave_file_bytes(data),
            overwrite=True,
            content_settings=ContentSettings(content_type="audio/wav"),
        )
        return blob_client.url
    except Exception as e:
        print(f"{str(e)} (text_to_speech_url)")
        raise HTTPException(status_code=500, detail="Text to speech conversion failed.")


class FileType(str, Enum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"


container_map = {
    FileType.IMAGE: get_image_container_client,
    FileType.AUDIO: get_audio_container_client,
}


async def file_upload_to_blob_storage(
    file_stream: Union[bytes, IO[bytes]],
    blob_name: str,
    file_type: FileType,
    mime_type: str = None,
) -> str:
    """
    Uploads a file stream or bytes to Azure Blob Storage and returns the URL.
    """
    try:
        if file_type not in container_map:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: '{file_type}'. Supported types are: {list(container_map.keys())}",
            )
        container_client = await container_map[file_type]()

        blob_client = container_client.get_blob_client(blob_name)
        if mime_type:
            settings = ContentSettings(content_type=mime_type)
            await blob_client.upload_blob(
                file_stream,
                overwrite=True,
                content_settings=settings,
            )
        else:
            await blob_client.upload_blob(file_stream, overwrite=True)
        return blob_client.url
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload file to blob storage: {str(e)}",
        )


async def delete_file_from_blob_storage(
    blob_url: str,
    file_type: FileType,
) -> None:
    """
    Deletes a file from Azure Blob Storage using its URL.
    The URL is parsed to extract the container (file_type) and blob name.
    """
    try:
        parsed_url = urlparse(blob_url)
        path_parts = parsed_url.path.strip("/").split("/")

        if len(path_parts) < 2:
            raise HTTPException(
                status_code=400,
                detail="Invalid blob URL format. Expected format like '.../<file_type>/<blob_name>'.",
            )

        blob_name = "/".join(path_parts[1:])

        if file_type not in container_map:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: '{file_type}'. Supported types are: {list(container_map.keys())}",
            )

        container_client = await container_map[file_type]()
        blob_client = container_client.get_blob_client(blob_name)
        await blob_client.delete_blob()
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete file from blob storage: {str(e)} (delete_file_from_blob_storage)",
        )
