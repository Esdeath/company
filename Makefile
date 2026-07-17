.PHONY: setup dev-infra dev check compose-up compose-smoke compose-down

setup:
	corepack pnpm install --frozen-lockfile
	cd apps/api && uv sync --frozen

dev-infra:
	docker compose up -d postgres

dev:
	corepack pnpm run dev

check:
	node --test tests/*.test.mjs
	corepack pnpm run check
	cd apps/api && uv run ruff check .
	cd apps/api && uv run mypy src
	cd apps/api && uv run pytest

compose-up:
	docker compose up --build -d

compose-smoke:
	./scripts/compose-smoke.sh

compose-down:
	docker compose down
