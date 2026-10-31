.PHONY: setup db db-down migrate backend frontend test

setup:            ## install backend and frontend dependencies
	python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt
	cd frontend && npm install

db:               ## start PostgreSQL + pgvector
	docker compose up -d --wait db

db-down:
	docker compose down

migrate:          ## apply database migrations
	cd backend && .venv/bin/alembic upgrade head

backend:          ## FastAPI dev server on :8000
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:         ## Vite dev server on :5173
	cd frontend && npm run dev

test:
	cd backend && RUN_DB_TESTS=1 .venv/bin/python -m pytest -q
	cd frontend && npm run lint && npm run build
