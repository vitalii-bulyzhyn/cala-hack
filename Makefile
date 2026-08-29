SHELL := /bin/bash

PYTHON ?= python3.12
BACKEND_VENV := dev/backend/.venv
BACKEND_PYTHON := $(BACKEND_VENV)/bin/python
BACKEND_PIP := $(BACKEND_VENV)/bin/pip

.DEFAULT_GOAL := help

.PHONY: help env setup backend-install frontend-install dev infra-up infra-down down reset logs migrate backend-dev worker-dev frontend-dev backend-check frontend-check compose-check check smoke

help: ## Show the available commands
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target>\n\n"} /^[a-zA-Z_-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

env: ## Create .env from the safe template when it does not exist
	@test -f .env || { cp .env.example .env; echo "Created .env from .env.example"; }

setup: env backend-install frontend-install ## Install local backend and frontend dependencies

$(BACKEND_PYTHON):
	$(PYTHON) -m venv $(BACKEND_VENV)

backend-install: $(BACKEND_PYTHON) ## Install backend and development dependencies
	$(BACKEND_PIP) install --upgrade pip
	$(BACKEND_PIP) install -e 'dev/backend[dev]'

frontend-install: ## Install locked frontend dependencies
	npm --prefix dev/frontend ci

dev: env ## Start the complete hot-reloading stack
	docker compose up --build

infra-up: env ## Start Postgres, Redis, and pgAdmin only
	docker compose up -d postgres redis pgadmin

infra-down: ## Stop local infrastructure without deleting data
	docker compose stop postgres redis pgadmin

down: ## Stop the complete stack without deleting data
	docker compose down

reset: ## Delete local containers and database/Redis/pgAdmin volumes
	docker compose down --volumes --remove-orphans

logs: ## Follow logs from the complete stack
	docker compose logs --follow

migrate: env backend-install ## Apply backend database migrations
	cd dev/backend && .venv/bin/alembic upgrade head

backend-dev: migrate ## Run FastAPI locally with reload
	$(BACKEND_VENV)/bin/uvicorn app.main:app --app-dir dev/backend --reload --host 0.0.0.0 --port $${BACKEND_PORT:-8000} --env-file .env

worker-dev: migrate ## Run the generation worker locally
	$(BACKEND_PYTHON) -m app.worker

frontend-dev: env frontend-install ## Run Next.js locally with reload
	@set -a; source ./.env; set +a; cd dev/frontend && npm run dev

backend-check: backend-install ## Lint, format-check, and test the backend
	$(BACKEND_VENV)/bin/ruff check dev/backend
	$(BACKEND_VENV)/bin/ruff format --check dev/backend
	$(BACKEND_VENV)/bin/pytest dev/backend
	cd dev/backend && .venv/bin/alembic upgrade head --sql >/dev/null

frontend-check: frontend-install ## Lint, type-check, and build the frontend
	npm --prefix dev/frontend run lint
	npm --prefix dev/frontend run typecheck
	npm --prefix dev/frontend run build

compose-check: env ## Validate the resolved Compose configuration
	docker compose config --quiet

check: backend-check frontend-check compose-check ## Run all repository checks

smoke: env ## Build the stack and verify every local service boundary
	docker compose up -d --build --wait
	@set -a; source ./.env; set +a; \
		curl --fail --silent --show-error --retry 10 --retry-delay 1 "http://127.0.0.1:$${BACKEND_PORT:-8000}/api/v1/health/live" >/dev/null; \
		curl --fail --silent --show-error --retry 10 --retry-delay 1 "http://127.0.0.1:$${BACKEND_PORT:-8000}/api/v1/health/ready" >/dev/null; \
		curl --fail --silent --show-error --retry 10 --retry-delay 1 "http://127.0.0.1:$${FRONTEND_PORT:-3000}/" >/dev/null; \
		curl --fail --silent --show-error --retry 10 --retry-delay 1 "http://127.0.0.1:$${FRONTEND_PORT:-3000}/api/backend-health" >/dev/null; \
		curl --fail --silent --show-error --retry 10 --retry-delay 1 "http://127.0.0.1:$${PGADMIN_PORT:-5050}/misc/ping" >/dev/null
	docker compose exec -T postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -c "SELECT 1"' >/dev/null
	@test "$$(docker compose exec -T redis redis-cli ping | tr -d '\r')" = "PONG"
	docker compose exec -T worker python -m app.worker.healthcheck
	docker compose exec -T backend alembic check
	docker compose exec -T backend python scripts/smoke_itinerary.py
	@echo "Smoke test passed"
