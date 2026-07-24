import asyncio
import html
import json
import logging
import os
import smtplib
from dataclasses import dataclass
from email.headerregistry import Address
from email.message import EmailMessage as MimeEmailMessage
from email.utils import parseaddr
from typing import Protocol

from email_validator import EmailNotValidError, validate_email

from company_api.config import Settings

LOGGER = logging.getLogger(__name__)


def _mailbox(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("mailbox must not contain line breaks")
    display_name, address = parseaddr(value, strict=True)
    if not address:
        raise ValueError("mailbox is invalid")
    try:
        normalized = validate_email(address, check_deliverability=False).normalized
    except EmailNotValidError as error:
        raise ValueError("mailbox is invalid") from error
    return str(Address(display_name=display_name, addr_spec=normalized))


@dataclass(frozen=True, slots=True)
class EmailMessage:
    recipient: str
    subject: str
    text_body: str

    def __post_init__(self) -> None:
        if "\n" in self.subject or "\r" in self.subject:
            raise ValueError("subject must not contain line breaks")
        object.__setattr__(self, "recipient", _mailbox(self.recipient))


class Mailer(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class SmtpUnavailable(RuntimeError):
    """Production SMTP has not been configured yet."""


class UnavailableMailer:
    async def send(self, message: EmailMessage) -> None:
        del message
        raise SmtpUnavailable("SMTP is not configured")


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._username = settings.smtp_username
        self._password = settings.smtp_password.get_secret_value()
        self._starttls = settings.smtp_starttls
        self._sender = _mailbox(settings.smtp_sender)

    async def send(self, message: EmailMessage) -> None:
        await asyncio.to_thread(self._send, message)

    def _send(self, message: EmailMessage) -> None:
        mime_message = _mime_message(self._sender, message)
        with smtplib.SMTP(self._host, self._port) as smtp:
            if self._starttls:
                smtp.starttls()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(mime_message)


class ConsoleMailer:
    async def send(self, message: EmailMessage) -> None:
        del message
        LOGGER.info("Email discarded by console backend")


class FileCaptureMailer:
    def __init__(self, settings: Settings) -> None:
        if settings.app_environment != "test":
            raise ValueError("file capture is restricted to the test environment")
        if settings.email_capture_path is None:
            raise ValueError("email capture path is required")
        self._path = settings.email_capture_path

    async def send(self, message: EmailMessage) -> None:
        await asyncio.to_thread(self._append, message)

    def _append(self, message: EmailMessage) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self._path, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            record = {
                "recipient": message.recipient,
                "subject": message.subject,
                "text_body": message.text_body,
            }
            line = json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n"
            os.write(descriptor, line.encode())
        finally:
            os.close(descriptor)


def _mime_message(sender: str, message: EmailMessage) -> MimeEmailMessage:
    mime_message = MimeEmailMessage()
    mime_message["From"] = sender
    mime_message["To"] = message.recipient
    mime_message["Subject"] = message.subject
    mime_message.set_content(message.text_body)
    escaped_body = html.escape(message.text_body).replace("\n", "<br>\n")
    mime_message.add_alternative(f"<p>{escaped_body}</p>", subtype="html")
    return mime_message
