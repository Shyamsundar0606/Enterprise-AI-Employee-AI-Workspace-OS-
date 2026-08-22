# Production operations

Set `APP_ENV=production`, an explicit comma-separated `CORS_ORIGINS` list, and a
strong `JWT_SECRET_KEY` before deployment. Never place credentials in source or
logs. Start with `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`.

`/health` confirms process liveness; `/ready` verifies PostgreSQL and Redis;
`/metrics` exposes low-cardinality, secret-free text metrics. Ollama is optional:
non-AI routes stay available when it is offline, while AI calls fail safely.

Run `alembic upgrade head` before deployment. Back up PostgreSQL with a
consistent `pg_dump`, validate restoration in an isolated environment, and do
not perform automated destructive migration rollbacks. Redis is cache/rate-limit
state; PostgreSQL remains the source of truth. Preserve the document volume.
