from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, Field, field_validator


class Command(str, Enum):
    CONTINUE = "continue"  # Continue the conversation
    EXIT = "exit"  # Stop conversation and save the farm data
    OPEN_CAMERA = "open_camera"  # Opening camera if any pictures are needed
    LOCATION = "location"  # Get present location, when farmer is in farm


class ChatType(str, Enum):
    FARM_SURVEY = "farm_survey"
    CROP_RECOMMENDATION = "crop_recommendation"
    GENERAL = "general"
    ABOUT_CROP = "about_crop"
    ABOUT_PESTS = "about_pests"
    ABOUT_FERTILIZERS = "about_fertilizers"
    ABOUT_IRRIGATION = "about_irrigation"


class Role(str, Enum):
    USER = "user"
    MODEL = "model"
    SYSTEM = "system"


class ChatSession(BaseModel):
    id: str = Field(
        default_factory=lambda: uuid4().hex,
        validation_alias=AliasChoices("id", "_id"),
        serialization_alias="_id",
    )
    user_id: str = Field(...)
    chat_type: ChatType = Field(description="Type of chat session")
    data_id: Optional[str] = Field(default=None)
    ts: float = Field(default_factory=lambda: datetime.now().timestamp())


class Message(BaseModel):
    id: str = Field(
        default_factory=lambda: uuid4().hex,
        validation_alias=AliasChoices("id", "_id"),
        serialization_alias="_id",
    )
    chat_id: str = Field(...)
    content: "MessageContent" = Field(
        ...,
        description="Provider-agnostic content format with text/media parts.",
    )
    ts: float = Field(default_factory=lambda: datetime.now().timestamp())

    @field_validator("content", mode="before")
    @classmethod
    def _normalize_content(cls, value: Any) -> Any:
        if isinstance(value, MessageContent):
            return value

        if not isinstance(value, dict):
            return value

        role = value.get("role")
        parts = value.get("parts") or []

        normalized_parts = []
        for part in parts:
            if not isinstance(part, dict):
                continue

            if "file_data" in part and isinstance(part["file_data"], dict):
                file_data = part["file_data"]
            elif "fileData" in part and isinstance(part["fileData"], dict):
                file_data = part["fileData"]
            else:
                file_data = None

            if file_data and "file_uri" not in file_data and "fileUri" in file_data:
                file_data = {
                    "file_uri": file_data.get("fileUri"),
                    "mime_type": file_data.get("mimeType"),
                }

            normalized_parts.append(
                {
                    "text": part.get("text"),
                    "file_data": file_data,
                }
            )

        return {
            "role": role,
            "parts": normalized_parts,
        }


class MessageFileData(BaseModel):
    file_uri: str = Field(validation_alias=AliasChoices("file_uri", "fileUri"))
    mime_type: str = Field(
        default="application/octet-stream",
        validation_alias=AliasChoices("mime_type", "mimeType"),
    )


class MessagePart(BaseModel):
    text: Optional[str] = Field(default=None)
    file_data: Optional[MessageFileData] = Field(
        default=None,
        validation_alias=AliasChoices("file_data", "fileData"),
    )


class MessageContent(BaseModel):
    role: Optional[str] = Field(default=None)
    parts: list[MessagePart] = Field(default_factory=list)


class GeneralChatModelResponse(BaseModel):
    command: Command = Field(
        description="Command for the app to decide the next action."
    )
    message_to_user: str = Field(description="A message to be displayed to the user.")
    user_query: Optional[str] = Field(
        default=None, description="The original query from the user."
    )


class GeneralChatResponse(BaseModel):
    command: Command
    user_message: Optional[Message] = Field(default=None)
    model_message: Optional[Message] = Field(default=None)
