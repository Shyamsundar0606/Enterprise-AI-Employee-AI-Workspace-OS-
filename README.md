# Enterprise AI Employee (AI Workspace OS)

Enterprise AI Employee is a production-hardened, local-first AI Workspace OS. It combines authenticated chat, memory, RAG, bounded multi-agent execution, safe tools, controlled integrations, and durable human-approved workflows without requiring a paid AI provider.

## Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy async, Alembic, PostgreSQL, Redis
- Frontend: Next.js, React, TypeScript, Tailwind CSS
- Operations: structured JSON logging, request correlation, health/readiness, metrics, Redis rate limiting, security headers, and production Compose support
- Tooling: Docker Compose, Ruff, Black, pre-commit, pytest, Alembic, GitHub Actions

## Quick start

1. Copy the environment template: `Copy-Item .env.example .env`
2. Replace development passwords in `.env` before using a shared environment.
3. Start: `docker compose up -d --build`
4. Open `http://localhost:3000`; API docs are at `http://localhost:8000/docs`.
5. Check readiness: `http://localhost:8000/api/v1/ready`.

For a production-oriented Compose profile, use:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

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

## Multi-agent delegation

The existing LangGraph runtime uses a bounded deterministic supervisor with four explicitly registered roles: `general`, `knowledge`, `data`, and `planner`. The supervisor derives trusted identity from the authenticated runtime, limits delegation with `MAX_AGENT_DELEGATIONS` and `MAX_AGENT_STEPS`, and preserves source metadata, memory, and tool restrictions. No specialist can register arbitrary agents, access another user's documents, or bypass the shared ToolExecutor.

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

## Enterprise integrations and MCP

Milestone 10 adds a separate, policy-enforced connector boundary at `/api/v1/integrations`. `ConnectorRegistry` exposes only statically registered local connectors; `ConnectorExecutor` validates input, derives identity from JWT authentication, redacts sensitive fields, limits results, and writes safe audit events. Local Email, Calendar, Workspace, GitHub-style, and MCP-compatible connectors are free to test.

Reads may run automatically. Write and destructive capabilities always return `approval_required` until a Milestone 11 persisted approval is consumed. The workspace connector confines requests to a per-user sandbox and blocks traversal, absolute paths, symlinks, and secret-like filenames. MCP tools/resources are allow-listed and their data is untrusted.

## Autonomous workflows and approvals

Milestone 11 persists owner-scoped workflows, ordered steps, approval requests, dependencies, retry limits, and safe lifecycle audit events in PostgreSQL. `WorkflowExecutor` runs allow-listed READ connectors, tools, and user-isolated knowledge retrieval; WRITE and DESTRUCTIVE operations pause until `ApprovalService` records an explicit decision.

Approvals bind a redacted immutable action snapshot to a SHA-256 action hash. The backend creates `ApprovedActionContext`; clients cannot submit an approval flag, action hash, or owner identity. `ConnectorExecutor` revalidates the persisted approval, workflow/step state, and exact action before consequential execution. Completed steps and connector idempotency keys prevent replay.

Workflow APIs are under `/api/v1/workflows`; approvals are under `/api/v1/approvals`; owner-scoped safe lifecycle events are available as SSE at `/api/v1/workflows/{workflow_id}/events`. The minimal local UI is `/workflows`. All connectors remain local/mock-first; credentials, prompts, JWTs, and hidden reasoning are never recorded in workflow audit events.

## Production operations

Milestone 12 adds production hardening while preserving the M1–M11 security boundaries.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/health` | Process liveness |
| `GET /api/v1/ready` | PostgreSQL and Redis readiness |
| `GET /metrics` | Low-cardinality, Prometheus-compatible operational metrics |
| `GET /api/v1/workflows/{id}/events` | Owner-scoped safe workflow SSE events |

Request IDs are accepted only when safely formatted, generated otherwise, included in structured logs, and returned in `X-Request-ID`. Configured CORS, CSP/frame protections, content-type protections, bounded request bodies, and Redis-backed rate limits protect abuse-sensitive HTTP paths. The metrics endpoint deliberately avoids user IDs, document contents, prompts, and other high-cardinality or sensitive labels.

For production, set explicit `APP_ENV=production`, `JWT_SECRET_KEY` (32+ characters), PostgreSQL `DATABASE_URL`, Redis `REDIS_URL`, and comma-separated `CORS_ORIGINS`. Never commit a real `.env` file or credentials. See [operations](docs/operations.md) for deployment, backups/restores, migrations, rollback considerations, incident basics, and local-Ollama behavior.

## Verification status

The final M12 verification completed with **130 backend tests passing**, Ruff passing, Black formatting clean, and Alembic at `20260817_workflow_audit_events` (head). Docker services for backend, frontend, PostgreSQL, and Redis are healthy; the root UI and `/workflows` both return HTTP 200.

## Contact

Shyamsundar Sasikumar<br>
shyamsundar.sasikumar@gmail.com<br>
+33745604671
