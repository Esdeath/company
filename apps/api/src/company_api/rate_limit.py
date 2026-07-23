"""Fixed-window, account-scoped rate limiting."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from company_api.models import RateLimitBucket


class RateLimiter(Protocol):
    async def consume(
        self,
        action: str,
        subject: str,
        *,
        limit: int,
        window: timedelta,
        now: datetime,
    ) -> bool: ...


class SqlAlchemyRateLimiter:
    """Stores rate-limit buckets with one short-lived transaction per action."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def consume(
        self,
        action: str,
        subject: str,
        *,
        limit: int,
        window: timedelta,
        now: datetime,
    ) -> bool:
        if limit < 1:
            raise ValueError("limit must be at least one")

        window_started_at = fixed_window_start(now, window)
        subject_hash = hashlib.sha256(subject.encode()).hexdigest()
        statement = (
            insert(RateLimitBucket)
            .values(
                action=action,
                subject_hash=subject_hash,
                window_started_at=window_started_at,
                count=1,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[
                    RateLimitBucket.action,
                    RateLimitBucket.subject_hash,
                    RateLimitBucket.window_started_at,
                ],
                set_={
                    "count": RateLimitBucket.count + 1,
                    "updated_at": now,
                },
                where=RateLimitBucket.count < limit,
            )
            .returning(RateLimitBucket.count)
        )

        async with self._session_factory() as session:
            await session.execute(
                delete(RateLimitBucket).where(
                    RateLimitBucket.action == action,
                    RateLimitBucket.window_started_at < window_started_at,
                )
            )
            count = (await session.execute(statement)).scalar_one_or_none()
            await session.commit()
        return count is not None


def fixed_window_start(now: datetime, window: timedelta) -> datetime:
    """Return the UTC start of the fixed bucket containing ``now``."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if window <= timedelta():
        raise ValueError("window must be positive")

    utc_now = now.astimezone(UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    return epoch + ((utc_now - epoch) // window) * window
