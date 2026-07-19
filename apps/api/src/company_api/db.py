from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from company_api.config import Settings


def create_engine_and_session_factory(
    settings: Settings,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory


class ReadinessProbe(Protocol):
    async def check(self) -> None: ...


class SqlAlchemyReadinessProbe:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def check(self) -> None:
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
