# Convenience targets. Backend commands run through uv inside backend/.
.PHONY: up down logs ps lint fmt types test itest check web-dev web-lint web-test web-e2e api-contract

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

# ── Frontend ──
web-dev:       ## Vite dev server on :5173 (proxies the API on :8000)
	cd frontend && npm run dev
web-lint:
	cd frontend && npm run lint && npm run format:check && npm run typecheck
web-test:      ## Frontend unit tests (no services needed)
	cd frontend && npm test
web-e2e:       ## Browser e2e against the running stack (:8080)
	cd frontend && npm run e2e
api-contract:  ## Re-export the OpenAPI schema and regenerate frontend API types
	cd backend && uv run python -m app.cli openapi && cd ../frontend && npm run gen:api
