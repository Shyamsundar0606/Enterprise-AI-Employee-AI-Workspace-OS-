"""Bounded executor that preserves M7/M10 security boundaries."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.executor import ConnectorExecutor
from app.integrations.schemas import ApprovedActionContext, ConnectorContext
from app.models.workflow import Workflow, WorkflowStatus
from app.services.knowledge import KnowledgeError, KnowledgeService
from app.tools.executor import ToolExecutor
from app.tools.schemas import ToolContext
from app.workflows.service import WorkflowService
from app.workflows.state_machine import InvalidWorkflowTransition, require_workflow_transition


def is_retryable_workflow_failure(*, step_type: str, access_type: str | None, code: str) -> bool:
    """Allow retries only for bounded safe read/tool/knowledge transient failures."""
    if access_type in {"write", "destructive"}:
        return False
    if step_type not in {"connector", "tool", "knowledge"}:
        return False
    return code in {"connector_execution_failed", "tool_execution_failed", "knowledge_unavailable"}


class WorkflowExecutor:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.service = WorkflowService(session)

    async def _execute_with_retries(
        self,
        *,
        step: Any,
        execute_once: Callable[[], Awaitable[tuple[bool, dict[str, Any], str]]],
    ) -> tuple[bool, dict[str, Any], str]:
        """Run a safe step once plus its bounded number of additional retries.

        ``max_retries`` is the number of attempts allowed after the initial
        attempt.  The counter records retries already consumed, so a default
        value of two permits at most three total executions of a safe step.
        """
        while True:
            succeeded, payload, error_code = await execute_once()
            if succeeded:
                return succeeded, payload, error_code
            if (
                not is_retryable_workflow_failure(
                    step_type=step.step_type,
                    access_type=step.access_type,
                    code=error_code,
                )
                or step.retry_count >= step.max_retries
            ):
                return succeeded, payload, error_code
            step.retry_count += 1
            await self.session.flush()

    async def _fail_step(
        self, *, workflow: Workflow, step: Any, result: dict[str, Any]
    ) -> Workflow:
        step.status = "failed"
        step.result = result
        require_workflow_transition(workflow.status, WorkflowStatus.FAILED)
        workflow.status = WorkflowStatus.FAILED.value
        await self.service.record_event(workflow, "step_failed", {"step_id": step.id})
        await self.service.record_event(workflow, "workflow_failed")
        await self.session.commit()
        return workflow

    async def run(self, *, workflow_id: str, user_id: int, role: str) -> Workflow | None:
        workflow = await self.service.get(workflow_id=workflow_id, user_id=user_id)
        if workflow is None or workflow.status in {
            WorkflowStatus.CANCELLED,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
        }:
            return workflow
        if workflow.status == WorkflowStatus.PENDING.value:
            require_workflow_transition(workflow.status, WorkflowStatus.RUNNING)
            workflow.status = WorkflowStatus.RUNNING.value
            await self.service.record_event(workflow, "workflow_started")
        steps = await self.service.steps(workflow_id=workflow.id, user_id=user_id)
        steps_by_position = {item.position: item for item in steps}
        for step in steps:
            if step.status == "completed":
                continue
            if any(
                steps_by_position[dependency].status != "completed"
                for dependency in step.depends_on
            ):
                return await self._fail_step(
                    workflow=workflow,
                    step=step,
                    result={"error": "Workflow dependency did not complete"},
                )
            await self.service.record_event(workflow, "step_started", {"step_id": step.id})
            if step.step_type == "connector":
                connector_executor = ConnectorExecutor(session=self.session)
                try:
                    connector = connector_executor._registry.get(step.connector_id or "")
                    capability = next(
                        item for item in connector.capabilities if item.name == step.operation
                    )
                except Exception:
                    return await self._fail_step(
                        workflow=workflow,
                        step=step,
                        result={"error": "Workflow connector operation is unavailable"},
                    )
                if capability.access_type.value != "read":
                    await self.service.gate_approval(workflow=workflow, step=step)
                    return workflow

                async def execute_connector(
                    connector_executor: ConnectorExecutor = connector_executor,
                    step: Any = step,
                ) -> tuple[bool, dict[str, Any], str]:
                    result = await connector_executor.execute(
                        connector_id=step.connector_id or "",
                        operation=step.operation or "",
                        raw_arguments=step.arguments,
                        context=ConnectorContext(
                            authenticated_user_id=user_id,
                            role=role,
                            conversation_id=workflow.conversation_id,
                        ),
                    )
                    return (
                        result.status == "success",
                        result.model_dump(mode="json"),
                        result.error.code if result.error else "connector_execution_failed",
                    )

                succeeded, payload, _ = await self._execute_with_retries(
                    step=step, execute_once=execute_connector
                )
                if not succeeded:
                    return await self._fail_step(workflow=workflow, step=step, result=payload)
                step.result = payload
            elif step.step_type == "tool":
                tool_executor = ToolExecutor()

                async def execute_tool(
                    tool_executor: ToolExecutor = tool_executor,
                    step: Any = step,
                ) -> tuple[bool, dict[str, Any], str]:
                    result = await tool_executor.execute(
                        tool_name=step.arguments.get("tool_name", ""),
                        raw_input=step.arguments.get("input", {}),
                        context=ToolContext(
                            user_id=user_id,
                            role=role,
                            conversation_id=workflow.conversation_id or workflow.id,
                        ),
                    )
                    return (
                        result.status == "success",
                        result.model_dump(mode="json"),
                        result.error.code if result.error else "tool_execution_failed",
                    )

                succeeded, payload, _ = await self._execute_with_retries(
                    step=step, execute_once=execute_tool
                )
                if not succeeded:
                    return await self._fail_step(workflow=workflow, step=step, result=payload)
                step.result = payload
            elif step.step_type == "knowledge":
                query = str(step.arguments.get("query", "")).strip()
                if not query:
                    return await self._fail_step(
                        workflow=workflow,
                        step=step,
                        result={"error": "Knowledge query is required"},
                    )
                knowledge_service = KnowledgeService(self.session)

                async def execute_knowledge(
                    knowledge_service: KnowledgeService = knowledge_service,
                    query: str = query,
                ) -> tuple[bool, dict[str, Any], str]:
                    try:
                        matches = await knowledge_service.search(user_id=user_id, query=query)
                    except KnowledgeError:
                        return (
                            False,
                            {"error": "Knowledge retrieval failed safely"},
                            "knowledge_unavailable",
                        )
                    return (
                        True,
                        {
                            "results": [
                                {
                                    "content": item.content,
                                    "source": item.source.model_dump(mode="json"),
                                }
                                for item in matches
                            ]
                        },
                        "",
                    )

                succeeded, payload, _ = await self._execute_with_retries(
                    step=step, execute_once=execute_knowledge
                )
                if not succeeded:
                    return await self._fail_step(workflow=workflow, step=step, result=payload)
                step.result = payload
            else:
                return await self._fail_step(
                    workflow=workflow,
                    step=step,
                    result={"error": "Unsupported workflow step"},
                )
            step.status = "completed"
            workflow.current_step = step.position + 1
            await self.service.record_event(workflow, "step_completed", {"step_id": step.id})
            await self.session.flush()
        require_workflow_transition(workflow.status, WorkflowStatus.COMPLETED)
        workflow.status = WorkflowStatus.COMPLETED.value
        await self.service.record_event(workflow, "workflow_completed")
        await self.session.commit()
        return workflow

    async def resume_workflow(
        self, *, workflow_id: str, user_id: int, role: str
    ) -> Workflow | None:
        """Resume only owner-visible, non-terminal workflows from their first incomplete step."""
        workflow = await self.service.get(workflow_id=workflow_id, user_id=user_id)
        if workflow is None:
            return None
        if workflow.status == WorkflowStatus.WAITING_FOR_APPROVAL.value:
            raise InvalidWorkflowTransition("Workflow is waiting for a required approval")
        if workflow.status in {
            WorkflowStatus.CANCELLED.value,
            WorkflowStatus.COMPLETED.value,
            WorkflowStatus.FAILED.value,
        }:
            raise InvalidWorkflowTransition("Terminal workflow cannot be resumed")
        if workflow.status == WorkflowStatus.PENDING.value:
            require_workflow_transition(workflow.status, WorkflowStatus.RUNNING)
            workflow.status = WorkflowStatus.RUNNING.value
            await self.session.commit()
        await self.service.record_event(workflow, "workflow_resumed")
        return await self.run(workflow_id=workflow.id, user_id=user_id, role=role)

    async def execute_approved(
        self,
        *,
        workflow_id: str,
        step_id: str,
        user_id: int,
        role: str,
        approved: ApprovedActionContext,
    ) -> Workflow | None:
        workflow = await self.service.get(workflow_id=workflow_id, user_id=user_id)
        if workflow is None or workflow.status != WorkflowStatus.RUNNING.value:
            return workflow
        step = next(
            (
                item
                for item in await self.service.steps(workflow_id=workflow_id, user_id=user_id)
                if item.id == step_id
            ),
            None,
        )
        if step is None or step.status == "completed":
            return workflow
        result = await ConnectorExecutor(session=self.session).execute(
            connector_id=step.connector_id or "",
            operation=step.operation or "",
            raw_arguments=step.arguments,
            context=ConnectorContext(
                authenticated_user_id=user_id,
                role=role,
                conversation_id=workflow.conversation_id,
                metadata={"idempotency_key": approved.action_hash},
            ),
            approved_action=approved,
        )
        if result.status != "success":
            require_workflow_transition(workflow.status, WorkflowStatus.FAILED)
            workflow.status = WorkflowStatus.FAILED.value
            step.status = "failed"
            step.result = result.model_dump(mode="json")
            await self.session.commit()
            return workflow
        step.result = result.model_dump(mode="json")
        step.status = "completed"
        # The action hash already binds this marker to the persisted step and
        # immutable connector action, while fitting the database's 128-char key.
        step.idempotency_key = approved.action_hash
        workflow.current_step = step.position + 1
        await self.service.record_event(workflow, "approved_action_executed", {"step_id": step.id})
        await self.session.commit()
        return await self.run(workflow_id=workflow.id, user_id=user_id, role=role)
