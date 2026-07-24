import asyncio
import dataclasses
import logging
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from company_api.email_outbox import (
    EmailDispatcher,
    EmailJob,
    SqlAlchemyEmailOutboxRepository,
)
from company_api.mailer import EmailMessage, UnavailableMailer
from company_api.models import EmailOutbox

NOW = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
JOB_ID = UUID("00000000-0000-0000-0000-000000000111")
TOKEN_ID = UUID("00000000-0000-0000-0000-000000000222")
LEASE_ID = UUID("00000000-0000-0000-0000-000000000333")


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


class ScalarRows:
    def __init__(self, rows: list[EmailOutbox]) -> None:
        self._rows = rows

    def all(self) -> list[EmailOutbox]:
        return self._rows


class UpdateResult:
    def __init__(self, updated_id: UUID | None) -> None:
        self._updated_id = updated_id

    def scalar_one_or_none(self) -> UUID | None:
        return self._updated_id


class FakeSession:
    def __init__(
        self,
        *,
        claimed: list[EmailOutbox] | None = None,
        retry_row: EmailOutbox | None = None,
        updated_id: UUID | None = JOB_ID,
    ) -> None:
        self.claimed = claimed or []
        self.retry_row = retry_row
        self.updated_id = updated_id
        self.statements: list[object] = []
        self.events: list[str] = []

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exc_type, exc_value, traceback

    async def scalars(self, statement: object) -> ScalarRows:
        self.statements.append(statement)
        return ScalarRows(self.claimed)

    async def scalar(self, statement: object) -> EmailOutbox | None:
        self.statements.append(statement)
        return self.retry_row

    async def execute(self, statement: object) -> UpdateResult:
        self.statements.append(statement)
        return UpdateResult(self.updated_id)

    async def commit(self) -> None:
        self.events.append("commit")


class SessionFactory:
    def __init__(self, sessions: list[FakeSession]) -> None:
        self._sessions = iter(sessions)

    def __call__(self) -> FakeSession:
        return next(self._sessions)


def outbox_row(*, attempts: int = 0) -> EmailOutbox:
    return EmailOutbox(
        id=JOB_ID,
        token_id=TOKEN_ID,
        template="verify_email",
        recipient="private@example.com",
        payload={"display_name": "Private Reader"},
        attempts=attempts,
        available_at=NOW,
        lease_id=None,
        lease_expires_at=None,
        sent_at=None,
        last_error=None,
    )


def sql(statement: object) -> str:
    return str(
        statement.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_claim_batch_uses_skip_locked_and_recovers_expired_leases() -> None:
    row = outbox_row()
    session = FakeSession(claimed=[row])
    repository = SqlAlchemyEmailOutboxRepository(
        SessionFactory([session]),  # type: ignore[arg-type]
        max_attempts=4,
        lease_seconds=90,
    )

    jobs = run(repository.claim_batch(NOW, LEASE_ID, 10))

    statement_sql = sql(session.statements[0])
    assert "FOR UPDATE SKIP LOCKED" in statement_sql
    assert "email_outbox.lease_id IS NULL OR email_outbox.lease_expires_at <=" in statement_sql
    assert "email_outbox.attempts < 4" in statement_sql
    assert row.lease_id == LEASE_ID
    assert row.lease_expires_at == NOW + timedelta(seconds=90)
    assert row.attempts == 1
    assert session.events == ["commit"]
    assert jobs == [
        EmailJob(
            id=JOB_ID,
            token_id=TOKEN_ID,
            template="verify_email",
            recipient="private@example.com",
            payload={"display_name": "Private Reader"},
            attempts=1,
        )
    ]
    assert "raw_token" not in {field.name for field in dataclasses.fields(EmailJob)}


@pytest.mark.parametrize(("attempts", "delay_seconds"), [(3, 8), (12, 3600)])
def test_reschedule_clears_lease_and_uses_capped_exponential_delay(
    attempts: int,
    delay_seconds: int,
) -> None:
    row = outbox_row(attempts=attempts)
    row.lease_id = LEASE_ID
    row.lease_expires_at = NOW + timedelta(seconds=90)
    session = FakeSession(retry_row=row)
    repository = SqlAlchemyEmailOutboxRepository(
        SessionFactory([session]),  # type: ignore[arg-type]
        max_attempts=20,
    )

    updated = run(repository.reschedule(JOB_ID, LEASE_ID, NOW, RuntimeError("private payload")))

    assert updated is True
    assert row.available_at == NOW + timedelta(seconds=delay_seconds)
    assert row.lease_id is None
    assert row.lease_expires_at is None
    assert row.last_error == "RuntimeError"
    assert "private payload" not in row.last_error
    assert session.events == ["commit"]


def test_maximum_attempt_rows_are_excluded_from_claims() -> None:
    session = FakeSession()
    repository = SqlAlchemyEmailOutboxRepository(
        SessionFactory([session]),  # type: ignore[arg-type]
        max_attempts=3,
    )

    assert run(repository.claim_batch(NOW, LEASE_ID, 10)) == []
    assert "email_outbox.attempts < 3" in sql(session.statements[0])


def test_mark_sent_scrubs_private_delivery_material() -> None:
    session = FakeSession()
    repository = SqlAlchemyEmailOutboxRepository(
        SessionFactory([session])  # type: ignore[arg-type]
    )

    updated = run(repository.mark_sent(JOB_ID, LEASE_ID, NOW))

    assert updated is True
    compiled = session.statements[0].compile(dialect=postgresql.dialect())  # type: ignore[attr-defined]
    assert compiled.params["recipient"] is None
    assert compiled.params["payload"] is None
    assert compiled.params["token_id"] is None
    assert compiled.params["lease_id"] is None
    assert compiled.params["lease_expires_at"] is None
    assert compiled.params["last_error"] is None
    assert NOW in compiled.params.values()
    assert session.events == ["commit"]


class FakeRepository:
    def __init__(self, job: EmailJob, stop: asyncio.Event) -> None:
        self.job = job
        self.stop = stop
        self.events: list[tuple[object, ...]] = []

    async def claim_batch(self, now: datetime, lease_id: UUID, limit: int) -> list[EmailJob]:
        self.events.append(("claim", now, lease_id, limit))
        return [self.job]

    async def mark_sent(self, job_id: UUID, lease_id: UUID, sent_at: datetime) -> bool:
        self.events.append(("sent", job_id, lease_id, sent_at))
        self.stop.set()
        return True

    async def reschedule(
        self,
        job_id: UUID,
        lease_id: UUID,
        now: datetime,
        error: Exception,
    ) -> bool:
        self.events.append(("retry", job_id, lease_id, now, type(error).__name__))
        self.stop.set()
        return True


class RecordingMailer:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.messages: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.messages.append(message)
        if self.error is not None:
            raise self.error


def job() -> EmailJob:
    return EmailJob(
        id=JOB_ID,
        token_id=TOKEN_ID,
        template="verify_email",
        recipient="private@example.com",
        payload={"name": "Reader"},
        attempts=1,
    )


def message_factory(email_job: EmailJob) -> EmailMessage:
    return EmailMessage(email_job.recipient, "Verify", "fixed body")


def dispatcher(
    repository: FakeRepository,
    mailer: RecordingMailer,
    *,
    lease_id_factory: Callable[[], UUID] = lambda: LEASE_ID,
) -> EmailDispatcher:
    return EmailDispatcher(
        repository,
        mailer,
        message_factory,
        interval_seconds=0.01,
        batch_limit=5,
        clock=lambda: NOW,
        lease_id_factory=lease_id_factory,
    )


def test_dispatcher_sends_after_claim_commit_and_marks_success() -> None:
    stop = asyncio.Event()
    repository = FakeRepository(job(), stop)
    mailer = RecordingMailer()

    run(dispatcher(repository, mailer).run(stop))

    assert mailer.messages == [EmailMessage("private@example.com", "Verify", "fixed body")]
    assert repository.events == [
        ("claim", NOW, LEASE_ID, 5),
        ("sent", JOB_ID, LEASE_ID, NOW),
    ]


def test_dispatcher_reschedules_failure_and_logs_no_private_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop = asyncio.Event()
    repository = FakeRepository(job(), stop)
    mailer = RecordingMailer(error=RuntimeError("private@example.com raw-token private payload"))

    with caplog.at_level(logging.WARNING, logger="company_api.email_outbox"):
        run(dispatcher(repository, mailer).run(stop))

    assert repository.events == [
        ("claim", NOW, LEASE_ID, 5),
        ("retry", JOB_ID, LEASE_ID, NOW, "RuntimeError"),
    ]
    assert [record.getMessage() for record in caplog.records] == ["Email delivery failed"]
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "private@example.com" not in logged
    assert "raw-token" not in logged
    assert "private payload" not in logged


def test_dispatcher_retries_unavailable_smtp_with_fixed_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop = asyncio.Event()
    repository = FakeRepository(job(), stop)

    with caplog.at_level(logging.WARNING, logger="company_api.email_outbox"):
        run(dispatcher(repository, UnavailableMailer()).run(stop))

    assert repository.events == [
        ("claim", NOW, LEASE_ID, 5),
        ("retry", JOB_ID, LEASE_ID, NOW, "SmtpUnavailable"),
    ]
    assert [record.getMessage() for record in caplog.records] == ["Email delivery failed"]
