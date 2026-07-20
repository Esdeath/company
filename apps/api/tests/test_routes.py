import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from company_api.config import Settings
from company_api.library_service import CompanyNotEmpty, DocumentNotFound, UploadInput
from company_api.main import create_app
from company_api.models import DocumentFormat
from company_api.schemas import (
    CompanyCreate,
    CompanyRead,
    DocumentRead,
    UploadBatchResponse,
    UploadItem,
)

COMPANY_ID = uuid.UUID("fef2857a-8794-42b6-98c2-d5697d877632")
DOCUMENT_ID = uuid.UUID("5cc11f7f-23bd-4a5c-9dc7-a28058ac5ae2")
NOW = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)


class SuccessfulProbe:
    async def check(self) -> None:
        return None


class FakeService:
    def __init__(self, content_path: Path) -> None:
        self.content = content_path
        self.uploads: list[UploadInput] = []
        self.deleted_company: uuid.UUID | None = None
        self.deleted_document: uuid.UUID | None = None

    async def list_companies(self) -> list[CompanyRead]:
        return [company_read()]

    async def create_company(self, data: CompanyCreate) -> CompanyRead:
        return company_read(name=data.name, ticker=data.ticker, market=data.market)

    async def delete_company(self, company_id: uuid.UUID) -> None:
        self.deleted_company = company_id

    async def list_documents(self, company_id: uuid.UUID) -> list[DocumentRead]:
        assert company_id == COMPANY_ID
        return [document_read()]

    async def upload_documents(
        self, company_id: uuid.UUID, uploads: list[UploadInput]
    ) -> UploadBatchResponse:
        assert company_id == COMPANY_ID
        self.uploads = uploads
        return UploadBatchResponse(
            items=[
                UploadItem(**document_read(document_format=DocumentFormat.MARKDOWN).model_dump()),
                UploadItem(
                    **document_read(
                        document_id=uuid.uuid4(),
                        document_format=DocumentFormat.HTML,
                    ).model_dump()
                ),
            ],
            errors=[],
        )

    async def rename_document(self, document_id: uuid.UUID, title: str) -> DocumentRead:
        assert document_id == DOCUMENT_ID
        return document_read(title=title)

    async def delete_document(self, document_id: uuid.UUID) -> None:
        self.deleted_document = document_id

    async def content_path(self, document_id: uuid.UUID) -> Path:
        assert document_id == DOCUMENT_ID
        return self.content


class NonEmptyCompanyService(FakeService):
    async def delete_company(self, company_id: uuid.UUID) -> None:
        del company_id
        raise CompanyNotEmpty


class MissingDocumentService(FakeService):
    async def content_path(self, document_id: uuid.UUID) -> Path:
        del document_id
        raise DocumentNotFound


def company_read(
    *,
    name: str = "Acme",
    ticker: str | None = "ACME",
    market: str | None = "NYSE",
) -> CompanyRead:
    return CompanyRead(
        id=COMPANY_ID,
        name=name,
        ticker=ticker,
        market=market,
        created_at=NOW,
    )


def document_read(
    *,
    document_id: uuid.UUID = DOCUMENT_ID,
    title: str = "Talk",
    document_format: DocumentFormat = DocumentFormat.MARKDOWN,
) -> DocumentRead:
    return DocumentRead(
        id=document_id,
        company_id=COMPANY_ID,
        title=title,
        format=document_format,
        original_filename="talk.md",
        uploaded_at=NOW,
    )


def settings(content_root: Path) -> Settings:
    return Settings(
        database_url="postgresql+psycopg://company:local@postgres:5432/company",
        cors_origins="http://localhost:3000",
        content_root=content_root,
    )


def client_for(service: FakeService, content_root: Path) -> TestClient:
    return TestClient(
        create_app(
            settings(content_root),
            readiness_probe=SuccessfulProbe(),
            library_service=service,
        )
    )


def test_company_routes(tmp_path: Path) -> None:
    service = FakeService(tmp_path / "content.html")
    with client_for(service, tmp_path) as client:
        listed = client.get("/api/v1/companies")
        created = client.post(
            "/api/v1/companies",
            json={"name": "New Co", "ticker": None, "market": "HKEX"},
        )
        deleted = client.delete(f"/api/v1/companies/{COMPANY_ID}")

    assert listed.status_code == 200
    assert listed.json()[0]["id"] == str(COMPANY_ID)
    assert created.status_code == 201
    assert created.json()["name"] == "New Co"
    assert "created_at" in created.json()
    assert deleted.status_code == 204
    assert service.deleted_company == COMPANY_ID


def test_non_empty_company_delete_returns_conflict(tmp_path: Path) -> None:
    service = NonEmptyCompanyService(tmp_path / "content.html")
    with client_for(service, tmp_path) as client:
        response = client.delete(f"/api/v1/companies/{COMPANY_ID}")

    assert response.status_code == 409
    assert response.json() == {"detail": "公司仍有资料，无法删除"}


def test_document_list_and_upload_routes(tmp_path: Path) -> None:
    service = FakeService(tmp_path / "content.html")
    with client_for(service, tmp_path) as client:
        listed = client.get(f"/api/v1/companies/{COMPANY_ID}/documents")
        response = client.post(
            f"/api/v1/companies/{COMPANY_ID}/documents",
            files=[
                ("files", ("talk.md", b"# Talk", "text/markdown")),
                ("files", ("page.html", b"<title>Page</title>", "text/html")),
            ],
        )

    assert listed.status_code == 200
    assert listed.json() == [document_read().model_dump(mode="json")]
    assert response.status_code == 200
    assert [item["format"] for item in response.json()["items"]] == ["markdown", "html"]
    assert set(response.json()["items"][0]) == {
        "id",
        "title",
        "format",
        "content_url",
    }
    assert service.uploads == [
        UploadInput("talk.md", b"# Talk"),
        UploadInput("page.html", b"<title>Page</title>"),
    ]


def test_document_rename_and_delete_routes(tmp_path: Path) -> None:
    service = FakeService(tmp_path / "content.html")
    with client_for(service, tmp_path) as client:
        renamed = client.patch(
            f"/api/v1/documents/{DOCUMENT_ID}",
            json={"title": "New title"},
        )
        deleted = client.delete(f"/api/v1/documents/{DOCUMENT_ID}")

    assert renamed.status_code == 200
    assert renamed.json()["title"] == "New title"
    assert renamed.json()["content_url"] == f"/api/v1/documents/{DOCUMENT_ID}/content"
    assert deleted.status_code == 204
    assert service.deleted_document == DOCUMENT_ID


def test_content_route_returns_html_with_safe_headers(tmp_path: Path) -> None:
    content = tmp_path / "content.html"
    content.write_bytes(b"<title>Talk</title>")
    service = FakeService(content)

    with client_for(service, tmp_path) as client:
        response = client.get(f"/api/v1/documents/{DOCUMENT_ID}/content")

    assert response.status_code == 200
    assert response.content == b"<title>Talk</title>"
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-cache"


def test_content_route_supports_a_bodyless_head_probe(tmp_path: Path) -> None:
    content = tmp_path / "content.html"
    content.write_bytes(b"<title>Talk</title>")
    service = FakeService(content)

    with client_for(service, tmp_path) as client:
        response = client.head(f"/api/v1/documents/{DOCUMENT_ID}/content")

    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-cache"


def test_missing_content_returns_not_found(tmp_path: Path) -> None:
    service = MissingDocumentService(tmp_path / "content.html")

    with client_for(service, tmp_path) as client:
        response = client.get(f"/api/v1/documents/{DOCUMENT_ID}/content")

    assert response.status_code == 404
    assert response.json() == {"detail": "资料不存在"}
