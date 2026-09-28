# Convenience targets. Backend commands run through uv inside backend/.
.PHONY: up down logs ps build lint fmt types test itest check

up:            ## Start the full stack and wait until healthy
	docker compose up -d --build --wait
down:          ## Stop the stack (keeps volumes)
	docker compose down
logs:
	docker compose logs -f --tail=100
ps:
	docker compose ps
lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
fmt:
	cd backend && uv run ruff format . && uv run ruff check . --fix
types:
	cd backend && uv run mypy app
test:          ## Unit tests (no services needed)
	cd backend && uv run pytest
itest:         ## Integration tests (stack must be up)
	cd backend && uv run pytest -m integration
check:         ## Readiness + worker round-trip from inside the stack
	docker compose exec -T worker python -m app.cli check --worker
