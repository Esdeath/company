import asyncio
import contextlib
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from company_api.mailer import EmailMessage, Mailer
from company_api.models import EmailOutbox, User, UserStatus, UserToken, UserTokenPurpose

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EmailJob:
    id: UUID
    token_id: UUID | None
    template: str
    recipient: str
    payload: dict[str, object]
    attempts: int


class EmailOutboxRepository(Protocol):
    async def claim_batch(
        self,
        now: datetime,
        lease_id: UUID,
        limit: int,
    ) -> list[EmailJob]: ...

    async def mark_sent(self, job_id: UUID, lease_id: UUID, sent_at: datetime) -> bool: ...

    async def reschedule(
        self,
        job_id: UUID,
        lease_id: UUID,
        now: datetime,
        error: Exception,
    ) -> bool: ...


class SqlAlchemyEmailOutboxRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_attempts: int = 8,
        lease_seconds: int = 60,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max attempts must be positive")
        if lease_seconds < 1:
            raise ValueError("lease seconds must be positive")
        self._session_factory = session_factory
        self._max_attempts = max_attempts
        self._lease_duration = timedelta(seconds=lease_seconds)

    async def claim_batch(
        self,
        now: datetime,
        lease_id: UUID,
        limit: int,
    ) -> list[EmailJob]:
        if limit < 1:
            return []
        async with self._session_factory() as session:
            valid_reply_recipient = exists(
                select(UserToken.id)
                .join(User, User.id == UserToken.user_id)
                .where(
                    UserToken.id == EmailOutbox.token_id,
                    UserToken.purpose == UserTokenPurpose.UNSUBSCRIBE,
                    UserToken.consumed_at.is_(None),
                    User.status == UserStatus.ACTIVE,
                    User.reply_email_enabled.is_(True),
                )
            )
            statement = (
                select(EmailOutbox)
                .where(
                    EmailOutbox.sent_at.is_(None),
                    EmailOutbox.available_at <= now,
                    EmailOutbox.attempts < self._max_attempts,
                    or_(
                        EmailOutbox.lease_id.is_(None),
                        EmailOutbox.lease_expires_at <= now,
                    ),
                    or_(
                        EmailOutbox.template != "comment_reply",
                        and_(
                            EmailOutbox.template == "comment_reply",
                            valid_reply_recipient,
                        ),
                    ),
                )
                .order_by(EmailOutbox.available_at.asc(), EmailOutbox.id.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            rows = (await session.scalars(statement)).all()
            lease_expires_at = now + self._lease_duration
            for row in rows:
                row.lease_id = lease_id
                row.lease_expires_at = lease_expires_at
                row.attempts += 1
            jobs = [_email_job(row) for row in rows]
            await session.commit()
            return jobs

    async def mark_sent(self, job_id: UUID, lease_id: UUID, sent_at: datetime) -> bool:
        async with self._session_factory() as session:
            statement = (
                update(EmailOutbox)
                .where(
                    EmailOutbox.id == job_id,
                    EmailOutbox.lease_id == lease_id,
                    EmailOutbox.sent_at.is_(None),
                )
                .values(
                    sent_at=sent_at,
                    recipient=None,
                    payload=None,
                    token_id=None,
                    lease_id=None,
                    lease_expires_at=None,
                    last_error=None,
                )
                .returning(EmailOutbox.id)
            )
            updated_id = (await session.execute(statement)).scalar_one_or_none()
            await session.commit()
            return updated_id is not None

    async def reschedule(
        self,
        job_id: UUID,
        lease_id: UUID,
        now: datetime,
        error: Exception,
    ) -> bool:
        async with self._session_factory() as session:
            statement = (
                select(EmailOutbox)
                .where(
                    EmailOutbox.id == job_id,
                    EmailOutbox.lease_id == lease_id,
                    EmailOutbox.sent_at.is_(None),
                )
                .with_for_update()
            )
            row = await session.scalar(statement)
            if row is None:
                return False
            delay_seconds = min(2**row.attempts, 3600)
            row.available_at = now + timedelta(seconds=delay_seconds)
            row.lease_id = None
            row.lease_expires_at = None
            row.last_error = type(error).__name__[:100]
            await session.commit()
            return True


MessageFactory = Callable[[EmailJob], EmailMessage]


class EmailDispatcher:
    def __init__(
        self,
        repository: EmailOutboxRepository,
        mailer: Mailer,
        message_factory: MessageFactory,
        *,
        interval_seconds: float = 2.0,
        batch_limit: int = 20,
        clock: Callable[[], datetime] | None = None,
        lease_id_factory: Callable[[], UUID] = uuid.uuid4,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("dispatch interval must be positive")
        if batch_limit < 1:
            raise ValueError("batch limit must be positive")
        self._repository = repository
        self._mailer = mailer
        self._message_factory = message_factory
        self._interval_seconds = interval_seconds
        self._batch_limit = batch_limit
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lease_id_factory = lease_id_factory

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            lease_id = self._lease_id_factory()
            try:
                jobs = await self._repository.claim_batch(
                    self._clock(),
                    lease_id,
                    self._batch_limit,
                )
            except Exception:
                LOGGER.warning("Email outbox claim failed")
                jobs = []
            for job in jobs:
                try:
                    message = self._message_factory(job)
                    await self._mailer.send(message)
                except Exception as error:
                    LOGGER.warning("Email delivery failed")
                    try:
                        await self._repository.reschedule(
                            job.id,
                            lease_id,
                            self._clock(),
                            error,
                        )
                    except Exception:
                        LOGGER.warning("Email outbox reschedule failed")
                else:
                    try:
                        await self._repository.mark_sent(job.id, lease_id, self._clock())
                    except Exception:
                        LOGGER.warning("Email outbox mark-sent failed")

            if not stop.is_set():
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self._interval_seconds)


def _email_job(row: EmailOutbox) -> EmailJob:
    if row.recipient is None or row.payload is None:
        raise ValueError("pending email is missing delivery data")
    return EmailJob(
        id=row.id,
        token_id=row.token_id,
        template=row.template,
        recipient=row.recipient,
        payload=dict(row.payload),
        attempts=row.attempts,
    )
