"""Unit and API tests for secure knowledge-base ingestion and retrieval."""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import build_graph
from app.agents.nodes.llm_node import llm_node
from app.agents.state import create_initial_state
from app.llm.schemas import LLMChatResponse
from app.models.user import User
from app.services.chunking import TextChunker
from app.services.document_extraction import DocumentExtractor, DocumentExtractionError, ExtractedPage
from app.services.embeddings import EmbeddingError, EmbeddingService
from app.services.knowledge import DocumentStorage, KnowledgeError, KnowledgeService


class FakeEmbeddingProvider:
    async def embed(self, text: str) -> list[float]:
        normalized = text.lower()
        if "phoenix" in normalized or "budget" in normalized:
            return [1.0, 0.0]
        return [0.0, 1.0]


def _embedding_service() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider())


def _pdf_with_text(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode())
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_chunking_is_deterministic_and_preserves_page_metadata() -> None:
    chunker = TextChunker(chunk_size=5, overlap=2)
    pages = [ExtractedPage(content="abcdefghij", page_number=3)]
    first = chunker.chunk(pages)
    second = chunker.chunk(pages)
    assert [chunk.content for chunk in first] == ["abcde", "defgh", "ghij"]
    assert first == second
    assert all(chunk.page_number == 3 and chunk.content for chunk in first)


@pytest.mark.asyncio
async def test_text_markdown_and_pdf_extraction() -> None:
    extractor = DocumentExtractor()
    assert (await extractor.extract(content=b"# Phoenix", content_type="text/markdown"))[0].content == "# Phoenix"
    pages = await extractor.extract(
        content=_pdf_with_text("Project Phoenix has a budget of 200000 euros."),
        content_type="application/pdf",
    )
    assert pages[0].page_number == 1
    assert "Phoenix" in pages[0].content


@pytest.mark.asyncio
async def test_malformed_pdf_and_embedding_failures_are_safe() -> None:
    with pytest.raises(DocumentExtractionError, match="signature"):
        await DocumentExtractor().extract(content=b"not a pdf", content_type="application/pdf")

    class FailingProvider:
        async def embed(self, text: str) -> list[float]:
            raise RuntimeError("network secret")

    with pytest.raises(EmbeddingError, match="unavailable"):
        await EmbeddingService(FailingProvider()).embed("Phoenix")


@pytest.fixture()
async def session(tmp_path: Path) -> AsyncSession:
    db_path = tmp_path / "knowledge-unit.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["DOCUMENT_STORAGE_PATH"] = str(tmp_path / "documents")

    import app.config.settings as settings_module
    import app.database.session as session_module

    settings_module.get_settings.cache_clear()
    importlib.reload(session_module)
    await session_module.init_db()
    async with session_module.AsyncSessionFactory() as test_session:
        yield test_session


async def _user(session: AsyncSession, *, email: str, username: str) -> User:
    user = User(
        email=email,
        username=username,
        hashed_password="not-used",
        role="user",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await session.commit()
    return user


@pytest.mark.asyncio
async def test_ingestion_retrieval_and_user_isolation(session: AsyncSession, tmp_path: Path) -> None:
    user_a = await _user(session, email="a@example.com", username="usera")
    user_b = await _user(session, email="b@example.com", username="userb")
    service = KnowledgeService(
        session,
        embedding_service=_embedding_service(),
        storage=DocumentStorage(tmp_path / "storage"),
    )
    document = await service.ingest(
        user_id=user_a.id,
        filename="phoenix.txt",
        content_type="text/plain",
        content=b"Project Phoenix has a budget of 200000 euros and launches in September.",
    )
    assert document.status == "ready"
    assert document.chunk_count == 1
    assert len(await service.search(user_id=user_a.id, query="Phoenix budget")) == 1
    assert await service.search(user_id=user_b.id, query="Phoenix budget") == []
    assert await service.search(
        user_id=user_b.id, query="Phoenix budget", document_ids=[document.id]
    ) == []


@pytest.mark.asyncio
async def test_document_delete_removes_chunks_and_storage(session: AsyncSession, tmp_path: Path) -> None:
    user = await _user(session, email="delete@example.com", username="deleteuser")
    storage = DocumentStorage(tmp_path / "storage")
    service = KnowledgeService(session, embedding_service=_embedding_service(), storage=storage)
    document = await service.ingest(
        user_id=user.id,
        filename="delete.md",
        content_type="text/markdown",
        content=b"# Delete this knowledge",
    )
    assert (storage.root / document.stored_filename).exists()
    await service.delete_document(user_id=user.id, document_id=document.id)
    assert not (storage.root / document.stored_filename).exists()
    assert await service.repository.list_chunks(document_id=document.id, user_id=user.id) == []


@pytest.mark.asyncio
async def test_unsafe_uploads_are_rejected(session: AsyncSession, tmp_path: Path) -> None:
    user = await _user(session, email="unsafe@example.com", username="unsafeuser")
    service = KnowledgeService(
        session,
        embedding_service=_embedding_service(),
        storage=DocumentStorage(tmp_path / "storage"),
    )
    for filename, content_type, content in [
        ("../escape.txt", "text/plain", b"bad"),
        ("program.exe", "application/octet-stream", b"bad"),
        ("fake.txt", "application/pdf", b"%PDF-bad"),
        ("empty.txt", "text/plain", b""),
    ]:
        with pytest.raises(KnowledgeError):
            await service.ingest(
                user_id=user.id,
                filename=filename,
                content_type=content_type,
                content=content,
            )


@pytest.mark.asyncio
async def test_retrieved_context_is_added_to_llm_prompt() -> None:
    class FakeLLM:
        def __init__(self) -> None:
            self.message = ""

        async def chat(self, request):
            self.message = request.message
            return LLMChatResponse(
                conversation_id=request.conversation_id,
                response="200000 euros",
                provider="fake",
                model="fake",
            )

    service = FakeLLM()
    state = create_initial_state(
        conversation_id="rag-state", user_id=1, user_message="What is the Phoenix budget?",
        retrieved_context=[{"content": "Phoenix budget is 200000 euros."}],
        sources=[{"document_id": "doc-1"}],
    )
    result = await llm_node(state, service)
    assert "200000 euros" in service.message
    assert result["metadata"]["sources"] == [{"document_id": "doc-1"}]


@pytest.mark.asyncio
async def test_retrieval_and_calculator_use_the_existing_safe_tool() -> None:
    class FakeLLM:
        async def chat(self, request):
            assert "30000" in request.message
            return LLMChatResponse(
                conversation_id=request.conversation_id,
                response="15% of the documented budget is 30000 euros.",
                provider="fake",
                model="fake",
            )

    state = create_initial_state(
        conversation_id="rag-calculator",
        user_id=1,
        user_message="What is 15% of that budget?",
        retrieved_context=[{"content": "Project Phoenix has a budget of 200000 euros."}],
    )
    state["user_role"] = "user"
    result = await build_graph(FakeLLM()).ainvoke(state)
    assert result["tool_result"]["output"] == {"result": 30000.0}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    db_path = tmp_path / "knowledge-api.db"
    storage_path = tmp_path / "documents"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["DOCUMENT_STORAGE_PATH"] = str(storage_path)
    os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"

    import app.api.routes.knowledge as knowledge_routes
    import app.config.settings as settings_module
    import app.database.redis as redis_module
    import app.database.session as session_module
    import app.main as main_module

    class TestKnowledgeService(KnowledgeService):
        def __init__(self, db_session: AsyncSession) -> None:
            super().__init__(
                db_session,
                embedding_service=_embedding_service(),
                storage=DocumentStorage(storage_path),
            )

    redis_module._redis_client = None
    settings_module.get_settings.cache_clear()
    importlib.reload(session_module)
    importlib.reload(main_module)
    monkeypatch.setattr(knowledge_routes, "KnowledgeService", TestKnowledgeService)
    with TestClient(main_module.app) as test_client:
        yield test_client


def _token(client: TestClient, email: str, username: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": "secret123"},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_authenticated_upload_search_and_ownership_api(client: TestClient) -> None:
    assert client.post("/api/v1/knowledge/documents").status_code == 401
    token_a = _token(client, "api-a@example.com", "apia")
    token_b = _token(client, "api-b@example.com", "apib")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    upload = client.post(
        "/api/v1/knowledge/documents",
        headers=headers_a,
        files={
            "file": (
                "phoenix.txt",
                b"Project Phoenix has a budget of 200000 euros.",
                "text/plain",
            )
        },
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]
    assert client.get(f"/api/v1/knowledge/documents/{document_id}", headers=headers_b).status_code == 404
    search = client.post(
        "/api/v1/knowledge/search",
        headers=headers_a,
        json={"query": "What is the Phoenix budget?", "document_ids": [document_id]},
    )
    assert search.status_code == 200
    assert search.json()["results"][0]["source"]["document_id"] == document_id
    cross_search = client.post(
        "/api/v1/knowledge/search",
        headers=headers_b,
        json={"query": "Phoenix budget", "document_ids": [document_id]},
    )
    assert cross_search.json()["results"] == []
    assert client.delete(f"/api/v1/knowledge/documents/{document_id}", headers=headers_b).status_code == 404
    assert client.delete(f"/api/v1/knowledge/documents/{document_id}", headers=headers_a).status_code == 200
