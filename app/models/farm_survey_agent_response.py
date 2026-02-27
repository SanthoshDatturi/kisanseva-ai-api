from typing import Optional

from pydantic import Field

from .chat_session import GeneralChatModelResponse, GeneralChatResponse
from .farm_profile import FarmProfile


class FarmSurveyAgentResponse(GeneralChatModelResponse):
    """
    Represents the response structure for the Farm Survey Agent.
    This model defines the expected output format from the agent,
    including the command for the frontend/backend and any message to the user.
    """

    farm_profile: Optional[FarmProfile] = Field(
        default=None,
        description="To be taken by AI from the farmer and give at the end of the conversation, with EXIT command. (English version)",
    )
    user_language_farm_profile: Optional[FarmProfile] = Field(
        default=None,
        description="Farm profile with same details as english version but the values are should be in user specific language.",
    )

class FarmSurveyAgentMappedResponse(GeneralChatResponse):
    farm_profile: Optional[FarmProfile] = Field(default=None)