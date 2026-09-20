SHELL := /bin/bash

.PHONY: dev down demo-data seed-demo test lint backend-test frontend-test clean-data smoke migrate validate-gpu verify

dev:
	docker compose up --build

down:
	docker compose down

demo-data:
	docker compose run --rm --build backend python -m app.scripts.generate_demo_data

seed-demo:
	docker compose run --rm --build backend python -m app.scripts.seed_demo_case

backend-test:
	docker compose run --rm --build backend python -m pytest -v

frontend-test:
	docker compose run --rm --build frontend npm test -- --run

test: backend-test frontend-test

lint:
	docker compose run --rm --build backend ruff check app tests
	docker compose run --rm --build frontend npm run lint

smoke:
	bash scripts/smoke.sh

migrate:
	cd backend && alembic upgrade head

validate-gpu:
	./scripts/validate_gpu.sh

verify:
	cd backend && ruff check app tests && pytest -q
	cd frontend && npm run lint && npm test -- --run && npm run build
	docker compose config >/dev/null
	docker compose --profile gpu config >/dev/null

clean-data:
	rm -rf data/cases/* data/neuroannotate.db data/smoke-*
	mkdir -p data/cases
	touch data/cases/.gitkeep
