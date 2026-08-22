"""Focused execution and isolation tests for Knowledge workflow steps."""

from pathlib import Path

import pytest
from app.models.user import User
from app.services.embeddings import EmbeddingService
from app.services.knowledge import DocumentStorage, KnowledgeService
from app.workflows.executor import WorkflowExecutor
from app.workflows.service import WorkflowService


class FakeEmbeddingProvider:
    """Deterministic local embeddings; no Ollama service is involved in these tests."""

    async def embed(self, text: str) -> list[float]:
        normalized = text.lower()
        if "phoenix" in normalized or "budget" in normalized:
            return [1.0, 0.0]
        return [0.0, 1.0]


@pytest.mark.asyncio
async def test_knowledge_step_persists_owned_results_and_sources(
    test_user, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A workflow reuses M8 retrieval and cannot surface another user's document."""
    import app.workflows.executor as executor_module
    from app.database.session import AsyncSessionFactory

    class TestKnowledgeService(KnowledgeService):
        def __init__(self, session) -> None:
            super().__init__(
                session,
                embedding_service=EmbeddingService(FakeEmbeddingProvider()),
                storage=DocumentStorage(tmp_path / "documents"),
            )

    monkeypatch.setattr(executor_module, "KnowledgeService", TestKnowledgeService)
    async with AsyncSessionFactory() as session:
        other_user = User(
            email=f"knowledge-other-{test_user.id}@example.com",
            username=f"knowledgeother{test_user.id}",
            hashed_password="not-used",
            role="user",
            is_active=True,
        )
        session.add(other_user)
        await session.flush()
        await session.commit()

        knowledge = TestKnowledgeService(session)
        owned_document = await knowledge.ingest(
            user_id=test_user.id,
            filename="phoenix.txt",
            content_type="text/plain",
            content=b"Project Phoenix has a budget of 200000 euros.",
        )
        other_document = await knowledge.ingest(
            user_id=other_user.id,
            filename="private.txt",
            content_type="text/plain",
            content=b"Project Phoenix private budget is 999999 euros.",
        )

        service = WorkflowService(session)
        workflow = await service.create(
            user_id=test_user.id,
            name="Retrieve owned Phoenix context",
            steps=[
                {
                    "name": "Search knowledge",
                    "step_type": "knowledge",
                    "arguments": {"query": "Phoenix budget"},
                }
            ],
        )
        completed = await WorkflowExecutor(session).run(
            workflow_id=workflow.id, user_id=test_user.id, role="user"
        )
        step = (await service.steps(workflow_id=workflow.id, user_id=test_user.id))[0]

        other_workflow = await service.create(
            user_id=other_user.id,
            name="Isolated search",
            steps=[
                {
                    "name": "Search knowledge",
                    "step_type": "knowledge",
                    "arguments": {"query": "Phoenix budget"},
                }
            ],
        )
        other_completed = await WorkflowExecutor(session).run(
            workflow_id=other_workflow.id, user_id=other_user.id, role="user"
        )
        other_step = (await service.steps(workflow_id=other_workflow.id, user_id=other_user.id))[0]

    assert completed is not None and completed.status == "completed"
    assert completed.current_step == 1
    assert step.status == "completed"
    assert step.result is not None
    assert step.result["results"][0]["content"] == "Project Phoenix has a budget of 200000 euros."
    assert step.result["results"][0]["source"]["document_id"] == owned_document.id
    assert other_document.id not in str(step.result)

    assert other_completed is not None and other_completed.status == "completed"
    assert other_step.result is not None
    assert other_document.id in {
        item["source"]["document_id"] for item in other_step.result["results"]
    }
    assert owned_document.id not in str(other_step.result)


@pytest.mark.asyncio
async def test_empty_knowledge_query_fails_safely(test_user) -> None:
    from app.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        workflow = await WorkflowService(session).create(
            user_id=test_user.id,
            name="Knowledge validation",
            steps=[{"name": "Search", "step_type": "knowledge", "arguments": {}}],
        )
        result = await WorkflowExecutor(session).run(
            workflow_id=workflow.id, user_id=test_user.id, role="user"
        )
        assert result is not None and result.status == "failed"
        steps = await WorkflowService(session).steps(workflow_id=workflow.id, user_id=test_user.id)
        assert steps[0].result == {"error": "Knowledge query is required"}
