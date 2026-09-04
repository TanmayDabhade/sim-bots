SHELL := /bin/sh
PYTHON := backend/.venv/bin/python
PIP := backend/.venv/bin/pip

.PHONY: install test check db-up migrate init-db seed arena-once dev-backend dev-frontend up down

install:
	python3 -m venv backend/.venv
	$(PIP) install -e './backend[dev]'
	cd frontend && npm install

test:
	cd backend && .venv/bin/pytest -q
	cd frontend && npm test -- --run

check:
	cd backend && .venv/bin/ruff check . && .venv/bin/mypy app && .venv/bin/pytest -q
	cd frontend && npm test -- --run && npm run lint && npm run typecheck && npm run build

db-up:
	docker compose up -d db

migrate:
	cd backend && .venv/bin/alembic upgrade head

init-db: migrate
	cd backend && .venv/bin/python -m app.cli init-db

seed: init-db
	cd backend && .venv/bin/python -m app.cli seed

arena-once: init-db
	cd backend && .venv/bin/python -m app.cli arena-once

dev-backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

up:
	docker compose up --build

down:
	docker compose down

