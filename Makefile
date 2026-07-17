UV ?= uv
PNPM ?= corepack pnpm

.PHONY: setup dev-infra dev dev-web dev-admin dev-api check compose-up compose-smoke compose-down require-env

setup:
	@printf 'Expected Node 24.18.0; found '
	@node --version
	@printf 'Expected pnpm 10.34.5; found '
	@$(PNPM) --version
	@printf 'Expected uv 0.11.29; found '
	@$(UV) --version
	@printf 'Docker: '
	@docker --version
	@printf 'Docker Compose: '
	@docker compose version
	$(PNPM) install --frozen-lockfile
	cd apps/api && $(UV) sync --frozen
	@printf 'Expected Python 3.13; found '
	@cd apps/api && $(UV) run python --version

require-env:
	@test -f .env || { echo 'Missing .env. Run: cp .env.example .env' >&2; exit 1; }

dev-infra: require-env
	docker compose --env-file .env up -d postgres

dev: require-env
	+$(MAKE) -j3 dev-web dev-admin dev-api

dev-web:
	$(PNPM) --filter @company/web dev

dev-admin:
	$(PNPM) --filter @company/admin dev

dev-api:
	cd apps/api && $(UV) run --env-file ../../.env uvicorn --factory company_api.main:create_app --reload --host 0.0.0.0 --port 8000

check:
	node --test tests/docs.test.mjs tests/prototype.test.mjs tests/scaffold.test.mjs
	$(PNPM) --filter @company/web check
	$(PNPM) --filter @company/admin check
	cd apps/api && $(UV) run ruff check .
	cd apps/api && $(UV) run ruff format --check .
	cd apps/api && $(UV) run mypy src
	cd apps/api && $(UV) run pytest

compose-up: require-env
	docker compose --env-file .env up --build -d

compose-smoke:
	./scripts/compose-smoke.sh

compose-down:
	docker compose --env-file .env down
