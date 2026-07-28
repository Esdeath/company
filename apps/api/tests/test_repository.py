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
from company_api.models import Company, Document, DocumentFormat
from company_api.repository import (
    InvalidCompanyOrder,
    NewDocumentRecord,
    SqlAlchemyLibraryRepository,
)
from company_api.schemas import CompanyCreate, UploadError

COMPANY_ID = uuid.UUID("fef2857a-8794-42b6-98c2-d5697d877632")
DOCUMENT_ID = uuid.UUID("5cc11f7f-23bd-4a5c-9dc7-a28058ac5ae2")
NOW = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


class FakeSession:
    def __init__(
        self,
        *,
        companies: list[Company] | None = None,
        fail_refresh: bool = False,
        max_sort_order: int | None = 3,
        max_company_sort_order: int | None = 3,
    ) -> None:
        self.events: list[str] = []
        self.companies = list(companies or [])
        self.fail_refresh = fail_refresh
        self.max_sort_order = max_sort_order
        self.max_company_sort_order = max_company_sort_order
        self.added: Company | Document | None = None
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

    def add(self, document: Company | Document) -> None:
        self.events.append("add")
        self.added = document

    async def execute(self, statement: object) -> None:
        sql = str(statement)
        if sql == "LOCK TABLE companies IN SHARE ROW EXCLUSIVE MODE":
            self.events.append("lock_company_order")
            return None
        raise AssertionError(f"Unexpected execute statement: {sql}")

    async def scalar(self, statement: object) -> object:
        sql = str(statement)
        if "FROM companies" in sql and "FOR UPDATE" in sql:
            self.events.append("lock_company")
            return COMPANY_ID
        if "max(documents.sort_order)" in sql:
            self.events.append("read_max_sort_order")
            return self.max_sort_order
        if "max(companies.sort_order)" in sql:
            self.events.append("read_max_company_sort_order")
            return self.max_company_sort_order
        raise AssertionError(f"Unexpected scalar statement: {sql}")

    async def scalars(self, statement: object) -> "FakeScalars":
        sql = str(statement)
        if "FROM companies" not in sql:
            raise AssertionError(f"Unexpected scalars statement: {sql}")
        if "ORDER BY companies.sort_order ASC, companies.id ASC" in sql:
            self.events.append("list_companies")
        else:
            self.events.append("load_companies")
        return FakeScalars(self.companies)

    async def flush(self) -> None:
        self.events.append("flush")

    async def refresh(self, document: Company | Document) -> None:
        self.events.append("refresh")
        if self.fail_refresh:
            raise RuntimeError("refresh failed")
        if isinstance(document, Company):
            document.created_at = NOW
        else:
            document.uploaded_at = NOW

    async def commit(self) -> None:
        self.events.append("commit")
        self.committed = True


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self) -> FakeSession:
        return self.session


class FakeScalars:
    def __init__(self, values: list[Company]) -> None:
        self._values = values

    def all(self) -> list[Company]:
        return self._values


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


def saved_company(company_id: uuid.UUID, name: str, sort_order: int) -> Company:
    return Company(
        id=company_id,
        name=name,
        ticker=None,
        market=None,
        sort_order=sort_order,
        created_at=NOW,
    )


def test_create_company_serializes_order_and_appends_after_current_max() -> None:
    session = FakeSession(max_company_sort_order=3)
    repository = SqlAlchemyLibraryRepository(FakeSessionFactory(session))  # type: ignore[arg-type]

    saved = run(repository.create_company(CompanyCreate(name="Acme")))

    assert saved.sort_order == 4
    assert isinstance(session.added, Company)
    assert session.added.sort_order == 4
    assert session.events == [
        "lock_company_order",
        "read_max_company_sort_order",
        "add",
        "flush",
        "refresh",
        "commit",
    ]


def test_create_company_starts_empty_collection_at_zero() -> None:
    session = FakeSession(max_company_sort_order=None)
    repository = SqlAlchemyLibraryRepository(FakeSessionFactory(session))  # type: ignore[arg-type]

    saved = run(repository.create_company(CompanyCreate(name="Acme")))

    assert saved.sort_order == 0


def test_list_companies_orders_by_sort_order_then_id() -> None:
    session = FakeSession(
        companies=[
            saved_company(COMPANY_ID, "Zulu", 1),
            saved_company(DOCUMENT_ID, "Alpha", 0),
        ]
    )
    repository = SqlAlchemyLibraryRepository(FakeSessionFactory(session))  # type: ignore[arg-type]

    records = run(repository.list_companies())

    assert [record.id for record in records] == [COMPANY_ID, DOCUMENT_ID]
    assert session.events == ["list_companies"]


def test_reorder_companies_locks_before_replacing_complete_order() -> None:
    first = saved_company(COMPANY_ID, "One", 0)
    second = saved_company(DOCUMENT_ID, "Two", 1)
    session = FakeSession(companies=[first, second])
    repository = SqlAlchemyLibraryRepository(FakeSessionFactory(session))  # type: ignore[arg-type]

    records = run(repository.reorder_companies([second.id, first.id]))

    assert [(record.id, record.sort_order) for record in records] == [
        (DOCUMENT_ID, 0),
        (COMPANY_ID, 1),
    ]
    assert session.events == ["lock_company_order", "load_companies", "flush", "commit"]


def test_reorder_companies_rejects_unknown_company_id_after_locking() -> None:
    session = FakeSession(companies=[saved_company(COMPANY_ID, "One", 0)])
    repository = SqlAlchemyLibraryRepository(FakeSessionFactory(session))  # type: ignore[arg-type]

    with pytest.raises(InvalidCompanyOrder):
        run(repository.reorder_companies([DOCUMENT_ID]))

    assert session.events == ["lock_company_order", "load_companies"]
    assert session.committed is False


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
