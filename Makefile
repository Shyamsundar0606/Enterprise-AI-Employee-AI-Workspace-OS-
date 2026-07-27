.DEFAULT_GOAL := help
.PHONY: help up down logs build test lint format migrate migration frontend-lint

help:
	@echo "Available: up down logs build test lint format migrate migration frontend-lint"
up:
	docker compose up --build
down:
	docker compose down
logs:
	docker compose logs -f
build:
	docker compose build
test:
	docker compose run --rm backend pytest
lint:
	docker compose run --rm backend sh -c "ruff check . && black --check ."
format:
	docker compose run --rm backend sh -c "ruff check --fix . && black ."
migrate:
	docker compose run --rm backend alembic upgrade head
migration:
	docker compose run --rm backend alembic revision --autogenerate -m "$(message)"
frontend-lint:
	docker compose run --rm frontend npm run lint
