from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from google.genai.types import Content
from pydantic import BaseModel, Field, field_serializer


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
    )
    user_id: str = Field(...)
    chat_type: ChatType = Field(description="Type of chat session")
    data_id: Optional[str] = Field(default=None)
    ts: float = Field(default_factory=lambda: datetime.now().timestamp())


class Message(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    chat_id: str = Field(...)
    content: Content = Field(
        ...,
        description="Content of the message. Serialized to snake_case, overriding nested model's camelCase config.",
    )
    ts: float = Field(default_factory=lambda: datetime.now().timestamp())

    @field_serializer("content")
    def serialize_content(self, value: Content, _info):
        return value.model_dump(by_alias=False)


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
