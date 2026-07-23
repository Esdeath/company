import asyncio
import uuid
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import company_api.repository as repository_module
from company_api.content_store import ContentStore
from company_api.library_service import LibraryService, UploadInput
from company_api.models import Document, DocumentFormat
from company_api.repository import NewDocumentRecord, SqlAlchemyLibraryRepository
from company_api.schemas import UploadError

COMPANY_ID = uuid.UUID("fef2857a-8794-42b6-98c2-d5697d877632")
DOCUMENT_ID = uuid.UUID("5cc11f7f-23bd-4a5c-9dc7-a28058ac5ae2")
NOW = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


class FakeSession:
    def __init__(self, *, fail_refresh: bool = False, max_sort_order: int | None = 3) -> None:
        self.events: list[str] = []
        self.fail_refresh = fail_refresh
        self.max_sort_order = max_sort_order
        self.committed = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exc_type, exc_value, traceback

    def add(self, document: Document) -> None:
        self.events.append("add")

    async def scalar(self, statement: object) -> object:
        sql = str(statement)
        if "FROM companies" in sql and "FOR UPDATE" in sql:
            self.events.append("lock_company")
            return COMPANY_ID
        if "max(documents.sort_order)" in sql:
            self.events.append("read_max_sort_order")
            return self.max_sort_order
        raise AssertionError(f"Unexpected scalar statement: {sql}")

    async def flush(self) -> None:
        self.events.append("flush")

    async def refresh(self, document: Document) -> None:
        self.events.append("refresh")
        if self.fail_refresh:
            raise RuntimeError("refresh failed")
        document.uploaded_at = NOW

    async def commit(self) -> None:
        self.events.append("commit")
        self.committed = True


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self) -> FakeSession:
        return self.session


class ExistingCompanyRepository:
    def __init__(self, repository: SqlAlchemyLibraryRepository) -> None:
        self._repository = repository

    async def company_exists(self, company_id: uuid.UUID) -> bool:
        return company_id == COMPANY_ID

    async def insert_document(self, record: NewDocumentRecord):
        return await self._repository.insert_document(record)


def new_document() -> NewDocumentRecord:
    directory = f"companies/{COMPANY_ID}/{DOCUMENT_ID}"
    return NewDocumentRecord(
        id=DOCUMENT_ID,
        company_id=COMPANY_ID,
        title="Talk",
        format=DocumentFormat.MARKDOWN,
        source_path=f"{directory}/source.md",
        rendered_path=f"{directory}/rendered.html",
        original_filename="talk.md",
    )


def test_insert_materializes_before_commit_and_has_no_post_commit_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    repository = SqlAlchemyLibraryRepository(FakeSessionFactory(session))  # type: ignore[arg-type]
    original_materialize = repository_module._document_record

    def track_materialize(document: Document):
        session.events.append("materialize")
        return original_materialize(document)

    monkeypatch.setattr(repository_module, "_document_record", track_materialize)

    saved = run(repository.insert_document(new_document()))

    assert saved.uploaded_at == NOW
    assert saved.sort_order == 4
    assert session.events == [
        "lock_company",
        "read_max_sort_order",
        "add",
        "flush",
        "refresh",
        "materialize",
        "commit",
    ]
    assert session.committed is True


def test_refresh_failure_never_commits_document() -> None:
    session = FakeSession(fail_refresh=True)
    repository = SqlAlchemyLibraryRepository(FakeSessionFactory(session))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="refresh failed"):
        run(repository.insert_document(new_document()))

    assert session.events == [
        "lock_company",
        "read_max_sort_order",
        "add",
        "flush",
        "refresh",
    ]
    assert session.committed is False


def test_refresh_failure_compensates_committed_files(tmp_path: Path) -> None:
    session = FakeSession(fail_refresh=True)
    sql_repository = SqlAlchemyLibraryRepository(FakeSessionFactory(session))  # type: ignore[arg-type]
    repository = ExistingCompanyRepository(sql_repository)
    service = LibraryService(repository, ContentStore(tmp_path))  # type: ignore[arg-type]

    response = run(service.upload_documents(COMPANY_ID, [UploadInput("talk.md", b"# Talk")]))

    assert response.items == []
    assert response.errors == [UploadError(filename="talk.md", message="文件处理失败")]
    assert session.committed is False
    assert list(tmp_path.rglob("source.md")) == []
