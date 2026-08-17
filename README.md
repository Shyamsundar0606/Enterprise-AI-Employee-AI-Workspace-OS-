# Enterprise AI Employee (AI Workspace OS)

Enterprise AI Employee is a modular workspace operating system for enterprise AI workflows. Milestones 1–7 provide the application foundation, authentication, chat and memory persistence, LLM provider layer, LangGraph runtime, and controlled tool execution.

## Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy async, Alembic, PostgreSQL, Redis
- Frontend: Next.js, React, TypeScript, Tailwind CSS
- Tooling: Docker Compose, Ruff, Black, pre-commit, pytest, GitHub Actions

## Quick start

1. Copy the environment template: `Copy-Item .env.example .env`
2. Replace development passwords in `.env` before using a shared environment.
3. Start: `docker compose up --build`
4. Open `http://localhost:3000`; API docs are at `http://localhost:8000/docs`.

## LLM provider layer

The backend now exposes a provider-agnostic LLM interface under `/api/v1/llm/*`.

- `GET /api/v1/llm/health`
- `GET /api/v1/llm/models`
- `POST /api/v1/llm/chat`
- `POST /api/v1/llm/stream`

Use `LLM_PROVIDER=OLLAMA`, `OLLAMA_URL=http://host.docker.internal:11434`, and `DEFAULT_MODEL=qwen3` for the first working provider.

## Safe tools

The GeneralAssistant can call explicitly registered, authenticated tools through a controlled execution layer. Milestone 7 includes:

- `calculator` — AST-restricted arithmetic only; arbitrary code, imports, calls, and attribute access are rejected.
- `current_time` — standard-library local time lookup for an IANA timezone.

Discover the safe tool catalog with authenticated `GET /api/v1/tools`. Tool calls are persisted as `tool` messages with sanitized JSON metadata. Shell, filesystem, arbitrary Python, browser, and unrestricted HTTP tools are intentionally unavailable.

## Enterprise knowledge base (RAG)

Authenticated users can upload TXT, Markdown, and text-based PDF documents through `POST /api/v1/knowledge/documents`. The ingestion pipeline validates the upload, stores it using a generated identifier, extracts text, deterministically chunks it, creates local embeddings, and persists user-owned chunks and vectors in PostgreSQL.

Knowledge search and agent retrieval always filter by the JWT-authenticated user. The agent receives retrieved evidence separately from conversation memory and returns source metadata with grounded responses. `GET`, `DELETE`, chunk listing, and `POST /api/v1/knowledge/search` are all authenticated.

Embeddings run locally through Ollama; no paid embedding API is required. Install the local model before document ingestion:

```bash
ollama pull nomic-embed-text
```

Configure `RAG_*`, `DOCUMENT_STORAGE_PATH`, and `EMBEDDING_*` variables from `.env.example`. PostgreSQL persists embedding vectors as JSON arrays and the repository applies user-filtered cosine similarity scoring, avoiding an additional vector-database service in this milestone.

## Commands

```bash
make up
make down
make logs
make test
make lint
make format
make migrate
```

## Local backend development

Install Python 3.12 dependencies from `backend/` with `pip install -e ".[dev]"`, then run `uvicorn app.main:app --reload`. When running outside Docker, use `localhost` rather than Compose service names in the connection URLs.

## Layout

```text
backend/   FastAPI service and database migrations
frontend/  Next.js web application
docker/    Container build definitions
docs/      Architecture documentation
```

Run `pre-commit install` once after installing backend development dependencies. Every change should pass `make lint` and `make test` before commit.

## Contact

Shyamsundar Sasikumar<br>
shyamsundar.sasikumar@gmail.com<br>
+33745604671
