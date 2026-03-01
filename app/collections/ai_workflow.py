from datetime import datetime
from typing import List, Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.mongodb import get_ai_workflow_collection, get_ai_workflow_event_collection
from app.models.ai_workflow import AIWorkflowEvent, AIWorkflowRun


async def save_ai_workflow_run(workflow: AIWorkflowRun) -> AIWorkflowRun:
    collection: AsyncIOMotorCollection = get_ai_workflow_collection()
    workflow.updated_at = datetime.utcnow()
    payload = workflow.model_dump(mode="json", exclude_none=True, by_alias=True)
    await collection.replace_one({"_id": workflow.id}, payload, upsert=True)
    stored = await collection.find_one({"_id": workflow.id})
    return AIWorkflowRun.model_validate(stored)


async def get_ai_workflow_run(workflow_id: str) -> Optional[AIWorkflowRun]:
    collection: AsyncIOMotorCollection = get_ai_workflow_collection()
    stored = await collection.find_one({"_id": workflow_id})
    if not stored:
        return None
    return AIWorkflowRun.model_validate(stored)


async def save_ai_workflow_event(event: AIWorkflowEvent) -> AIWorkflowEvent:
    collection: AsyncIOMotorCollection = get_ai_workflow_event_collection()
    payload = event.model_dump(mode="json", exclude_none=True, by_alias=True)
    await collection.insert_one(payload)
    stored = await collection.find_one({"_id": event.id})
    return AIWorkflowEvent.model_validate(stored)


async def get_ai_workflow_events(
    workflow_id: str,
    limit: int = 100,
) -> List[AIWorkflowEvent]:
    collection: AsyncIOMotorCollection = get_ai_workflow_event_collection()
    cursor = collection.find({"workflow_id": workflow_id}).sort("ts", 1).limit(limit)
    return [AIWorkflowEvent.model_validate(item) async for item in cursor]
