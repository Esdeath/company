#!/bin/sh
set -eu

uv run --no-sync alembic upgrade head
exec uv run --no-sync uvicorn --factory company_api.main:create_app --host 0.0.0.0 --port 8000
