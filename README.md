# Enterprise AI Employee (AI Workspace OS)

Enterprise AI Employee is a modular workspace operating system for enterprise AI workflows. This repository currently contains **Milestone 1**: the production-oriented application foundation. AI agents and integrations are intentionally out of scope until later milestones.

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
