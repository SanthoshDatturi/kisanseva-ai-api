from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from app.collections.ai_workflow import save_ai_workflow_event, save_ai_workflow_run
from app.models.ai_workflow import (
    AIWorkflowEvent,
    AIWorkflowRun,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepStatus,
    WorkflowType,
)

StreamEmitter = Callable[[dict[str, Any]], Awaitable[None]]


class WorkflowRuntime:
    def __init__(
        self,
        *,
        action: str,
        workflow_type: WorkflowType,
        emitter: Optional[StreamEmitter] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        farm_id: Optional[str] = None,
        crop_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        self.emitter = emitter
        self.workflow = AIWorkflowRun(
            action=action,
            workflow_type=workflow_type,
            user_id=user_id,
            request_id=request_id,
            farm_id=farm_id,
            crop_id=crop_id,
            chat_id=chat_id,
            metadata=metadata or {},
        )

    @property
    def id(self) -> str:
        return self.workflow.id

    @property
    def action(self) -> str:
        return self.workflow.action

    @property
    def current_step(self) -> Optional[str]:
        return self.workflow.current_step

    async def start(self) -> None:
        self.workflow.status = WorkflowStatus.RUNNING
        self.workflow.updated_at = datetime.utcnow()
        await save_ai_workflow_run(self.workflow)
        await self._emit_event(
            event_type="workflow_started",
            payload={"status": self.workflow.status.value},
        )

    async def start_step(self, step: str, payload: Optional[dict[str, Any]] = None) -> None:
        step_state = self.workflow.steps.get(step)
        if step_state is None:
            step_state = WorkflowStep(name=step)

        step_state.status = WorkflowStepStatus.IN_PROGRESS
        step_state.started_at = datetime.utcnow()
        step_state.completed_at = None
        step_state.error = None
        step_state.attempts += 1

        self.workflow.steps[step] = step_state
        self.workflow.current_step = step
        self.workflow.updated_at = datetime.utcnow()

        await save_ai_workflow_run(self.workflow)
        await self._emit_event(
            event_type="step_started",
            step=step,
            payload=payload or {},
        )

    async def complete_step(
        self,
        step: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        step_state = self.workflow.steps.get(step)
        if step_state is None:
            step_state = WorkflowStep(name=step)

        step_state.status = WorkflowStepStatus.COMPLETED
        if step_state.started_at is None:
            step_state.started_at = datetime.utcnow()
        step_state.completed_at = datetime.utcnow()
        step_state.error = None

        self.workflow.steps[step] = step_state
        self.workflow.current_step = step
        self.workflow.updated_at = datetime.utcnow()

        await save_ai_workflow_run(self.workflow)
        await self._emit_event(
            event_type="step_completed",
            step=step,
            payload=payload or {},
        )

    async def emit_chunk(
        self,
        *,
        step: Optional[str],
        chunk_type: str,
        data: Optional[dict[str, Any]] = None,
    ) -> None:
        payload = {"chunk_type": chunk_type, "data": data or {}}
        await self._emit_event(
            event_type="chunk",
            step=step,
            payload=payload,
        )

    async def emit_result(self, data: dict[str, Any]) -> None:
        await self._emit_event(
            event_type="result",
            step=self.workflow.current_step,
            payload=data,
        )

    async def complete(self, payload: Optional[dict[str, Any]] = None) -> None:
        self.workflow.status = WorkflowStatus.COMPLETED
        self.workflow.updated_at = datetime.utcnow()
        await save_ai_workflow_run(self.workflow)
        await self._emit_event(
            event_type="workflow_completed",
            step=self.workflow.current_step,
            payload=payload or {"status": self.workflow.status.value},
        )

    async def fail(
        self,
        *,
        error_message: str,
        step: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        target_step = step or self.workflow.current_step
        if target_step:
            step_state = self.workflow.steps.get(target_step)
            if step_state is None:
                step_state = WorkflowStep(name=target_step)
            step_state.status = WorkflowStepStatus.FAILED
            if step_state.started_at is None:
                step_state.started_at = datetime.utcnow()
            step_state.completed_at = datetime.utcnow()
            step_state.error = error_message
            self.workflow.steps[target_step] = step_state
            self.workflow.current_step = target_step

        self.workflow.status = WorkflowStatus.FAILED
        self.workflow.updated_at = datetime.utcnow()
        await save_ai_workflow_run(self.workflow)

        event_payload = {"error": error_message}
        if payload:
            event_payload.update(payload)

        await self._emit_event(
            event_type="workflow_failed",
            step=target_step,
            payload=event_payload,
        )

    async def _emit_event(
        self,
        *,
        event_type: str,
        payload: Optional[dict[str, Any]] = None,
        step: Optional[str] = None,
    ) -> None:
        payload = payload or {}

        event = AIWorkflowEvent(
            workflow_id=self.workflow.id,
            action=self.workflow.action,
            event_type=event_type,
            step=step,
            payload=payload,
        )
        await save_ai_workflow_event(event)

        if self.emitter is None:
            return

        message = {
            "action": self.workflow.action,
            "event": event_type,
            "workflow_id": self.workflow.id,
            "workflow_status": self.workflow.status.value,
            "step": step,
            "data": payload,
            "ts": event.ts.isoformat(),
        }

        try:
            await self.emitter(message)
        except Exception:
            # Streaming must never break core workflow persistence.
            return


def sanitize_http_error_message(detail: Any) -> str:
    if detail is None:
        return "Request failed"
    if isinstance(detail, str):
        return detail
    return str(detail)
