import importlib
import os
from collections.abc import Iterator

import pytest
from app.llm.factory import ProviderFactory
from app.llm.providers.ollama import OllamaProvider
from app.llm.schemas import LLMChatRequest, LLMHealthResponse, LLMModelInfo
from app.llm.service import LLMService
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: pytest.TempPathFactory) -> Iterator[TestClient]:
    db_path = tmp_path / "llm-test.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"
    os.environ["JWT_ALGORITHM"] = "HS256"
    os.environ["LLM_PROVIDER"] = "OLLAMA"
    os.environ["OLLAMA_URL"] = "http://example.test:11434"
    os.environ["DEFAULT_MODEL"] = "qwen3"

    import app.config.settings as settings_module
    import app.database.redis as redis_module
    import app.database.session as session_module
    import app.main as main_module

    # Reset Redis client to avoid event loop conflicts between tests
    redis_module._redis_client = None
    settings_module.get_settings.cache_clear()
    importlib.reload(session_module)
    importlib.reload(main_module)

    with TestClient(main_module.app) as test_client:
        yield test_client


def test_provider_factory_uses_ollama() -> None:
    provider = ProviderFactory.create_provider()
    assert isinstance(provider, OllamaProvider)


@pytest.mark.asyncio
async def test_llm_service_chat_and_health() -> None:
    class FakeProvider:
        async def generate(
            self, *, prompt: str, model: str, temperature: float, max_tokens: int, timeout: float
        ) -> str:
            return "fake response"

        async def stream(
            self, *, prompt: str, model: str, temperature: float, max_tokens: int, timeout: float
        ):
            yield "chunk"

        async def list_models(self) -> list[LLMModelInfo]:
            return [LLMModelInfo(name="qwen3", provider="ollama")]

        async def health(self) -> LLMHealthResponse:
            return LLMHealthResponse(provider="ollama", model="qwen3", status="ok", latency_ms=5.0)

        async def embeddings(self, *, text: str, model: str, timeout: float) -> list[float]:
            return [0.1, 0.2]

    service = LLMService(provider=FakeProvider())
    response = await service.chat(
        LLMChatRequest(conversation_id="conv-1", message="hello", provider="ollama", model="qwen3")
    )
    assert response.response == "fake response"
    health = await service.health()
    assert health.status == "ok"


def test_health_endpoint_uses_dependency(monkeypatch, client: TestClient) -> None:
    import app.api.routes.llm as llm_routes

    class FakeService:
        async def health(self) -> LLMHealthResponse:
            return LLMHealthResponse(provider="ollama", model="qwen3", status="ok", latency_ms=3.0)

        async def list_models(self) -> list[LLMModelInfo]:
            return [LLMModelInfo(name="qwen3", provider="ollama")]

        async def chat(self, request: LLMChatRequest) -> object:
            return object()

        async def stream(self, request: LLMChatRequest):
            yield {"chunk": "hello"}

    monkeypatch.setattr(llm_routes, "get_llm_service", lambda: FakeService())
    response = client.get("/api/v1/llm/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_models_endpoint(monkeypatch, client: TestClient) -> None:
    import app.api.routes.llm as llm_routes

    class FakeService:
        async def health(self) -> LLMHealthResponse:
            return LLMHealthResponse(provider="ollama", model="qwen3", status="ok", latency_ms=3.0)

        async def list_models(self) -> list[LLMModelInfo]:
            return [LLMModelInfo(name="qwen3", provider="ollama")]

        async def chat(self, request: LLMChatRequest) -> object:
            return object()

        async def stream(self, request: LLMChatRequest):
            yield {"chunk": "hi"}

    monkeypatch.setattr(llm_routes, "get_llm_service", lambda: FakeService())
    response = client.get("/api/v1/llm/models")
    assert response.status_code == 200
    assert response.json()["models"][0]["name"] == "qwen3"


def test_chat_endpoint(monkeypatch, client: TestClient) -> None:
    import app.api.routes.llm as llm_routes

    class FakeService:
        async def health(self) -> LLMHealthResponse:
            return LLMHealthResponse(provider="ollama", model="qwen3", status="ok", latency_ms=3.0)

        async def list_models(self) -> list[LLMModelInfo]:
            return [LLMModelInfo(name="qwen3", provider="ollama")]

        async def chat(self, request: LLMChatRequest):
            return {
                "conversation_id": request.conversation_id,
                "response": "hi",
                "provider": request.provider,
            }

        async def stream(self, request: LLMChatRequest):
            yield {"chunk": "hi"}

    monkeypatch.setattr(llm_routes, "get_llm_service", lambda: FakeService())
    response = client.post(
        "/api/v1/llm/chat",
        json={"conversation_id": "conv-1", "message": "hello"},
    )
    assert response.status_code == 200
    assert response.json()["response"] == "hi"


def test_stream_endpoint(monkeypatch, client: TestClient) -> None:
    import app.api.routes.llm as llm_routes

    class FakeService:
        async def health(self) -> LLMHealthResponse:
            return LLMHealthResponse(provider="ollama", model="qwen3", status="ok", latency_ms=3.0)

        async def list_models(self) -> list[LLMModelInfo]:
            return [LLMModelInfo(name="qwen3", provider="ollama")]

        async def chat(self, request: LLMChatRequest):
            return {"response": "hi"}

        async def stream(self, request: LLMChatRequest):
            yield {"chunk": "hi"}

    monkeypatch.setattr(llm_routes, "get_llm_service", lambda: FakeService())
    response = client.post(
        "/api/v1/llm/stream",
        json={"conversation_id": "conv-1", "message": "hello"},
        headers={"accept": "text/event-stream"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
