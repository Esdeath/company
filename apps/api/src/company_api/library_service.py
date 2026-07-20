"""Application service coordinating the database index and atomic content store."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from company_api.content_store import (
    ContentStore,
    PreparedDocument,
    StoredDocument,
    UnsupportedDocumentType,
)
from company_api.models import DocumentFormat
from company_api.repository import (
    CompanyRecord,
    DocumentRecord,
    LibraryRepository,
    NewDocumentRecord,
)
from company_api.schemas import (
    CompanyCreate,
    CompanyRead,
    DocumentRead,
    UploadBatchResponse,
    UploadError,
    UploadItem,
)

logger = logging.getLogger(__name__)

_UNSUPPORTED_TYPE_MESSAGE = "只支持 .html 和 .md 文件"
_GENERIC_UPLOAD_MESSAGE = "文件处理失败"


class CompanyNotFound(Exception):
    pass


class CompanyNotEmpty(Exception):
    pass


class DocumentNotFound(Exception):
    pass


@dataclass(frozen=True, slots=True)
class UploadInput:
    filename: str
    content: bytes


class LibraryOperations(Protocol):
    async def create_company(self, data: CompanyCreate) -> CompanyRead: ...

    async def list_companies(self) -> list[CompanyRead]: ...

    async def delete_company(self, company_id: UUID) -> None: ...

    async def list_documents(self, company_id: UUID) -> list[DocumentRead]: ...

    async def upload_documents(
        self, company_id: UUID, uploads: list[UploadInput]
    ) -> UploadBatchResponse: ...

    async def rename_document(self, document_id: UUID, title: str) -> DocumentRead: ...

    async def delete_document(self, document_id: UUID) -> None: ...

    async def content_path(self, document_id: UUID) -> Path: ...


class LibraryService:
    def __init__(self, repository: LibraryRepository, content_store: ContentStore) -> None:
        self._repository = repository
        self._content_store = content_store

    async def create_company(self, data: CompanyCreate) -> CompanyRead:
        return _company_read(await self._repository.create_company(data))

    async def list_companies(self) -> list[CompanyRead]:
        records = await self._repository.list_companies()
        records.sort(key=lambda record: (record.name.strip().casefold(), str(record.id)))
        return [_company_read(record) for record in records]

    async def delete_company(self, company_id: UUID) -> None:
        if await self._repository.delete_empty_company(company_id):
            return
        if not await self._repository.company_exists(company_id):
            raise CompanyNotFound
        raise CompanyNotEmpty

    async def list_documents(self, company_id: UUID) -> list[DocumentRead]:
        if not await self._repository.company_exists(company_id):
            raise CompanyNotFound
        records = await self._repository.list_documents(company_id)
        records.sort(key=lambda record: (record.uploaded_at, record.id), reverse=True)
        return [_document_read(record) for record in records]

    async def upload_documents(
        self, company_id: UUID, uploads: list[UploadInput]
    ) -> UploadBatchResponse:
        if not await self._repository.company_exists(company_id):
            raise CompanyNotFound

        items: list[UploadItem] = []
        errors: list[UploadError] = []
        for upload in uploads:
            prepared: PreparedDocument | None = None
            stored: StoredDocument | None = None
            try:
                document_id = uuid4()
                prepared = self._content_store.prepare(
                    company_id,
                    document_id,
                    upload.filename,
                    upload.content,
                )
                stored = self._content_store.commit(prepared)
                record = await self._repository.insert_document(
                    NewDocumentRecord(
                        id=document_id,
                        company_id=company_id,
                        title=stored.title,
                        format=stored.format,
                        source_path=stored.source_relative_path,
                        rendered_path=stored.rendered_relative_path,
                        original_filename=stored.original_filename,
                    )
                )
            except UnsupportedDocumentType:
                errors.append(
                    UploadError(
                        filename=upload.filename,
                        message=_UNSUPPORTED_TYPE_MESSAGE,
                    )
                )
                continue
            except UnicodeError:
                self._cleanup_failed_upload(prepared, stored)
                errors.append(
                    UploadError(filename=upload.filename, message=_GENERIC_UPLOAD_MESSAGE)
                )
                continue
            except BaseException as error:
                self._cleanup_failed_upload(prepared, stored)
                if not isinstance(error, Exception):
                    raise
                logger.error("Document upload failed")
                errors.append(
                    UploadError(filename=upload.filename, message=_GENERIC_UPLOAD_MESSAGE)
                )
                continue

            items.append(UploadItem(**_document_read(record).model_dump()))

        return UploadBatchResponse(items=items, errors=errors)

    async def rename_document(self, document_id: UUID, title: str) -> DocumentRead:
        record = await self._repository.rename_document(document_id, title)
        if record is None:
            raise DocumentNotFound
        return _document_read(record)

    async def delete_document(self, document_id: UUID) -> None:
        record = await self._repository.get_document(document_id)
        if record is None:
            raise DocumentNotFound
        stored = self._stored_document(record)
        self._content_store.delete(stored)
        try:
            deleted = await self._repository.delete_document(document_id)
        except BaseException:
            self._content_store.restore_deleted(stored)
            raise
        if deleted is None:
            self._content_store.restore_deleted(stored)
            raise DocumentNotFound
        self._content_store.purge_deleted(stored)

    async def content_path(self, document_id: UUID) -> Path:
        record = await self._repository.get_document(document_id)
        if record is None:
            raise DocumentNotFound
        stored = self._stored_document(record)
        path = stored.source_path if record.format is DocumentFormat.HTML else stored.rendered_path
        if path is None or not self._is_safe_regular_file(path):
            raise DocumentNotFound
        return path

    def _cleanup_failed_upload(
        self,
        prepared: PreparedDocument | None,
        stored: StoredDocument | None,
    ) -> None:
        try:
            if stored is not None:
                self._content_store.delete(stored)
                self._content_store.purge_deleted(stored)
            elif prepared is not None:
                self._content_store.discard(prepared)
        except Exception:
            logger.error("Document upload cleanup failed")

    def _stored_document(self, record: DocumentRecord) -> StoredDocument:
        directory = self._content_store.root / "companies" / str(record.company_id) / str(record.id)
        source_filename = "source.html" if record.format is DocumentFormat.HTML else "source.md"
        source_path = directory / source_filename
        rendered_path = (
            directory / "rendered.html" if record.format is DocumentFormat.MARKDOWN else None
        )
        expected_source = source_path.relative_to(self._content_store.root).as_posix()
        expected_rendered = (
            rendered_path.relative_to(self._content_store.root).as_posix()
            if rendered_path is not None
            else None
        )
        if record.source_path != expected_source or record.rendered_path != expected_rendered:
            raise DocumentNotFound

        return StoredDocument(
            title=record.title,
            format=record.format,
            original_filename=record.original_filename,
            directory=directory,
            source_path=source_path,
            rendered_path=rendered_path,
            source_relative_path=record.source_path,
            rendered_relative_path=record.rendered_path,
        )

    def _is_safe_regular_file(self, path: Path) -> bool:
        try:
            relative = path.relative_to(self._content_store.root)
        except ValueError:
            return False

        current = self._content_store.root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                return False
        try:
            path.resolve(strict=True).relative_to(self._content_store.root)
        except (FileNotFoundError, RuntimeError, ValueError):
            return False
        return os.path.isfile(path)


def _company_read(record: CompanyRecord) -> CompanyRead:
    return CompanyRead(
        id=record.id,
        name=record.name,
        ticker=record.ticker,
        market=record.market,
        created_at=record.created_at,
    )


def _document_read(record: DocumentRecord) -> DocumentRead:
    return DocumentRead(
        id=record.id,
        company_id=record.company_id,
        title=record.title,
        format=record.format,
        original_filename=record.original_filename,
        uploaded_at=record.uploaded_at,
    )
