# app/api/websocket/actions.py
import json
from uuid import uuid4

from fastapi import HTTPException, status

from app.models.chat_session import MessageContent
from app.services.crop_recommendation_service import (
    crop_recommendation,
    select_crop_from_recommendation,
)
from app.services.farm_survey_service import (
    farm_survey_agent,
)
from app.services.files import (
    VoiceModulation,
    VoiceName,
    build_user_scoped_path_prefix,
    text_to_speech_url,
)
from app.services.general_chat import general_chat_service
from app.services.pesticide_recommendation_service import (
    pesticide_recommendation,
)

from .manager import manager


def _build_stream_emitter(user_id: str):
    async def _emitter(payload: dict):
        await manager.send_to_user(user_id, json.dumps(payload, default=str))

    return _emitter


async def farm_survey_agent_handler(user_id: str, language: str, data: dict):
    try:
        content_data = data.get("content")
        if not content_data:
            # Handle cases where content might be missing, or initialize an empty one
            content = MessageContent(parts=[])
        else:
            content = MessageContent(**content_data)

        chat_id = data.get("chat_id")
        if not chat_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="chat_id is required for farm_survey_agent",
            )
        request_id = data.get("request_id")
        if not request_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="request_id is required for farm_survey_agent",
            )

        await farm_survey_agent(
            user_id=user_id,
            language=language,
            content=content,
            audio_response=data.get("audio_response", False),
            chat_id=chat_id,
            request_id=request_id,
            stream_emitter=_build_stream_emitter(user_id),
        )

    except HTTPException as e:
        response = {
            "action": "farm_survey_agent",
            "error": {
                "status_code": e.status_code,
                "message": e.detail,
            },
        }
        await manager.send_to_user(user_id, json.dumps(response))


async def crop_recommendation_handler(user_id: str, language: str, data: dict):
    try:
        await crop_recommendation(
            farm_id=data.get("farm_id", ""),
            language=language,
            user_id=user_id,
            request_id=data.get("request_id", uuid4().hex),
            stream_emitter=_build_stream_emitter(user_id),
        )
    except HTTPException as e:
        response = {
            "action": "crop_recommendation",
            "error": {"status_code": e.status_code, "message": e.detail},
        }
        await manager.send_to_user(user_id, json.dumps(response))


async def select_crop_from_recommendation_handler(
    user_id: str, language: str, data: dict
):
    try:
        await select_crop_from_recommendation(
            farm_id=data.get("farm_id", ""),
            crop_recommendation_response_id=data.get(
                "crop_recommendation_response_id", ""
            ),
            language=language,
            selected_crop_id=data.get("selected_crop_id", ""),
            user_id=user_id,
            request_id=data.get("request_id", uuid4().hex),
            stream_emitter=_build_stream_emitter(user_id),
        )
    except HTTPException as e:
        response = {
            "action": "select_crop_from_recommendation",
            "error": {"status_code": e.status_code, "message": e.detail},
        }
        await manager.send_to_user(user_id, json.dumps(response))


async def pesticide_recommendation_handler(user_id: str, language: str, data: dict):
    try:
        await pesticide_recommendation(
            crop_id=data.get("crop_id", ""),
            farm_id=data.get("farm_id", ""),
            pest_or_disease_description=data.get("pest_or_disease_description", ""),
            language=language,
            files=data.get("files", []),
            user_id=user_id,
            request_id=data.get("request_id", uuid4().hex),
            stream_emitter=_build_stream_emitter(user_id),
        )
    except HTTPException as e:
        response = {
            "action": "pesticide_recommendation",
            "error": {"status_code": e.status_code, "message": e.detail},
        }
        await manager.send_to_user(user_id, json.dumps(response))


async def text_to_speech_url_handler(user_id: str, language: str, data: dict):
    try:
        modulation_str = data.get("modulation", "general")
        try:
            modulation = VoiceModulation(modulation_str)
        except ValueError:
            modulation = VoiceModulation.GENERAL

        voice_name_str = data.get("voice_name", "Kore")
        try:
            voice_name = VoiceName(voice_name_str)
        except ValueError:
            voice_name = VoiceName.KORE

        if modulation == VoiceModulation.DATA_EXPLANATION:
            text_or_data = json.dumps(data.get("text_or_data", ""))
        else:
            text_or_data = data.get("text_or_data", "")

        blob_reference = await text_to_speech_url(
            text_or_data=text_or_data,
            blob_name=data.get("blob_name", uuid4().hex),
            modulation=modulation,
            language=language,
            voice_name=voice_name,
            path_prefix=build_user_scoped_path_prefix(
                user_id=user_id,
                path_prefix=data.get("path_prefix"),
            ),
        )

        response = {
            "action": "text_to_speech_url",
            "data": {"url": blob_reference},
        }
        await manager.send_to_user(user_id, json.dumps(response))
    except HTTPException as e:
        response = {
            "action": "text_to_speech_url",
            "error": {"status_code": e.status_code, "message": e.detail},
        }
        await manager.send_to_user(user_id, json.dumps(response))


async def general_chat_handler(user_id: str, language: str, data: dict):
    try:
        content_data = data.get("content")
        if not content_data:
            # Handle cases where content might be missing, or initialize an empty one
            content = MessageContent(parts=[])
        else:
            content = MessageContent(**content_data)

        chat_id = data.get("chat_id")
        if not chat_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="chat_id is required for general_chat",
            )
        request_id = data.get("request_id")
        if not request_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="request_id is required for general_chat",
            )

        await general_chat_service(
            user_id=user_id,
            language=language,
            content=content,
            audio_response=data.get("audio_response", False),
            chat_id=chat_id,
            request_id=request_id,
            stream_emitter=_build_stream_emitter(user_id),
        )
    except HTTPException as e:
        response = {
            "action": "general_chat",
            "error": {
                "status_code": e.status_code,
                "message": e.detail,
            },
        }
        await manager.send_to_user(user_id, json.dumps(response))


actions = {
    "farm_survey_agent": farm_survey_agent_handler,
    "crop_recommendation": crop_recommendation_handler,
    "select_crop_from_recommendation": select_crop_from_recommendation_handler,
    "pesticide_recommendation": pesticide_recommendation_handler,
    "text_to_speech_url": text_to_speech_url_handler,
    "general_chat": general_chat_handler,
}
