import asyncio
import hashlib
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.dialects import postgresql

from company_api.rate_limit import RateLimiter, SqlAlchemyRateLimiter, fixed_window_start


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str, datetime], int] = {}

    async def consume(
        self,
        action: str,
        subject: str,
        *,
        limit: int,
        window: timedelta,
        now: datetime,
    ) -> bool:
        bucket = (action, subject, fixed_window_start(now, window))
        count = self._buckets.get(bucket, 0)
        if count >= limit:
            return False
        self._buckets[bucket] = count + 1
        return True


def test_limiter_blocks_the_next_action_inside_the_window() -> None:
    limiter: RateLimiter = InMemoryRateLimiter()
    now = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)

    assert run(limiter.consume("comment", "user-1", limit=2, window=timedelta(minutes=1), now=now))
    assert run(limiter.consume("comment", "user-1", limit=2, window=timedelta(minutes=1), now=now))
    assert not run(
        limiter.consume("comment", "user-1", limit=2, window=timedelta(minutes=1), now=now)
    )
    assert run(limiter.consume("comment", "user-2", limit=2, window=timedelta(minutes=1), now=now))


class FakeResult:
    def scalar_one_or_none(self) -> int:
        return 1


class FakeSession:
    def __init__(self) -> None:
        self.statements: list[object] = []
        self.committed = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exc_type, exc_value, traceback

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        return FakeResult()

    async def commit(self) -> None:
        self.committed = True


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self._session = session

    def __call__(self) -> FakeSession:
        return self._session


def test_sql_limiter_hashes_subject_and_uses_an_atomic_upsert() -> None:
    session = FakeSession()
    limiter = SqlAlchemyRateLimiter(FakeSessionFactory(session))  # type: ignore[arg-type]
    now = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)

    assert run(
        limiter.consume(
            "password_reset",
            "reader@example.com",
            limit=3,
            window=timedelta(minutes=15),
            now=now,
        )
    )

    upsert = session.statements[1].compile(dialect=postgresql.dialect())  # type: ignore[union-attr]
    assert upsert.params["subject_hash"] == hashlib.sha256(
        b"reader@example.com"
    ).hexdigest()
    assert "reader@example.com" not in upsert.params.values()
    assert "ON CONFLICT (action, subject_hash, window_started_at) DO UPDATE" in str(upsert)
    assert "rate_limit_buckets.count <" in str(upsert)
    assert session.committed is True
