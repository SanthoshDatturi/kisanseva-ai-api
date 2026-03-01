from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, Field


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowType(str, Enum):
    CROP_RECOMMENDATION = "crop_recommendation"
    CROP_SELECTION = "crop_selection"
    PESTICIDE_RECOMMENDATION = "pesticide_recommendation"
    FARM_SURVEY = "farm_survey"
    GENERAL_CHAT = "general_chat"


class WorkflowStep(BaseModel):
    name: str
    status: WorkflowStepStatus = Field(default=WorkflowStepStatus.PENDING)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    attempts: int = Field(default=0)
    error: Optional[str] = Field(default=None)


class AIWorkflowRun(BaseModel):
    id: str = Field(
        default_factory=lambda: uuid4().hex,
        validation_alias=AliasChoices("id", "_id"),
        serialization_alias="_id",
    )
    action: str
    workflow_type: WorkflowType
    status: WorkflowStatus = Field(default=WorkflowStatus.PENDING)
    user_id: Optional[str] = Field(default=None)
    request_id: Optional[str] = Field(default=None)
    farm_id: Optional[str] = Field(default=None)
    crop_id: Optional[str] = Field(default=None)
    chat_id: Optional[str] = Field(default=None)
    current_step: Optional[str] = Field(default=None)
    steps: Dict[str, WorkflowStep] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AIWorkflowEvent(BaseModel):
    id: str = Field(
        default_factory=lambda: uuid4().hex,
        validation_alias=AliasChoices("id", "_id"),
        serialization_alias="_id",
    )
    workflow_id: str
    action: str
    event_type: str
    step: Optional[str] = Field(default=None)
    payload: Dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=datetime.utcnow)
