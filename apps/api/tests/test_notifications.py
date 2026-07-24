import asyncio
from collections.abc import Coroutine
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from company_api.comment_notifications import add_reply_publication_side_effects
from company_api.email_outbox import EmailDispatcher, EmailJob
from company_api.email_tokens import EmailTokenSigner
from company_api.mailer import EmailMessage
from company_api.models import (
    Comment,
    CommentStatus,
    Document,
    EmailOutbox,
    Notification,
    NotificationType,
    User,
    UserStatus,
    UserToken,
    UserTokenPurpose,
)
from company_api.notification_service import (
    NotificationNotFound,
    NotificationRecord,
    NotificationService,
    SqlAlchemyNotificationRepository,
    UnsubscribeTokenInvalid,
)
from company_api.user_auth import token_hash

NOW = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
USER_ID = UUID("00000000-0000-0000-0000-000000000801")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000802")
COMPANY_ID = UUID("00000000-0000-0000-0000-000000000803")
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000804")
COMMENT_ID = UUID("00000000-0000-0000-0000-000000000805")
TOKEN_ID = UUID("00000000-0000-0000-0000-000000000806")


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def record(
    notification_id: int,
    *,
    recipient_id: UUID = USER_ID,
    kind: NotificationType = NotificationType.REPLY,
    body: str | None = "A <b>reply</b>",
    actor_username: str | None = "writer",
    created_at: datetime = NOW,
    read_at: datetime | None = None,
) -> NotificationRecord:
    return NotificationRecord(
        id=UUID(int=notification_id),
        recipient_id=recipient_id,
        type=kind,
        company_id=COMPANY_ID,
        document_id=DOCUMENT_ID,
        comment_id=COMMENT_ID,
        actor_username=actor_username,
        comment_body=body,
        created_at=created_at,
        read_at=read_at,
    )


class MemoryNotifications:
    def __init__(self) -> None:
        self.rows: dict[UUID, NotificationRecord] = {}
        self.challenges = {token_hash("challenge")}
        self.unsubscribe_tokens = {UUID(int=9): USER_ID}
        self.reply_email_enabled = {USER_ID: True}

    async def list(self, recipient_id: UUID) -> list[NotificationRecord]:
        return [row for row in self.rows.values() if row.recipient_id == recipient_id]

    async def mark_read(
        self, notification_id: UUID, recipient_id: UUID, *, now: datetime
    ) -> NotificationRecord | None:
        row = self.rows.get(notification_id)
        if row is None or row.recipient_id != recipient_id:
            return None
        if row.read_at is None:
            row = replace(row, read_at=now)
            self.rows[row.id] = row
        return row

    async def mark_all_read(self, recipient_id: UUID, *, now: datetime) -> None:
        for notification_id, row in self.rows.items():
            if row.recipient_id == recipient_id and row.read_at is None:
                self.rows[notification_id] = replace(row, read_at=now)

    async def unsubscribe(
        self,
        token_id: UUID,
        token_digest: str,
        challenge_hash: str,
        *,
        now: datetime,
    ) -> bool:
        del token_digest
        del now
        if challenge_hash not in self.challenges:
            return False
        self.challenges.remove(challenge_hash)
        user_id = self.unsubscribe_tokens.pop(token_id, None)
        if user_id is None:
            return False
        self.reply_email_enabled[user_id] = False
        return True


@pytest.fixture
def repository() -> MemoryNotifications:
    return MemoryNotifications()


@pytest.fixture
def service(repository: MemoryNotifications) -> NotificationService:
    return NotificationService(
        repository,
        EmailTokenSigner("x" * 32),
        clock=lambda: NOW,
    )  # type: ignore[arg-type]


def test_list_orders_unread_first_then_newest_and_escapes_display_content(
    service: NotificationService, repository: MemoryNotifications
) -> None:
    repository.rows = {
        UUID(int=1): record(1, created_at=NOW - timedelta(minutes=1), read_at=NOW),
        UUID(int=2): record(2, created_at=NOW - timedelta(minutes=2)),
        UUID(int=3): record(
            3,
            kind=NotificationType.COMMENT_APPROVED,
            actor_username=None,
            body="<script>alert(1)</script>",
            created_at=NOW,
        ),
        UUID(int=4): record(
            4,
            kind=NotificationType.COMMENT_REJECTED,
            actor_username=None,
            created_at=NOW - timedelta(seconds=30),
        ),
    }

    page = run(service.list(USER_ID))

    assert [item.id for item in page.items] == [UUID(int=3), UUID(int=4), UUID(int=2), UUID(int=1)]
    assert page.unread_count == 3
    assert page.items[0].excerpt == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert page.items[0].message == "你的评论已通过审核"
    assert page.items[1].message == "你的评论未通过审核"
    assert page.items[2].message == "writer 回复了你的评论"


def test_mark_read_enforces_ownership_and_preserves_the_first_read_timestamp(
    service: NotificationService, repository: MemoryNotifications
) -> None:
    owned = record(1)
    foreign = record(2, recipient_id=OTHER_USER_ID)
    repository.rows = {owned.id: owned, foreign.id: foreign}

    first = run(service.mark_read(owned.id, USER_ID))
    second = run(service.mark_read(owned.id, USER_ID))

    assert first.read_at == NOW
    assert second.read_at == NOW
    with pytest.raises(NotificationNotFound):
        run(service.mark_read(foreign.id, USER_ID))


def test_mark_all_read_only_changes_the_current_users_unread_notifications(
    service: NotificationService, repository: MemoryNotifications
) -> None:
    owned_unread = record(1)
    owned_read = record(2, read_at=NOW - timedelta(minutes=1))
    foreign = record(3, recipient_id=OTHER_USER_ID)
    repository.rows = {item.id: item for item in (owned_unread, owned_read, foreign)}

    run(service.mark_all_read(USER_ID))
    run(service.mark_all_read(USER_ID))

    assert repository.rows[owned_unread.id].read_at == NOW
    assert repository.rows[owned_read.id].read_at == NOW - timedelta(minutes=1)
    assert repository.rows[foreign.id].read_at is None


def test_unsubscribe_is_one_time_and_only_changes_reply_email_preference(
    service: NotificationService, repository: MemoryNotifications
) -> None:
    token = EmailTokenSigner("x" * 32).issue(UUID(int=9), UserTokenPurpose.UNSUBSCRIBE)
    run(service.unsubscribe(token, "challenge"))

    assert repository.reply_email_enabled[USER_ID] is False
    with pytest.raises(UnsubscribeTokenInvalid):
        run(service.unsubscribe(token, "challenge"))


def test_sqlalchemy_unsubscribe_locks_user_before_revalidating_the_token() -> None:
    session = UnsubscribeSession()
    repository = SqlAlchemyNotificationRepository(UnsubscribeFactory(session))  # type: ignore[arg-type]

    result = run(
        repository.unsubscribe(
            TOKEN_ID,
            "token-digest",
            token_hash("challenge"),
            now=NOW,
        )
    )

    statements = [
        str(statement.compile(dialect=postgresql.dialect())) for statement in session.statements
    ]
    assert result is True
    assert "SELECT user_tokens.user_id" in statements[0]
    assert "FOR UPDATE" not in statements[0]
    assert "FROM users" in statements[1] and "FOR UPDATE" in statements[1]
    assert "FROM user_tokens" in statements[2] and "FOR UPDATE" in statements[2]
    assert statements[3].startswith("DELETE FROM user_auth_challenges")
    assert session.user.reply_email_enabled is False
    assert session.token.consumed_at == NOW


@pytest.mark.parametrize("token_after_owner", [None, "changed"])
def test_sqlalchemy_unsubscribe_rejects_a_token_that_disappears_or_changes_after_owner_lookup(
    token_after_owner: str | None,
) -> None:
    session = UnsubscribeSession(token_after_owner=token_after_owner)
    repository = SqlAlchemyNotificationRepository(UnsubscribeFactory(session))  # type: ignore[arg-type]

    result = run(
        repository.unsubscribe(
            TOKEN_ID,
            "token-digest",
            token_hash("challenge"),
            now=NOW,
        )
    )

    assert result is False
    assert session.user.reply_email_enabled is True
    assert session.token.consumed_at is None
    assert session.events == ["commit"]


def test_reply_side_effects_keep_the_notification_when_reply_email_is_opted_out() -> None:
    recipient = stored_user(reply_email_enabled=False)
    session = SideEffectSession(recipient)

    run(
        add_reply_publication_side_effects(
            session,  # type: ignore[arg-type]
            comment_id=COMMENT_ID,
            document_id=DOCUMENT_ID,
            actor_id=OTHER_USER_ID,
            actor_username="writer",
            reply_target=reply_target(),
            created_at=NOW,
            unsubscribe_token_factory=lambda: (TOKEN_ID, "unused"),
        )
    )

    assert [type(item) for item in session.added] == [Notification]


def test_reply_email_defaults_to_enabled_and_stages_a_one_time_unsubscribe_token() -> None:
    recipient = stored_user(reply_email_enabled=True)
    session = SideEffectSession(recipient)
    signer = EmailTokenSigner("x" * 32)

    run(
        add_reply_publication_side_effects(
            session,  # type: ignore[arg-type]
            comment_id=COMMENT_ID,
            document_id=DOCUMENT_ID,
            actor_id=OTHER_USER_ID,
            actor_username="writer",
            reply_target=reply_target(),
            created_at=NOW,
            unsubscribe_token_factory=lambda: (
                TOKEN_ID,
                signer.digest(signer.issue(TOKEN_ID, UserTokenPurpose.UNSUBSCRIBE)),
            ),
        )
    )

    assert [type(item) for item in session.added] == [Notification, UserToken, EmailOutbox]
    token = session.added[1]
    outbox = session.added[2]
    assert isinstance(token, UserToken) and token.purpose == UserTokenPurpose.UNSUBSCRIBE
    assert isinstance(outbox, EmailOutbox) and outbox.token_id == TOKEN_ID
    assert token.token_hash == signer.digest(signer.issue(TOKEN_ID, UserTokenPurpose.UNSUBSCRIBE))


def test_email_dispatch_exhaustion_does_not_remove_the_paired_notification() -> None:
    notification = Notification(
        id=UUID(int=77),
        recipient_id=USER_ID,
        type=NotificationType.REPLY,
        actor_id=OTHER_USER_ID,
        comment_id=COMMENT_ID,
        document_id=DOCUMENT_ID,
        created_at=NOW,
    )
    stop = asyncio.Event()
    repository = ExhaustingOutbox(notification, stop)
    dispatcher = EmailDispatcher(
        repository,  # type: ignore[arg-type]
        FailingMailer(),
        lambda job: EmailMessage(recipient=job.recipient, subject="reply", text_body="reply"),
        clock=lambda: NOW,
    )

    run(dispatcher.run(stop))

    assert repository.exhausted is True
    assert notification.id == UUID(int=77)
    assert notification.read_at is None


def stored_user(*, reply_email_enabled: bool) -> User:
    return User(
        id=USER_ID,
        email="reader@example.com",
        normalized_email="reader@example.com",
        username="reader",
        normalized_username="reader",
        password_hash="hash",
        status=UserStatus.ACTIVE,
        email_verified_at=NOW,
        first_comment_approved_at=NOW,
        reply_email_enabled=reply_email_enabled,
        created_at=NOW,
        updated_at=NOW,
    )


def reply_target() -> Comment:
    return Comment(
        id=UUID(int=88),
        document_id=DOCUMENT_ID,
        author_id=USER_ID,
        parent_id=None,
        body="parent",
        status=CommentStatus.PUBLISHED,
        created_at=NOW,
    )


class SideEffectSession:
    def __init__(self, recipient: User) -> None:
        self.recipient = recipient
        self.document = Document(
            id=DOCUMENT_ID,
            company_id=COMPANY_ID,
            title="Research",
            format="html",
            source_path="source",
            rendered_path=None,
            original_filename="research.html",
            uploaded_at=NOW,
        )
        self.added: list[object] = []

    async def get(self, model: type[object], key: UUID) -> object | None:
        if model is User and key == self.recipient.id:
            return self.recipient
        if model is Document and key == DOCUMENT_ID:
            return self.document
        return None

    def add(self, item: object) -> None:
        self.added.append(item)


class ScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object:
        return self.value


class UnsubscribeSession:
    def __init__(self, *, token_after_owner: str | None = "token-digest") -> None:
        self.user = stored_user(reply_email_enabled=True)
        self.token = UserToken(
            id=TOKEN_ID,
            token_hash="token-digest",
            purpose=UserTokenPurpose.UNSUBSCRIBE,
            user_id=USER_ID,
            created_at=NOW,
            expires_at=NOW + timedelta(days=1),
        )
        self.token_after_owner = token_after_owner
        self.statements: list[object] = []
        self.events: list[str] = []
        self.scalar_calls = 0

    async def __aenter__(self) -> "UnsubscribeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    async def scalar(self, statement: object) -> object | None:
        self.statements.append(statement)
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            return USER_ID
        if self.scalar_calls == 2:
            return self.user
        if self.token_after_owner is None:
            return None
        self.token.token_hash = self.token_after_owner
        return self.token

    async def execute(self, statement: object) -> ScalarResult:
        self.statements.append(statement)
        return ScalarResult(token_hash("challenge"))

    async def commit(self) -> None:
        self.events.append("commit")


class UnsubscribeFactory:
    def __init__(self, session: UnsubscribeSession) -> None:
        self.session = session

    def __call__(self) -> UnsubscribeSession:
        return self.session


class FailingMailer:
    async def send(self, message: EmailMessage) -> None:
        del message
        raise RuntimeError("smtp unavailable")


class ExhaustingOutbox:
    def __init__(self, notification: Notification, stop: asyncio.Event) -> None:
        self.notification = notification
        self.stop = stop
        self.claimed = False
        self.exhausted = False

    async def claim_batch(self, now: datetime, lease_id: UUID, limit: int) -> list[EmailJob]:
        del now, lease_id, limit
        if self.claimed:
            return []
        self.claimed = True
        return [
            EmailJob(
                id=UUID(int=76),
                token_id=TOKEN_ID,
                template="comment_reply",
                recipient="reader@example.com",
                payload={},
                attempts=8,
            )
        ]

    async def mark_sent(self, job_id: UUID, lease_id: UUID, sent_at: datetime) -> bool:
        del job_id, lease_id, sent_at
        return False

    async def reschedule(
        self,
        job_id: UUID,
        lease_id: UUID,
        now: datetime,
        error: Exception,
    ) -> bool:
        del job_id, lease_id, now, error
        self.exhausted = True
        self.stop.set()
        return True
