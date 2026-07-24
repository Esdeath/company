import asyncio
import json
import logging
import ssl
import stat
from collections.abc import Coroutine
from email.message import EmailMessage as MimeEmailMessage
from pathlib import Path
from typing import Any

import pytest
from pwdlib import PasswordHash

from company_api.config import Settings
from company_api.mailer import (
    ConsoleMailer,
    EmailMessage,
    FileCaptureMailer,
    SmtpMailer,
    SmtpUnavailable,
    UnavailableMailer,
)
from company_api.main import _mailer


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql+psycopg://company:company@localhost/company",
        "admin_username": "admin",
        "admin_password_hash": PasswordHash.recommended().hash("correct horse battery staple"),
        "session_cookie_secure": False,
        "app_environment": "test",
        "smtp_host": "smtp.example.com",
        "smtp_port": 2525,
        "smtp_username": "smtp-user",
        "smtp_password": "smtp-secret",
        "smtp_starttls": True,
        "smtp_sender": "Research Library <library@example.com>",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


class FakeSmtp:
    instances: list["FakeSmtp"] = []

    def __init__(self, host: str, port: int, *, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.events: list[object] = []
        FakeSmtp.instances.append(self)

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exc_type, exc_value, traceback

    def starttls(self, *, context: ssl.SSLContext) -> None:
        self.events.append(("starttls", context))

    def login(self, username: str, password: str) -> None:
        self.events.append(("login", username, password))

    def send_message(self, message: MimeEmailMessage) -> None:
        self.events.append(("send_message", message))


def test_smtp_mailer_builds_safe_rfc_message_and_follows_transport_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeSmtp.instances.clear()
    monkeypatch.setattr("company_api.mailer.smtplib.SMTP", FakeSmtp)
    message = EmailMessage(
        recipient="Reader <reader@example.com>",
        subject="A reply arrived",
        text_body="Alice replied: <script>alert('no')</script> & welcome",
    )

    run(SmtpMailer(settings()).send(message))

    smtp = FakeSmtp.instances[0]
    assert (smtp.host, smtp.port, smtp.timeout) == ("smtp.example.com", 2525, 10.0)
    starttls = smtp.events[0]
    assert isinstance(starttls, tuple)
    tls_context = starttls[1]
    assert isinstance(tls_context, ssl.SSLContext)
    assert tls_context.verify_mode == ssl.CERT_REQUIRED
    assert tls_context.check_hostname is True
    assert smtp.events[1] == ("login", "smtp-user", "smtp-secret")
    sent = smtp.events[2]
    assert isinstance(sent, tuple)
    mime_message = sent[1]
    assert isinstance(mime_message, MimeEmailMessage)
    assert str(mime_message["From"]) == "Research Library <library@example.com>"
    assert str(mime_message["To"]) == "Reader <reader@example.com>"
    assert mime_message["Subject"] == "A reply arrived"
    html_body = mime_message.get_body(preferencelist=("html",)).get_content()
    assert "&lt;script&gt;alert(&#x27;no&#x27;)&lt;/script&gt; &amp; welcome" in html_body
    assert "<script>" not in html_body


def test_smtp_mailer_passes_configured_connection_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeSmtp.instances.clear()
    monkeypatch.setattr("company_api.mailer.smtplib.SMTP", FakeSmtp)

    run(
        SmtpMailer(settings(smtp_timeout_seconds=3.5)).send(
            EmailMessage("reader@example.com", "Subject", "Body")
        )
    )

    assert FakeSmtp.instances[0].timeout == 3.5


def test_smtp_mailer_skips_starttls_and_login_when_disabled_and_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeSmtp.instances.clear()
    monkeypatch.setattr("company_api.mailer.smtplib.SMTP", FakeSmtp)

    run(
        SmtpMailer(settings(smtp_starttls=False, smtp_username="", smtp_password="")).send(
            EmailMessage("reader@example.com", "Subject", "Body")
        )
    )

    assert FakeSmtp.instances[0].events[0][0] == "send_message"


def test_unconfigured_production_smtp_starts_but_delivery_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeSmtp.instances.clear()
    monkeypatch.setattr("company_api.mailer.smtplib.SMTP", FakeSmtp)
    configured = settings(
        app_environment="production",
        email_backend="smtp",
        user_registration_enabled=False,
        user_token_signing_key="x" * 32,
        public_base_url="https://research.example.com",
        smtp_host="",
        smtp_username="",
        smtp_password="",
        smtp_sender="",
    )

    mailer = _mailer(configured)

    assert isinstance(mailer, UnavailableMailer)
    with pytest.raises(SmtpUnavailable, match="SMTP is not configured"):
        run(mailer.send(EmailMessage("reader@example.com", "Subject", "private token")))
    assert FakeSmtp.instances == []
    assert str(SmtpUnavailable("SMTP is not configured")) == "SMTP is not configured"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("recipient", "reader@example.com\nBcc: stolen@example.com"),
        ("subject", "Subject\nBcc: stolen@example.com"),
    ],
)
def test_message_rejects_header_injection(field: str, value: str) -> None:
    values = {
        "recipient": "reader@example.com",
        "subject": "Subject",
        "text_body": "Body",
    }
    values[field] = value

    with pytest.raises(ValueError):
        EmailMessage(**values)


def test_file_capture_is_private_json_lines_and_only_allowed_in_test(tmp_path: Path) -> None:
    capture_path = tmp_path / "mail" / "capture.jsonl"
    mailer = FileCaptureMailer(settings(email_capture_path=capture_path))
    message = EmailMessage("reader@example.com", "Subject", "secret token")

    run(mailer.send(message))
    run(mailer.send(EmailMessage("second@example.com", "Another", "payload")))

    records = [json.loads(line) for line in capture_path.read_text().splitlines()]
    assert records == [
        {
            "recipient": "reader@example.com",
            "subject": "Subject",
            "text_body": "secret token",
        },
        {
            "recipient": "second@example.com",
            "subject": "Another",
            "text_body": "payload",
        },
    ]
    assert stat.S_IMODE(capture_path.stat().st_mode) == 0o600

    with pytest.raises(ValueError, match="test environment"):
        FileCaptureMailer(settings(app_environment="development", email_capture_path=capture_path))


def test_file_capture_requires_a_path() -> None:
    with pytest.raises(ValueError, match="capture path"):
        FileCaptureMailer(settings(email_capture_path=None))


def test_console_mailer_logs_only_a_fixed_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    message = EmailMessage("private@example.com", "Token notice", "raw-secret-token")

    with caplog.at_level(logging.INFO, logger="company_api.mailer"):
        run(ConsoleMailer().send(message))

    assert [record.getMessage() for record in caplog.records] == [
        "Email discarded by console backend"
    ]
    combined = " ".join(record.getMessage() for record in caplog.records)
    assert "private@example.com" not in combined
    assert "raw-secret-token" not in combined
