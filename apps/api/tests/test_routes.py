import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from company_api.auth import NewSession, SessionRecord, token_hash
from company_api.config import Settings
from company_api.library_service import (
    CompanyNotEmpty,
    CompanyNotFound,
    DocumentNotFound,
    DocumentOrderMismatch,
    UploadInput,
)
from company_api.main import create_app
from company_api.models import DocumentFormat
from company_api.schemas import (
    CompanyCreate,
    CompanyOrder,
    CompanyRead,
    DocumentRead,
    UploadBatchResponse,
    UploadItem,
)

COMPANY_ID = uuid.UUID("fef2857a-8794-42b6-98c2-d5697d877632")
DOCUMENT_ID = uuid.UUID("5cc11f7f-23bd-4a5c-9dc7-a28058ac5ae2")
SECOND_DOCUMENT_ID = uuid.UUID("a0252f1b-fc6e-4d31-8d8e-eb2e65cbe444")
NOW = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)
ADMIN_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "aXR5J2OvFOW7Bb653Nn6mQ$Mjw20TGkSlMBsX4JsoCVfOe1DH6Cedzk01lTosf8YPU"
)
CSRF_TOKEN = "test-csrf-token"


class SuccessfulProbe:
    async def check(self) -> None:
        return None


class FakeAuthService:
    def __init__(self) -> None:
        self.logged_out = False

    async def issue_login_challenge(self) -> str:
        return "login-challenge"

    async def login(self, username: str, password: str, challenge: str) -> NewSession:
        assert (username, password, challenge) == ("admin", "secret", "login-challenge")
        return NewSession(
            session_token="valid-session",
            username="admin",
            csrf_token=CSRF_TOKEN,
            expires_at=NOW,
        )

    async def authenticate(self, session_token: str) -> SessionRecord | None:
        if session_token != "valid-session":
            return None
        return SessionRecord(
            token_hash=token_hash(session_token),
            username="admin",
            credential_fingerprint="test-fingerprint",
            csrf_token=CSRF_TOKEN,
            expires_at=NOW,
        )

    def csrf_is_valid(self, session: SessionRecord, submitted_token: str) -> bool:
        return session.csrf_token == submitted_token

    async def logout(self, session: SessionRecord) -> None:
        self.logged_out = True


class FakeService:
    def __init__(self, content_path: Path) -> None:
        self.content = content_path
        self.uploads: list[UploadInput] = []
        self.deleted_company: uuid.UUID | None = None
        self.deleted_document: uuid.UUID | None = None
        self.document_order: list[uuid.UUID] | None = None

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

    async def reorder_documents(
        self,
        company_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> list[DocumentRead]:
        assert company_id == COMPANY_ID
        self.document_order = document_ids
        return [
            document_read(document_id=document_id, sort_order=sort_order)
            for sort_order, document_id in enumerate(document_ids)
        ]

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


class MissingCompanyService(FakeService):
    async def reorder_documents(
        self,
        company_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> list[DocumentRead]:
        del company_id, document_ids
        raise CompanyNotFound


class MismatchedOrderService(FakeService):
    async def reorder_documents(
        self,
        company_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> list[DocumentRead]:
        del company_id, document_ids
        raise DocumentOrderMismatch


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
        sort_order=0,
        created_at=NOW,
    )


def test_company_order_rejects_duplicate_ids() -> None:
    duplicate = uuid.uuid4()
    with pytest.raises(ValidationError, match="公司顺序不能包含重复项"):
        CompanyOrder(company_ids=[duplicate, duplicate])


def document_read(
    *,
    document_id: uuid.UUID = DOCUMENT_ID,
    title: str = "Talk",
    document_format: DocumentFormat = DocumentFormat.MARKDOWN,
    sort_order: int = 0,
) -> DocumentRead:
    return DocumentRead(
        id=document_id,
        company_id=COMPANY_ID,
        title=title,
        format=document_format,
        original_filename="talk.md",
        sort_order=sort_order,
        uploaded_at=NOW,
    )


def settings(content_root: Path) -> Settings:
    return Settings(
        database_url="postgresql+psycopg://company:local@postgres:5432/company",
        admin_username="admin",
        admin_password_hash=ADMIN_HASH,
        cors_origins="http://localhost:3000",
        content_root=content_root,
        session_cookie_secure=False,
    )


def client_for(
    service: FakeService,
    content_root: Path,
    auth_service: FakeAuthService | None = None,
) -> TestClient:
    client = TestClient(
        create_app(
            settings(content_root),
            readiness_probe=SuccessfulProbe(),
            library_service=service,
            auth_service=auth_service or FakeAuthService(),
        )
    )
    client.cookies.set("company-admin-session", "valid-session")
    return client


def csrf_headers() -> dict[str, str]:
    return {"X-CSRF-Token": CSRF_TOKEN}


def test_company_routes(tmp_path: Path) -> None:
    service = FakeService(tmp_path / "content.html")
    with client_for(service, tmp_path) as client:
        listed = client.get("/api/v1/companies")
        created = client.post(
            "/api/v1/companies",
            json={"name": "New Co", "ticker": None, "market": "HKEX"},
            headers=csrf_headers(),
        )
        deleted = client.delete(f"/api/v1/companies/{COMPANY_ID}", headers=csrf_headers())

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
        response = client.delete(f"/api/v1/companies/{COMPANY_ID}", headers=csrf_headers())

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
            headers=csrf_headers(),
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
            headers=csrf_headers(),
        )
        deleted = client.delete(f"/api/v1/documents/{DOCUMENT_ID}", headers=csrf_headers())

    assert renamed.status_code == 200
    assert renamed.json()["title"] == "New title"
    assert renamed.json()["content_url"] == f"/api/v1/documents/{DOCUMENT_ID}/content"
    assert deleted.status_code == 204
    assert service.deleted_document == DOCUMENT_ID


def test_document_order_route_replaces_complete_order(tmp_path: Path) -> None:
    service = FakeService(tmp_path / "content.html")
    requested = [SECOND_DOCUMENT_ID, DOCUMENT_ID]
    with client_for(service, tmp_path) as client:
        response = client.put(
            f"/api/v1/companies/{COMPANY_ID}/documents/order",
            json={"document_ids": [str(document_id) for document_id in requested]},
            headers=csrf_headers(),
        )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(item) for item in requested]
    assert [item["sort_order"] for item in response.json()] == [0, 1]
    assert service.document_order == requested


def test_document_order_route_rejects_duplicate_ids(tmp_path: Path) -> None:
    service = FakeService(tmp_path / "content.html")
    with client_for(service, tmp_path) as client:
        response = client.put(
            f"/api/v1/companies/{COMPANY_ID}/documents/order",
            json={"document_ids": [str(DOCUMENT_ID), str(DOCUMENT_ID)]},
            headers=csrf_headers(),
        )

    assert response.status_code == 422
    assert service.document_order is None


def test_document_order_route_maps_company_and_set_errors(tmp_path: Path) -> None:
    with client_for(MissingCompanyService(tmp_path), tmp_path) as client:
        missing = client.put(
            f"/api/v1/companies/{COMPANY_ID}/documents/order",
            json={"document_ids": []},
            headers=csrf_headers(),
        )
    with client_for(MismatchedOrderService(tmp_path), tmp_path) as client:
        mismatched = client.put(
            f"/api/v1/companies/{COMPANY_ID}/documents/order",
            json={"document_ids": [str(DOCUMENT_ID)]},
            headers=csrf_headers(),
        )

    assert missing.status_code == 404
    assert missing.json() == {"detail": "公司不存在"}
    assert mismatched.status_code == 422
    assert mismatched.json() == {"detail": "资料顺序与当前目录不一致"}


def test_document_order_route_requires_session_and_csrf(tmp_path: Path) -> None:
    service = FakeService(tmp_path / "content.html")
    path = f"/api/v1/companies/{COMPANY_ID}/documents/order"
    with client_for(service, tmp_path) as client:
        client.cookies.clear()
        unauthenticated = client.put(path, json={"document_ids": []})
        client.cookies.set("company-admin-session", "valid-session")
        missing_csrf = client.put(path, json={"document_ids": []})

    assert unauthenticated.status_code == 401
    assert missing_csrf.status_code == 403


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


def test_mutations_require_a_session_and_csrf(tmp_path: Path) -> None:
    service = FakeService(tmp_path / "content.html")
    with client_for(service, tmp_path) as client:
        client.cookies.clear()
        unauthenticated = client.post("/api/v1/companies", json={"name": "Blocked"})
        client.cookies.set("company-admin-session", "valid-session")
        missing_csrf = client.post("/api/v1/companies", json={"name": "Blocked"})

    assert unauthenticated.status_code == 401
    assert missing_csrf.status_code == 403


def test_auth_session_login_and_logout_routes(tmp_path: Path) -> None:
    service = FakeService(tmp_path / "content.html")
    auth_service = FakeAuthService()
    with client_for(service, tmp_path, auth_service) as client:
        client.cookies.clear()
        anonymous = client.get("/api/v1/auth/session")
        logged_in = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "secret"},
            headers={"X-CSRF-Token": anonymous.json()["csrf_token"]},
        )
        logged_out = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": logged_in.json()["csrf_token"]},
        )

    assert anonymous.json() == {
        "authenticated": False,
        "username": None,
        "csrf_token": "login-challenge",
        "expires_at": None,
    }
    assert logged_in.status_code == 200
    assert logged_in.json()["authenticated"] is True
    assert "HttpOnly" in logged_in.headers["set-cookie"]
    assert "SameSite=strict" in logged_in.headers["set-cookie"]
    assert logged_out.status_code == 204
    assert auth_service.logged_out is True
