# Milestone 1 architecture

The backend follows a layered, dependency-directed structure. HTTP concerns live in `app/api`; application orchestration belongs in `app/services`; persistence concerns remain in `app/database` and `app/models`; transport contracts live in `app/schemas`. Domain modules for agents, memory, tools, and graph workflows are deliberately deferred to future milestones.

Pydantic Settings parses environment configuration once. Readiness verifies PostgreSQL and Redis, preventing the service from reporting ready when required infrastructure is unavailable.
