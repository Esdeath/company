"""Persistence boundary for companies and document index records."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, exists, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from company_api.models import Company, Document, DocumentFormat
from company_api.schemas import CompanyCreate


class InvalidDocumentOrder(Exception):
    pass


class InvalidCompanyOrder(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CompanyRecord:
    id: UUID
    name: str
    ticker: str | None
    market: str | None
    sort_order: int
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

    async def reorder_companies(self, company_ids: list[UUID]) -> list[CompanyRecord]: ...

    async def company_exists(self, company_id: UUID) -> bool: ...

    async def delete_empty_company(self, company_id: UUID) -> bool: ...

    async def insert_document(self, record: NewDocumentRecord) -> DocumentRecord: ...

    async def list_documents(self, company_id: UUID) -> list[DocumentRecord]: ...

    async def reorder_documents(
        self,
        company_id: UUID,
        document_ids: list[UUID],
    ) -> list[DocumentRecord] | None: ...

    async def get_document(self, document_id: UUID) -> DocumentRecord | None: ...

    async def rename_document(self, document_id: UUID, title: str) -> DocumentRecord | None: ...

    async def delete_document(self, document_id: UUID) -> DocumentRecord | None: ...


class SqlAlchemyLibraryRepository:
    """One short-lived async session and transaction per repository operation."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_company(self, data: CompanyCreate) -> CompanyRecord:
        async with self._session_factory() as session:
            await session.execute(text("LOCK TABLE companies IN SHARE ROW EXCLUSIVE MODE"))
            current_max = await session.scalar(select(func.max(Company.sort_order)))
            company = Company(
                name=data.name,
                ticker=data.ticker,
                market=data.market,
                sort_order=(current_max if current_max is not None else -1) + 1,
            )
            session.add(company)
            await session.flush()
            await session.refresh(company)
            saved = _company_record(company)
            await session.commit()
            return saved

    async def list_companies(self) -> list[CompanyRecord]:
        async with self._session_factory() as session:
            statement = select(Company).order_by(
                Company.sort_order.asc(),
                Company.id.asc(),
            )
            companies = (await session.scalars(statement)).all()
            return [_company_record(company) for company in companies]

    async def reorder_companies(self, company_ids: list[UUID]) -> list[CompanyRecord]:
        async with self._session_factory() as session:
            await session.execute(text("LOCK TABLE companies IN SHARE ROW EXCLUSIVE MODE"))
            companies = (await session.scalars(select(Company))).all()
            by_id = {company.id: company for company in companies}
            if len(company_ids) != len(set(company_ids)) or set(company_ids) != set(by_id):
                raise InvalidCompanyOrder

            ordered: list[Company] = []
            for sort_order, company_id in enumerate(company_ids):
                company = by_id[company_id]
                company.sort_order = sort_order
                ordered.append(company)

            await session.flush()
            records = [_company_record(company) for company in ordered]
            await session.commit()
            return records

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
                .order_by(Document.sort_order.asc(), Document.id.asc())
            )
            documents = (await session.scalars(statement)).all()
            return [_document_record(document) for document in documents]

    async def reorder_documents(
        self,
        company_id: UUID,
        document_ids: list[UUID],
    ) -> list[DocumentRecord] | None:
        async with self._session_factory() as session:
            locked_company_id = await session.scalar(
                select(Company.id).where(Company.id == company_id).with_for_update()
            )
            if locked_company_id is None:
                return None

            statement = select(Document).where(Document.company_id == company_id)
            documents = (await session.scalars(statement)).all()
            by_id = {document.id: document for document in documents}
            if len(document_ids) != len(set(document_ids)) or set(document_ids) != set(by_id):
                raise InvalidDocumentOrder

            ordered: list[Document] = []
            for sort_order, document_id in enumerate(document_ids):
                document = by_id[document_id]
                document.sort_order = sort_order
                ordered.append(document)

            await session.flush()
            records = [_document_record(document) for document in ordered]
            await session.commit()
            return records

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
        sort_order=company.sort_order,
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
