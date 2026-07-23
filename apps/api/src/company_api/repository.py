"""Persistence boundary for companies and document index records."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from company_api.models import Company, Document, DocumentFormat
from company_api.schemas import CompanyCreate


@dataclass(frozen=True, slots=True)
class CompanyRecord:
    id: UUID
    name: str
    ticker: str | None
    market: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class NewDocumentRecord:
    id: UUID
    company_id: UUID
    title: str
    format: DocumentFormat
    source_path: str
    rendered_path: str | None
    original_filename: str


@dataclass(frozen=True, slots=True)
class DocumentRecord(NewDocumentRecord):
    sort_order: int
    uploaded_at: datetime


class LibraryRepository(Protocol):
    async def create_company(self, data: CompanyCreate) -> CompanyRecord: ...

    async def list_companies(self) -> list[CompanyRecord]: ...

    async def company_exists(self, company_id: UUID) -> bool: ...

    async def delete_empty_company(self, company_id: UUID) -> bool: ...

    async def insert_document(self, record: NewDocumentRecord) -> DocumentRecord: ...

    async def list_documents(self, company_id: UUID) -> list[DocumentRecord]: ...

    async def get_document(self, document_id: UUID) -> DocumentRecord | None: ...

    async def rename_document(self, document_id: UUID, title: str) -> DocumentRecord | None: ...

    async def delete_document(self, document_id: UUID) -> DocumentRecord | None: ...


class SqlAlchemyLibraryRepository:
    """One short-lived async session and transaction per repository operation."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_company(self, data: CompanyCreate) -> CompanyRecord:
        async with self._session_factory() as session:
            company = Company(name=data.name, ticker=data.ticker, market=data.market)
            session.add(company)
            await session.commit()
            await session.refresh(company)
            return _company_record(company)

    async def list_companies(self) -> list[CompanyRecord]:
        async with self._session_factory() as session:
            statement = select(Company).order_by(
                func.lower(func.trim(Company.name)).asc(),
                Company.id.asc(),
            )
            companies = (await session.scalars(statement)).all()
            return [_company_record(company) for company in companies]

    async def company_exists(self, company_id: UUID) -> bool:
        async with self._session_factory() as session:
            statement = select(exists().where(Company.id == company_id))
            return bool(await session.scalar(statement))

    async def delete_empty_company(self, company_id: UUID) -> bool:
        async with self._session_factory() as session:
            has_documents = exists().where(Document.company_id == Company.id)
            statement = (
                delete(Company)
                .where(Company.id == company_id, ~has_documents)
                .returning(Company.id)
            )
            deleted_id = (await session.execute(statement)).scalar_one_or_none()
            await session.commit()
            return deleted_id is not None

    async def insert_document(self, record: NewDocumentRecord) -> DocumentRecord:
        async with self._session_factory() as session:
            await session.scalar(
                select(Company.id).where(Company.id == record.company_id).with_for_update()
            )
            current_max = await session.scalar(
                select(func.max(Document.sort_order)).where(
                    Document.company_id == record.company_id
                )
            )
            document = Document(
                id=record.id,
                company_id=record.company_id,
                title=record.title,
                format=record.format,
                source_path=record.source_path,
                rendered_path=record.rendered_path,
                original_filename=record.original_filename,
                sort_order=(current_max if current_max is not None else -1) + 1,
            )
            session.add(document)
            await session.flush()
            await session.refresh(document)
            saved = _document_record(document)
            await session.commit()
            return saved

    async def list_documents(self, company_id: UUID) -> list[DocumentRecord]:
        async with self._session_factory() as session:
            statement = (
                select(Document)
                .where(Document.company_id == company_id)
                .order_by(Document.uploaded_at.desc(), Document.id.desc())
            )
            documents = (await session.scalars(statement)).all()
            return [_document_record(document) for document in documents]

    async def get_document(self, document_id: UUID) -> DocumentRecord | None:
        async with self._session_factory() as session:
            document = await session.get(Document, document_id)
            return _document_record(document) if document is not None else None

    async def rename_document(self, document_id: UUID, title: str) -> DocumentRecord | None:
        async with self._session_factory() as session:
            statement = (
                update(Document)
                .where(Document.id == document_id)
                .values(title=title)
                .returning(Document)
            )
            document = (await session.execute(statement)).scalar_one_or_none()
            await session.commit()
            return _document_record(document) if document is not None else None

    async def delete_document(self, document_id: UUID) -> DocumentRecord | None:
        async with self._session_factory() as session:
            statement = delete(Document).where(Document.id == document_id).returning(Document)
            document = (await session.execute(statement)).scalar_one_or_none()
            await session.commit()
            return _document_record(document) if document is not None else None


def _company_record(company: Company) -> CompanyRecord:
    return CompanyRecord(
        id=company.id,
        name=company.name,
        ticker=company.ticker,
        market=company.market,
        created_at=company.created_at,
    )


def _document_record(document: Document) -> DocumentRecord:
    return DocumentRecord(
        id=document.id,
        company_id=document.company_id,
        title=document.title,
        format=document.format,
        source_path=document.source_path,
        rendered_path=document.rendered_path,
        original_filename=document.original_filename,
        sort_order=document.sort_order,
        uploaded_at=document.uploaded_at,
    )
