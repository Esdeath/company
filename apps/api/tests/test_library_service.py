import asyncio
import logging
import uuid
from collections.abc import Coroutine
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from company_api.content_store import ContentStore
from company_api.library_service import (
    CompanyNotEmpty,
    CompanyNotFound,
    DocumentNotFound,
    LibraryService,
    UploadInput,
)
from company_api.models import DocumentFormat
from company_api.repository import CompanyRecord, DocumentRecord, NewDocumentRecord
from company_api.schemas import CompanyCreate, UploadError

COMPANY_ID = uuid.UUID("fef2857a-8794-42b6-98c2-d5697d877632")
OTHER_COMPANY_ID = uuid.UUID("a0252f1b-fc6e-4d31-8d8e-eb2e65cbe444")
DOCUMENT_ID = uuid.UUID("5cc11f7f-23bd-4a5c-9dc7-a28058ac5ae2")
NOW = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


class FakeRepository:
    def __init__(
        self,
        *,
        companies: list[CompanyRecord] | None = None,
        documents: list[DocumentRecord] | None = None,
        fail_on_document_insert: bool = False,
        fail_on_document_delete: bool = False,
    ) -> None:
        self.companies = list(companies or [])
        self.documents = list(documents or [])
        self.fail_on_document_insert = fail_on_document_insert
        self.fail_on_document_delete = fail_on_document_delete

    async def create_company(self, data: CompanyCreate) -> CompanyRecord:
        record = CompanyRecord(
            id=uuid.uuid4(),
            name=data.name,
            ticker=data.ticker,
            market=data.market,
            created_at=NOW,
        )
        self.companies.append(record)
        return record

    async def list_companies(self) -> list[CompanyRecord]:
        return list(self.companies)

    async def company_exists(self, company_id: uuid.UUID) -> bool:
        return any(company.id == company_id for company in self.companies)

    async def delete_empty_company(self, company_id: uuid.UUID) -> bool:
        if any(document.company_id == company_id for document in self.documents):
            return False
        before = len(self.companies)
        self.companies = [company for company in self.companies if company.id != company_id]
        return len(self.companies) != before

    async def insert_document(self, record: NewDocumentRecord) -> DocumentRecord:
        if self.fail_on_document_insert:
            raise RuntimeError("postgresql://secret")
        saved = DocumentRecord(
            id=record.id,
            company_id=record.company_id,
            title=record.title,
            format=record.format,
            source_path=record.source_path,
            rendered_path=record.rendered_path,
            original_filename=record.original_filename,
            uploaded_at=NOW,
        )
        self.documents.append(saved)
        return saved

    async def list_documents(self, company_id: uuid.UUID) -> list[DocumentRecord]:
        return [document for document in self.documents if document.company_id == company_id]

    async def get_document(self, document_id: uuid.UUID) -> DocumentRecord | None:
        return next(
            (document for document in self.documents if document.id == document_id),
            None,
        )

    async def rename_document(self, document_id: uuid.UUID, title: str) -> DocumentRecord | None:
        record = await self.get_document(document_id)
        if record is None:
            return None
        renamed = DocumentRecord(
            id=record.id,
            company_id=record.company_id,
            title=title,
            format=record.format,
            source_path=record.source_path,
            rendered_path=record.rendered_path,
            original_filename=record.original_filename,
            uploaded_at=record.uploaded_at,
        )
        self.documents[self.documents.index(record)] = renamed
        return renamed

    async def delete_document(self, document_id: uuid.UUID) -> DocumentRecord | None:
        if self.fail_on_document_delete:
            raise RuntimeError("postgresql://secret")
        record = await self.get_document(document_id)
        if record is not None:
            self.documents.remove(record)
        return record


class CancelledInsertRepository(FakeRepository):
    async def insert_document(self, record: NewDocumentRecord) -> DocumentRecord:
        raise asyncio.CancelledError


def company(company_id: uuid.UUID, name: str) -> CompanyRecord:
    return CompanyRecord(
        id=company_id,
        name=name,
        ticker=None,
        market=None,
        created_at=NOW,
    )


def document(
    document_id: uuid.UUID,
    *,
    company_id: uuid.UUID = COMPANY_ID,
    title: str = "Document",
    uploaded_at: datetime = NOW,
    document_format: DocumentFormat = DocumentFormat.HTML,
) -> DocumentRecord:
    directory = f"companies/{company_id}/{document_id}"
    return DocumentRecord(
        id=document_id,
        company_id=company_id,
        title=title,
        format=document_format,
        source_path=(
            f"{directory}/source.{('html' if document_format is DocumentFormat.HTML else 'md')}"
        ),
        rendered_path=(
            None if document_format is DocumentFormat.HTML else f"{directory}/rendered.html"
        ),
        original_filename="document.html",
        uploaded_at=uploaded_at,
    )


def test_create_company_and_allow_duplicate_name(tmp_path: Path) -> None:
    repository = FakeRepository()
    service = LibraryService(repository, ContentStore(tmp_path))

    first = run(service.create_company(CompanyCreate(name="Acme")))
    second = run(service.create_company(CompanyCreate(name="Acme")))

    assert first.name == second.name == "Acme"
    assert first.id != second.id


def test_company_list_sorts_normalized_name_then_uuid(tmp_path: Path) -> None:
    repository = FakeRepository(
        companies=[
            company(COMPANY_ID, "  zebra"),
            company(OTHER_COMPANY_ID, "Alpha"),
            company(DOCUMENT_ID, "alpha "),
        ]
    )
    service = LibraryService(repository, ContentStore(tmp_path))

    result = run(service.list_companies())

    assert [item.id for item in result] == [DOCUMENT_ID, OTHER_COMPANY_ID, COMPANY_ID]


def test_document_list_sorts_newest_then_id(tmp_path: Path) -> None:
    oldest = document(DOCUMENT_ID, uploaded_at=NOW - timedelta(days=1))
    tied_low = document(OTHER_COMPANY_ID)
    tied_high = document(COMPANY_ID)
    repository = FakeRepository(
        companies=[company(COMPANY_ID, "Acme")],
        documents=[oldest, tied_low, tied_high],
    )
    service = LibraryService(repository, ContentStore(tmp_path))

    result = run(service.list_documents(COMPANY_ID))

    assert [item.id for item in result] == [COMPANY_ID, OTHER_COMPANY_ID, DOCUMENT_ID]


def test_batch_upload_keeps_successful_sibling(tmp_path: Path) -> None:
    repository = FakeRepository(companies=[company(COMPANY_ID, "Acme")])
    service = LibraryService(repository, ContentStore(tmp_path))

    response = run(
        service.upload_documents(
            COMPANY_ID,
            [UploadInput("talk.md", b"# Talk"), UploadInput("notes.pdf", b"pdf")],
        )
    )

    assert [item.title for item in response.items] == ["Talk"]
    assert response.errors == [
        UploadError(filename="notes.pdf", message="只支持 .html 和 .md 文件")
    ]
    assert (tmp_path / "companies" / str(COMPANY_ID) / str(response.items[0].id)).is_dir()


def test_database_failure_removes_committed_directory(tmp_path: Path) -> None:
    repository = FakeRepository(
        companies=[company(COMPANY_ID, "Acme")],
        fail_on_document_insert=True,
    )
    service = LibraryService(repository, ContentStore(tmp_path))

    response = run(service.upload_documents(COMPANY_ID, [UploadInput("talk.md", b"# Talk")]))

    assert response.items == []
    assert response.errors == [UploadError(filename="talk.md", message="文件处理失败")]
    assert list((tmp_path / "companies").rglob("source.md")) == []


def test_cancelled_database_insert_removes_files_and_propagates_cancellation(
    tmp_path: Path,
) -> None:
    repository = CancelledInsertRepository(companies=[company(COMPANY_ID, "Acme")])
    service = LibraryService(repository, ContentStore(tmp_path))

    with pytest.raises(asyncio.CancelledError):
        run(service.upload_documents(COMPANY_ID, [UploadInput("talk.md", b"# Talk")]))

    company_directory = tmp_path / "companies" / str(COMPANY_ID)
    assert list(company_directory.rglob("source.md")) == []
    assert list(company_directory.rglob("rendered.html")) == []
    assert not company_directory.exists()


def test_unexpected_upload_failure_logs_only_fixed_message(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = FakeRepository(
        companies=[company(COMPANY_ID, "Acme")],
        fail_on_document_insert=True,
    )
    service = LibraryService(repository, ContentStore(tmp_path))

    with caplog.at_level(logging.ERROR, logger="company_api.library_service"):
        response = run(service.upload_documents(COMPANY_ID, [UploadInput("talk.md", b"# Talk")]))

    assert response.errors == [UploadError(filename="talk.md", message="文件处理失败")]
    assert caplog.messages == ["Document upload failed"]
    assert all(record.exc_info is None for record in caplog.records)


def test_upload_requires_existing_company(tmp_path: Path) -> None:
    service = LibraryService(FakeRepository(), ContentStore(tmp_path))

    with pytest.raises(CompanyNotFound):
        run(service.upload_documents(COMPANY_ID, [UploadInput("talk.md", b"# Talk")]))


def test_rename_document(tmp_path: Path) -> None:
    repository = FakeRepository(documents=[document(DOCUMENT_ID)])
    service = LibraryService(repository, ContentStore(tmp_path))

    renamed = run(service.rename_document(DOCUMENT_ID, "New title"))

    assert renamed.title == "New title"


def test_rename_missing_document(tmp_path: Path) -> None:
    service = LibraryService(FakeRepository(), ContentStore(tmp_path))

    with pytest.raises(DocumentNotFound):
        run(service.rename_document(DOCUMENT_ID, "New title"))


def test_delete_document_stages_then_purges_files(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    stored = store.commit(store.prepare(COMPANY_ID, DOCUMENT_ID, "report.html", b"source"))
    record = document(DOCUMENT_ID)
    repository = FakeRepository(documents=[record])
    service = LibraryService(repository, store)

    run(service.delete_document(DOCUMENT_ID))

    assert repository.documents == []
    assert not stored.directory.exists()
    assert not (tmp_path / ".trash").exists()


def test_delete_document_restores_files_when_database_fails(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    stored = store.commit(store.prepare(COMPANY_ID, DOCUMENT_ID, "report.html", b"source"))
    repository = FakeRepository(
        documents=[document(DOCUMENT_ID)],
        fail_on_document_delete=True,
    )
    service = LibraryService(repository, store)

    with pytest.raises(RuntimeError, match="secret"):
        run(service.delete_document(DOCUMENT_ID))

    assert stored.source_path.read_bytes() == b"source"
    assert not (tmp_path / ".trash").exists()


def test_delete_only_empty_company(tmp_path: Path) -> None:
    repository = FakeRepository(
        companies=[company(COMPANY_ID, "Acme")],
        documents=[document(DOCUMENT_ID)],
    )
    service = LibraryService(repository, ContentStore(tmp_path))

    with pytest.raises(CompanyNotEmpty):
        run(service.delete_company(COMPANY_ID))

    repository.documents.clear()
    run(service.delete_company(COMPANY_ID))
    assert repository.companies == []


def test_delete_missing_company(tmp_path: Path) -> None:
    service = LibraryService(FakeRepository(), ContentStore(tmp_path))

    with pytest.raises(CompanyNotFound):
        run(service.delete_company(COMPANY_ID))


def test_content_path_selects_html_source_and_markdown_rendered(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    html_stored = store.commit(
        store.prepare(COMPANY_ID, DOCUMENT_ID, "report.html", b"<title>HTML</title>")
    )
    markdown_id = uuid.uuid4()
    markdown_stored = store.commit(
        store.prepare(COMPANY_ID, markdown_id, "report.md", b"# Markdown")
    )
    repository = FakeRepository(
        documents=[
            document(DOCUMENT_ID),
            document(markdown_id, document_format=DocumentFormat.MARKDOWN),
        ]
    )
    service = LibraryService(repository, store)

    assert run(service.content_path(DOCUMENT_ID)) == html_stored.source_path
    assert run(service.content_path(markdown_id)) == markdown_stored.rendered_path


def test_content_path_rejects_arbitrary_database_path(tmp_path: Path) -> None:
    outside = tmp_path.parent / "secret.html"
    outside.write_text("secret")
    unsafe = replace(document(DOCUMENT_ID), source_path="../secret.html")
    service = LibraryService(FakeRepository(documents=[unsafe]), ContentStore(tmp_path))

    with pytest.raises(DocumentNotFound):
        run(service.content_path(DOCUMENT_ID))


def test_content_path_rejects_symlink(tmp_path: Path) -> None:
    directory = tmp_path / "companies" / str(COMPANY_ID) / str(DOCUMENT_ID)
    directory.mkdir(parents=True)
    outside = tmp_path / "outside.html"
    outside.write_text("secret")
    (directory / "source.html").symlink_to(outside)
    service = LibraryService(
        FakeRepository(documents=[document(DOCUMENT_ID)]),
        ContentStore(tmp_path),
    )

    with pytest.raises(DocumentNotFound):
        run(service.content_path(DOCUMENT_ID))
