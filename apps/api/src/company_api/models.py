import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class DocumentFormat(str, enum.Enum):  # noqa: UP042
    HTML = "html"
    MARKDOWN = "markdown"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), index=True)
    ticker: Mapped[str | None] = mapped_column(String(50))
    market: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500))
    format: Mapped[DocumentFormat] = mapped_column(
        Enum(DocumentFormat, name="document_format")
    )
    source_path: Mapped[str] = mapped_column(String(1000), unique=True)
    rendered_path: Mapped[str | None] = mapped_column(String(1000), unique=True)
    original_filename: Mapped[str] = mapped_column(String(500))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
    )
