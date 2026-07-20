FROM ghcr.io/astral-sh/uv:0.11.29 AS uv
FROM python:3.13-slim-bookworm AS runtime

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY --chmod=755 docker-entrypoint.sh /app/docker-entrypoint.sh
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /data/content \
    && chown -R app:app /app /data/content

ENV PATH="/app/.venv/bin:$PATH"

USER app

EXPOSE 8000

CMD ["/app/docker-entrypoint.sh"]
