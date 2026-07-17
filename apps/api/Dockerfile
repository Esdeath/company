FROM ghcr.io/astral-sh/uv:0.11.29 AS uv
FROM python:3.13-slim-bookworm AS runtime

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 app \
    && chown -R app:app /app

ENV PATH="/app/.venv/bin:$PATH"

USER app

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "--factory", "company_api.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
