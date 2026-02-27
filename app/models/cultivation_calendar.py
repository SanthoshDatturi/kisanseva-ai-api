from uuid import uuid4
from pydantic import AliasChoices, BaseModel, Field
from datetime import date
from enum import Enum
from typing import List


class TaskState(str, Enum):
    """Enumeration for the state of a cultivation task."""

    PENDING = "pending"
    COMPLETED = "completed"
    CANCELED = "canceled"


class Priority(str, Enum):
    """Enumeration for the priority level of a task."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CultivationTask(BaseModel):
    """Represents a single task in the cultivation plan."""

    task: str = Field(description="Description of the cultivation task.")
    from_date: date = Field(description="The start date for the task.")
    to_date: date = Field(description="The end date for the task.")
    state: TaskState = Field(
        default=TaskState.PENDING,
        description="Current state of the task. Set by backend.",
    )
    priority: Priority = Field(description="Priority level of the task.")


class CultivationCalendar(BaseModel):
    """Defines a complete cultivation calendar for a specific crop."""

    id: str = Field(
        description="UUID of the cultivation calendar, AI should ignore, given by system.",
        default_factory=lambda: uuid4().hex,
        validation_alias=AliasChoices("id", "_id"),
        serialization_alias="_id",
    )
    crop_id: str = Field(
        description="uuid of the particular crop this task calendar belongs to, given as input should be in output"
    )
    tasks: List[CultivationTask] = Field(
        description="A list of all tasks for the cultivation period."
    )
