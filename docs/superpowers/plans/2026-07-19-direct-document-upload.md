# Direct HTML and Markdown Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an administrator choose a company, upload HTML or Markdown files, and make each successful upload readable from the public company workspace at once.

**Architecture:** FastAPI stores source files under a persistent content root and keeps company and document indexes in PostgreSQL. HTML files remain byte-for-byte unchanged. Markdown files keep their source and receive a generated `rendered.html` that inlines the approved modern-editorial stylesheet. The Vue management app writes through `/api/v1`; the Nuxt app reads the same index and embeds the selected document URL in a sandboxed iframe.

**Tech Stack:** Python 3.13, FastAPI 0.139.2, SQLAlchemy 2.0.51, Alembic 1.18.5, markdown-it-py 4.2.0, mdit-py-plugins 0.6.1, python-multipart 0.0.32, PostgreSQL 18.4, Vue 3.5.40, Vite 8.1.5, Nuxt 4.4.8, TypeScript 5.9.3, Docker Compose, Nginx.

## Global Constraints

- Accept `.html` and `.md` files. Reject other extensions without inspecting their content.
- Treat administrator uploads and Skill output as trusted input. Do not add static safety checks, metadata gates, SHA-256 gates, review states, publication states, Skill-specific adapters, content deduplication, or automatic categories.
- Save HTML source bytes unchanged. Save Markdown source bytes and a generated HTML copy.
- Derive the title from HTML `<title>` or the first Markdown level-one heading. Fall back to the original filename stem.
- Make each successful file visible after its own database and filesystem transaction completes. A failed file must not undo successful siblings in the same batch.
- Generate paths from UUIDs: `content/companies/<company-id>/<document-id>/source.<ext>` and optional `rendered.html`.
- Load HTML source and Markdown output through one iframe reader with an empty `sandbox` attribute.
- Preserve mobile-first company navigation through a drawer.
- Keep all management writes local during this milestone. Do not deploy the unauthenticated management API to the public Aliyun host; administrator sessions form a later plan.
- Use TDD for each behavior change and commit after each task passes its focused checks.

---

### Task 1: Replace the Retired Validation and Publication Contract

**Files:**
- Modify: `tests/docs.test.mjs`
- Modify: `doc/README.md`
- Modify: `doc/DEVELOPMENT.md`
- Modify: `doc/BACKEND.md`
- Modify: `doc/PRODUCT_UI.md`
- Modify: `doc/DEPLOYMENT.md`
- Modify: `doc/SEO.md`
- Modify: `doc/specs/2026-07-18-direct-document-upload-design.md`
- Modify: `doc/templates/markdown/template.html`

**Interfaces:**
- Consumes: approved design in `doc/specs/2026-07-18-direct-document-upload-design.md`.
- Produces: one current documentation contract used by later API and UI tasks.

- [ ] **Step 1: Replace old document-contract tests with direct-upload assertions**

Keep infrastructure health and Aliyun network assertions. Remove helpers and tests for static validation, load-check queues, draft/published/withdrawn states, and audit-only Markdown. Add these assertions:

```js
test('current docs define one direct HTML and Markdown upload flow', () => {
  const development = readCurrentDoc('DEVELOPMENT.md')
  const backend = readCurrentDoc('BACKEND.md')
  const productUi = readCurrentDoc('PRODUCT_UI.md')

  assert.match(development, /选择或新建公司[\s\S]+上传[\s\S]+HTML[\s\S]+Markdown[\s\S]+立即公开/)
  assert.match(backend, /source\.md[\s\S]+rendered\.html/)
  assert.match(productUi, /HTML 原文件[\s\S]+Markdown 生成页[\s\S]+同一个 iframe 阅读器/)

  for (const markdown of [development, backend, productUi]) {
    assert.doesNotMatch(markdown, /静态校验|load-check|草稿|已撤回|发布门禁|MD 不进入后端/)
  }
})

test('Markdown template is a supported runtime contract', () => {
  const readme = readCurrentDoc('README.md')
  assert.match(readme, /HTML 和 Markdown 都可以上传/)
  assert.match(readme, /templates\/markdown\/showcase\.html/)
  assert.equal(existsSync(currentDocUrl('templates/markdown/template.css')), true)
})
```

- [ ] **Step 2: Run the document tests and confirm they fail on the old contract**

Run: `node --test tests/docs.test.mjs`

Expected: FAIL because current documents still say HTML is the only publication format and Markdown stays outside runtime.

- [ ] **Step 3: Rewrite current documents around the approved flow**

Use this mainline in `doc/DEVELOPMENT.md` and link the approved spec:

```markdown
Skill 或人工资料 → 管理员选择公司 → 上传 HTML/Markdown → 按文件保存并建立索引 → 立即公开阅读
```

Define these exact rules in `doc/BACKEND.md`:

```markdown
- HTML 保存为 `source.html`，内容响应直接返回该文件。
- Markdown 保存为 `source.md`，上传时生成 `rendered.html`，内容响应返回生成文件。
- 数据库保存公司和资料索引，不保存文件正文。
- 系统只按扩展名分流，并处理读取、渲染、写入和数据库错误。
- 批量上传按文件提交；一个文件失败不撤销同批次中已完成的文件。
```

Update `doc/PRODUCT_UI.md` to describe company selection, multi-file upload, per-file results, immediate visibility, document list, one iframe reader, and the mobile drawer. Update deployment and SEO language from “published HTML” to “indexed document content.” Remove checker services, draft caches, withdrawal rules, and Markdown exclusion. Change `template.html` from a runtime-relative stylesheet link to an inline placeholder:

```html
<style>{{ document_styles }}</style>
```

- [ ] **Step 4: Run document tests**

Run: `node --test tests/docs.test.mjs`

Expected: all document tests PASS.

- [ ] **Step 5: Commit the contract change**

```bash
git add tests/docs.test.mjs doc
git commit -m "docs: adopt direct document upload flow"
```

---

### Task 2: Add Content Settings, Database Models, and the First Migration

**Files:**
- Modify: `apps/api/pyproject.toml`
- Modify: `apps/api/uv.lock`
- Modify: `apps/api/src/company_api/config.py`
- Modify: `apps/api/src/company_api/db.py`
- Create: `apps/api/src/company_api/models.py`
- Create: `apps/api/alembic.ini`
- Create: `apps/api/migrations/env.py`
- Create: `apps/api/migrations/script.py.mako`
- Create: `apps/api/migrations/versions/20260719_01_companies_documents.py`
- Modify: `apps/api/tests/test_config.py`
- Create: `apps/api/tests/test_models.py`

**Interfaces:**
- Produces: `Base`, `Company`, `Document`, `DocumentFormat`, `create_engine_and_session_factory(settings)`, and PostgreSQL tables `companies` and `documents`.

- [ ] **Step 1: Write failing settings and metadata tests**

```python
from pathlib import Path

from company_api.config import Settings
from company_api.models import Base


def test_content_root_defaults_to_data_content() -> None:
    settings = Settings(database_url="postgresql+psycopg://company@postgres/company")
    assert settings.content_root == Path("/data/content")


def test_company_and_document_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {"companies", "documents"}
    columns = Base.metadata.tables["documents"].c
    assert set(columns.keys()) == {
        "id", "company_id", "title", "format", "source_path",
        "rendered_path", "original_filename", "uploaded_at",
    }
```

- [ ] **Step 2: Run focused tests and confirm missing model failures**

Run: `cd apps/api && uv run pytest tests/test_config.py tests/test_models.py -q`

Expected: FAIL because `content_root` and `company_api.models` do not exist.

- [ ] **Step 3: Pin dependencies and regenerate the uv lock**

Add these exact dependencies:

```toml
"alembic==1.18.5",
"markdown-it-py==4.2.0",
"mdit-py-plugins==0.6.1",
"python-multipart==0.0.32",
```

Run: `cd apps/api && uv lock && uv sync --frozen`

- [ ] **Step 4: Add settings, models, and session construction**

Use UUID primary keys and timezone-aware timestamps. Keep ticker and market optional because a company can lack a listing code.

```python
class DocumentFormat(str, enum.Enum):
    HTML = "html"
    MARKDOWN = "markdown"


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), index=True)
    ticker: Mapped[str | None] = mapped_column(String(50))
    market: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    format: Mapped[DocumentFormat] = mapped_column(Enum(DocumentFormat, name="document_format"))
    source_path: Mapped[str] = mapped_column(String(1000), unique=True)
    rendered_path: Mapped[str | None] = mapped_column(String(1000), unique=True)
    original_filename: Mapped[str] = mapped_column(String(500))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
```

Add `content_root: Path = Path("/data/content")` to `Settings`. Add `async_sessionmaker[AsyncSession]` construction in `db.py` without changing readiness behavior.

- [ ] **Step 5: Add and verify the Alembic migration**

The upgrade creates `companies`, `document_format`, and `documents`; the downgrade drops them in reverse order. Configure `migrations/env.py` to read `DATABASE_URL` through `Settings` and use Alembic's async migration pattern.

Run: `make dev-infra`

Expected: the local PostgreSQL container becomes healthy.

Run: `cd apps/api && DATABASE_URL=postgresql+psycopg://company:company_local_only@127.0.0.1:5432/company uv run alembic upgrade head`

Expected: migration `20260719_01` applies to the local PostgreSQL container.

- [ ] **Step 6: Run focused API quality checks**

Run: `cd apps/api && uv run pytest tests/test_config.py tests/test_models.py -q && uv run ruff check . && uv run mypy src`

Expected: all commands PASS.

- [ ] **Step 7: Commit the database foundation**

```bash
git add apps/api
git commit -m "feat(api): add company and document schema"
```

---

### Task 3: Build the Universal Markdown Renderer

**Files:**
- Create: `apps/api/src/company_api/rendering.py`
- Create: `apps/api/src/company_api/templates/markdown/template.html`
- Create: `apps/api/src/company_api/templates/markdown/template.css`
- Create: `apps/api/tests/test_rendering.py`

**Interfaces:**
- Produces: `RenderedMarkdown(title: str, html: str)`, `render_markdown(source: str, fallback_title: str, document_meta: str = "") -> RenderedMarkdown`, and `extract_html_title(source: bytes, fallback_title: str) -> str`.

- [ ] **Step 1: Write renderer tests for three document shapes**

```python
@pytest.mark.parametrize(
    ("fixture_name", "expected"),
    [
        ("financial-snapshot.md", "<table>"),
        ("ceo-interview.md", "<blockquote>"),
        ("public-speech.md", "<ul>"),
    ],
)
def test_examples_share_one_template(fixture_name: str, expected: str) -> None:
    source = (EXAMPLE_ROOT / fixture_name).read_text()
    result = render_markdown(source, fixture_name.removesuffix(".md"))
    assert result.title
    assert expected in result.html
    assert "<style>" in result.html
    assert "{{" not in result.html


def test_first_h1_becomes_title_and_is_not_duplicated() -> None:
    result = render_markdown("导语\n\n# CEO 访谈\n\n正文", "fallback")
    assert result.title == "CEO 访谈"
    assert result.html.count("CEO 访谈") == 1


def test_extended_markdown_elements_use_the_same_page() -> None:
    source = "- [x] 已核对\n\n脚注[^1]\n\n[^1]: 来源\n\n![图](https://example.com/a.png)\n\n[视频](https://example.com/video)\n\n```text\ncode\n```"
    html = render_markdown(source, "资料").html
    for fragment in ("task-list-item", "footnote", "<img", "<a href=", "<pre>"):
        assert fragment in html


def test_html_title_falls_back_without_changing_source() -> None:
    source = b"<!doctype html><p>plain</p>"
    assert extract_html_title(source, "plain") == "plain"
    assert source == b"<!doctype html><p>plain</p>"
```

- [ ] **Step 2: Run focused tests and confirm missing renderer failure**

Run: `cd apps/api && uv run pytest tests/test_rendering.py -q`

Expected: FAIL because `company_api.rendering` does not exist.

- [ ] **Step 3: Implement Markdown parsing and title extraction**

Configure one parser for tables, task lists, and footnotes:

```python
markdown = (
    MarkdownIt("commonmark", {"html": True})
    .enable("table")
    .use(footnote_plugin)
    .use(tasklists_plugin)
)


@dataclass(frozen=True)
class RenderedMarkdown:
    title: str
    html: str


def render_markdown(source: str, fallback_title: str, document_meta: str = "") -> RenderedMarkdown:
    tokens = markdown.parse(source)
    title = fallback_title
    title_index = next(
        (index for index, token in enumerate(tokens) if token.type == "heading_open" and token.tag == "h1"),
        None,
    )
    if title_index is not None:
        title = tokens[title_index + 1].content.strip() or fallback_title
        tokens = tokens[:title_index] + tokens[title_index + 3 :]
    body = markdown.renderer.render(tokens, markdown.options, {})
    page = load_template().replace("{{ document_title }}", html.escape(title))
    page = page.replace("{{ document_meta }}", html.escape(document_meta))
    page = page.replace("{{ document_styles }}", load_styles())
    page = page.replace("{{ document_content }}", body)
    return RenderedMarkdown(title=title, html=page)
```

Implement a small `HTMLParser` subclass that captures the first `<title>` text. Do not rewrite or parse the HTML for any other purpose. Copy the approved stylesheet from `doc/templates/markdown/template.css` into package data and configure `uv_build` to include both template files.

- [ ] **Step 4: Run renderer and API checks**

Run: `cd apps/api && uv run pytest tests/test_rendering.py -q && uv run ruff check . && uv run mypy src`

Expected: all commands PASS.

- [ ] **Step 5: Commit the renderer**

```bash
git add apps/api doc/templates/markdown/template.html
git commit -m "feat(api): render Markdown with one editorial template"
```

---

### Task 4: Add Atomic Filesystem Storage

**Files:**
- Create: `apps/api/src/company_api/content_store.py`
- Create: `apps/api/tests/test_content_store.py`

**Interfaces:**
- Consumes: `render_markdown` and `extract_html_title` from Task 3.
- Produces: `PreparedDocument`, `StoredDocument`, `UnsupportedDocumentType`, and `ContentStore.prepare(company_id, document_id, filename, source)`, `commit(prepared)`, `discard(prepared)`, `delete(stored)`, `restore_deleted(stored)`.

- [ ] **Step 1: Write failing storage tests**

```python
def test_html_is_saved_byte_for_byte(tmp_path: Path) -> None:
    source = b"<!doctype html><title>CEO speech</title><p>\xff</p>"
    store = ContentStore(tmp_path)
    prepared = store.prepare(COMPANY_ID, DOCUMENT_ID, "speech.HTML", source)
    stored = store.commit(prepared)
    assert stored.source_path.read_bytes() == source
    assert stored.rendered_path is None
    assert stored.title == "CEO speech"


def test_markdown_keeps_source_and_writes_rendered_html(tmp_path: Path) -> None:
    source = "# 访谈\n\n> 原话".encode()
    store = ContentStore(tmp_path)
    stored = store.commit(store.prepare(COMPANY_ID, DOCUMENT_ID, "talk.md", source))
    assert stored.source_path.read_bytes() == source
    assert stored.rendered_path is not None
    assert "<blockquote>" in stored.rendered_path.read_text()


def test_unsupported_extension_leaves_no_files(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    with pytest.raises(UnsupportedDocumentType):
        store.prepare(COMPANY_ID, DOCUMENT_ID, "notes.pdf", b"pdf")
    assert list(tmp_path.rglob("*")) == []
```

- [ ] **Step 2: Run focused tests and confirm missing store failure**

Run: `cd apps/api && uv run pytest tests/test_content_store.py -q`

Expected: FAIL because `company_api.content_store` does not exist.

- [ ] **Step 3: Implement staging, commit, and compensation primitives**

Use these immutable records:

```python
@dataclass(frozen=True)
class PreparedDocument:
    title: str
    format: DocumentFormat
    original_filename: str
    staging_directory: Path
    final_directory: Path
    source_relative_path: str
    rendered_relative_path: str | None


@dataclass(frozen=True)
class StoredDocument:
    title: str
    format: DocumentFormat
    original_filename: str
    directory: Path
    source_path: Path
    rendered_path: Path | None
    source_relative_path: str
    rendered_relative_path: str | None
```

`prepare` writes into `<content-root>/.staging/<document-id>/`. `commit` calls `os.replace(staging_directory, final_directory)` on the same filesystem. `discard` removes staging files. `delete` renames the final directory into `<content-root>/.trash/<document-id>/`; `restore_deleted` moves it back when a database delete fails. Resolve all final paths from UUID objects and constant filenames, never from the upload filename.

- [ ] **Step 4: Run storage tests and static checks**

Run: `cd apps/api && uv run pytest tests/test_content_store.py -q && uv run ruff check . && uv run mypy src`

Expected: all commands PASS.

- [ ] **Step 5: Commit storage**

```bash
git add apps/api/src/company_api/content_store.py apps/api/tests/test_content_store.py
git commit -m "feat(api): store source and rendered documents atomically"
```

---

### Task 5: Implement Company and Document APIs

**Files:**
- Create: `apps/api/src/company_api/schemas.py`
- Create: `apps/api/src/company_api/repository.py`
- Create: `apps/api/src/company_api/library_service.py`
- Create: `apps/api/src/company_api/routes.py`
- Modify: `apps/api/src/company_api/main.py`
- Create: `apps/api/tests/test_library_service.py`
- Create: `apps/api/tests/test_routes.py`
- Modify: `apps/api/tests/test_health.py`

**Interfaces:**
- Consumes: database session factory from Task 2 and `ContentStore` from Task 4.
- Produces: JSON APIs and `GET /api/v1/documents/{document_id}/content`.

- [ ] **Step 1: Write failing service tests for per-file transactions**

Use a fake repository and `tmp_path`. Cover company creation, ordered lists, mixed-success upload, rename, document delete, and empty-company delete.

```python
async def test_batch_upload_keeps_successful_sibling(tmp_path: Path) -> None:
    service = LibraryService(FakeRepository(), ContentStore(tmp_path))
    response = await service.upload_documents(
        COMPANY_ID,
        [UploadInput("talk.md", b"# Talk"), UploadInput("notes.pdf", b"pdf")],
    )
    assert [item.title for item in response.items] == ["Talk"]
    assert response.errors == [UploadError(filename="notes.pdf", message="只支持 .html 和 .md 文件")]
    assert (tmp_path / "companies" / str(COMPANY_ID) / str(response.items[0].id)).is_dir()


async def test_database_failure_removes_committed_directory(tmp_path: Path) -> None:
    repository = FakeRepository(fail_on_document_insert=True)
    service = LibraryService(repository, ContentStore(tmp_path))
    response = await service.upload_documents(COMPANY_ID, [UploadInput("talk.md", b"# Talk")])
    assert response.items == []
    assert list((tmp_path / "companies").rglob("source.md")) == []
```

- [ ] **Step 2: Write failing route tests with an injected fake service**

Cover these endpoints and response shapes:

```text
GET    /api/v1/companies
POST   /api/v1/companies
DELETE /api/v1/companies/{company_id}
GET    /api/v1/companies/{company_id}/documents
POST   /api/v1/companies/{company_id}/documents
PATCH  /api/v1/documents/{document_id}
DELETE /api/v1/documents/{document_id}
GET    /api/v1/documents/{document_id}/content
```

Use this upload assertion:

```python
response = client.post(
    f"/api/v1/companies/{COMPANY_ID}/documents",
    files=[
        ("files", ("talk.md", b"# Talk", "text/markdown")),
        ("files", ("page.html", b"<title>Page</title>", "text/html")),
    ],
)
assert response.status_code == 200
assert [item["format"] for item in response.json()["items"]] == ["markdown", "html"]
```

- [ ] **Step 3: Run service and route tests and confirm failures**

Run: `cd apps/api && uv run pytest tests/test_library_service.py tests/test_routes.py -q`

Expected: FAIL because service, repository, schemas, and routes do not exist.

- [ ] **Step 4: Implement schemas and repository protocol**

Define `CompanyCreate(name, ticker=None, market=None)`, `CompanyRead`, `DocumentRead`, `DocumentRename(title)`, `UploadItem`, `UploadError`, and `UploadBatchResponse`. `DocumentRead.content_url` must equal `/api/v1/documents/<uuid>/content`.

The repository protocol must expose explicit transaction methods:

```python
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
```

`SqlAlchemyLibraryRepository` opens one `AsyncSession` per method. Insert and delete methods commit their own transaction; the service compensates filesystem changes on raised exceptions.

Order companies by normalized display name and UUID. Order documents by `uploaded_at DESC, id DESC` so a new upload appears first with deterministic ties. Allow duplicate company names and duplicate filenames; this milestone does not infer identity from names.

- [ ] **Step 5: Implement service and routes**

The route reads each FastAPI `UploadFile` once into `UploadInput(filename: str, content: bytes)`. `LibraryService.upload_documents` creates a UUID, prepares and commits content, then inserts the index. It catches known extension and rendering errors as per-file results. It logs a fixed message for unexpected failures and returns a generic Chinese message without paths or exception text.

`GET .../content` resolves the indexed relative path under `Settings.content_root` and returns `FileResponse` with `media_type="text/html; charset=utf-8"`, `X-Content-Type-Options: nosniff`, and `Cache-Control: no-cache`. HTML documents use `source_path`; Markdown documents use `rendered_path`.

Extend `create_app` with an optional `library_service` parameter for route tests. In production lifespan, construct the engine, session factory, repository, and store, then attach the service to `app.state`. Preserve the existing readiness probe injection and clean engine shutdown.

- [ ] **Step 6: Run all API checks**

Run: `cd apps/api && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`

Expected: all commands PASS.

- [ ] **Step 7: Commit the API slice**

```bash
git add apps/api
git commit -m "feat(api): add direct company document APIs"
```

---

### Task 6: Build the Management Upload Workspace

**Files:**
- Create: `apps/admin/src/types.ts`
- Create: `apps/admin/src/api.ts`
- Create: `apps/admin/src/components/CompanyPicker.vue`
- Create: `apps/admin/src/components/DocumentUpload.vue`
- Create: `apps/admin/src/components/DocumentList.vue`
- Modify: `apps/admin/src/App.vue`
- Modify: `apps/admin/src/style.css`
- Modify: `apps/admin/vite.config.ts`
- Replace: `apps/admin/tests/App.test.ts`
- Create: `apps/admin/tests/api.test.ts`

**Interfaces:**
- Consumes: Task 5 JSON endpoints.
- Produces: company creation/selection, multi-file upload, per-file result messages, rename, and delete controls under `/admin/`.

- [ ] **Step 1: Write failing API client tests**

```ts
it('uploads all selected files under one company', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], errors: [] })))
  const files = [new File(['# Talk'], 'talk.md'), new File(['<title>Page</title>'], 'page.html')]
  await uploadDocuments('company-1', files, fetchMock)
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
  expect(url).toBe('/api/v1/companies/company-1/documents')
  expect(init.method).toBe('POST')
  expect([...((init.body as FormData).getAll('files'))]).toEqual(files)
})
```

- [ ] **Step 2: Write failing workspace tests**

Mock `src/api.ts`. Assert that the app loads companies, creates a company with optional ticker and market, accepts multiple `.html,.md` files, shows separate success and error rows, refreshes the document list, renames a document, and confirms deletion. Assert one `h1`, labeled controls, an `aria-live="polite"` result region, and a public-site link.

- [ ] **Step 3: Run admin tests and confirm the scaffold fails them**

Run: `corepack pnpm --filter @company/admin test`

Expected: FAIL because the upload workspace and API client do not exist.

- [ ] **Step 4: Implement the typed client and focused components**

Use these public types:

```ts
export type Company = { id: string; name: string; ticker: string | null; market: string | null }
export type DocumentItem = {
  id: string
  company_id: string
  title: string
  format: 'html' | 'markdown'
  original_filename: string
  uploaded_at: string
  content_url: string
}
export type UploadBatch = {
  items: DocumentItem[]
  errors: Array<{ filename: string; message: string }>
}
```

`CompanyPicker.vue` owns company selection and the small create-company form. `DocumentUpload.vue` owns the multiple file input and upload state. `DocumentList.vue` owns rename and delete events. `App.vue` coordinates API calls and keeps the selected company after refresh.

Add this development proxy:

```ts
server: {
  host: '0.0.0.0',
  port: 5173,
  proxy: { '/api': 'http://127.0.0.1:8000' },
},
```

- [ ] **Step 5: Apply the approved mobile-first visual language**

Reuse the modern-editorial colors from `doc/templates/markdown/template.css`. Keep one-column controls below `48rem`; use a company rail and document workspace above `64rem`. Show `HTML` or `MD` badges, original filenames, upload time, and inline actions. Do not add validation, review, draft, or publish copy.

- [ ] **Step 6: Run the admin quality gate**

Run: `corepack pnpm --filter @company/admin check`

Expected: lint, typecheck, tests, and build PASS.

- [ ] **Step 7: Commit the management workspace**

```bash
git add apps/admin
git commit -m "feat(admin): upload company HTML and Markdown documents"
```

---

### Task 7: Build the Public Company and Document Workspace

**Files:**
- Create: `apps/web/app/types/content.ts`
- Create: `apps/web/app/api/library.ts`
- Create: `apps/web/app/components/CompanyDirectory.vue`
- Create: `apps/web/app/components/DocumentDirectory.vue`
- Create: `apps/web/app/components/DocumentReader.vue`
- Modify: `apps/web/app/app.vue`
- Modify: `apps/web/app/assets/css/main.css`
- Modify: `apps/web/nuxt.config.ts`
- Replace: `apps/web/tests/app.test.ts`
- Create: `apps/web/tests/DocumentReader.test.ts`

**Interfaces:**
- Consumes: company list, document list, and `content_url` from Task 5.
- Produces: desktop master-detail reading, mobile company drawer, document selection, loading/error/empty states, and one sandboxed iframe.

- [ ] **Step 1: Write failing reader and app tests**

```ts
it('uses one isolated iframe for HTML and rendered Markdown', () => {
  const wrapper = mount(DocumentReader, {
    props: { document: DOCUMENT, loading: false, error: null },
  })
  const frame = wrapper.get('iframe')
  expect(frame.attributes('src')).toBe(DOCUMENT.content_url)
  expect(frame.attributes()).toHaveProperty('sandbox', '')
  expect(frame.attributes('title')).toBe('阅读：管理层访谈')
})
```

Mock the library client in `app.test.ts`. Assert initial company/document selection, company changes, document changes, empty states, fetch errors, mobile drawer open/close, Escape close, backdrop close, and focus restoration to the drawer button.

- [ ] **Step 2: Run web tests and confirm the scaffold fails them**

Run: `corepack pnpm --filter @company/web test`

Expected: FAIL because public directory and reader components do not exist.

- [ ] **Step 3: Implement the public data client and components**

Use the same `Company` and `DocumentItem` response shape as the management app. `CompanyDirectory.vue` emits a company ID and implements desktop selection plus the mobile dialog drawer. `DocumentDirectory.vue` emits a document ID and shows format badges and upload dates. `DocumentReader.vue` renders progress, error with retry, empty state, or one iframe.

Keep `app.vue` responsible for these transitions:

```ts
watch(selectedCompanyId, async (companyId) => {
  documents.value = companyId ? await listDocuments(companyId) : []
  selectedDocumentId.value = documents.value[0]?.id ?? null
})
```

If an active document disappears after refresh, select the first remaining document. If no companies or documents exist, keep the relevant empty state visible.

- [ ] **Step 4: Proxy `/api` during direct Nuxt development**

Add this route rule while keeping `/healthz` unchanged:

```ts
routeRules: {
  '/api/**': { proxy: 'http://127.0.0.1:8000/api/**' },
},
```

- [ ] **Step 5: Implement the responsive workspace styles**

Below `48rem`, show one reader column and a “选择公司” button; the company list opens as a left drawer with a backdrop. Above `64rem`, use a fixed company rail, a document rail, and the remaining width for the iframe. Give the iframe a minimum height of `70svh`; let embedded documents manage their own scrolling.

- [ ] **Step 6: Run the web quality gate**

Run: `corepack pnpm --filter @company/web check`

Expected: lint, typecheck, tests, and build PASS.

- [ ] **Step 7: Commit the public workspace**

```bash
git add apps/web
git commit -m "feat(web): browse company research documents"
```

---

### Task 8: Wire Persistent Content into Compose and Run the Vertical Slice

**Files:**
- Modify: `.gitignore`
- Modify: `.env.example`
- Modify: `Makefile`
- Modify: `apps/api/Dockerfile`
- Modify: `compose.yaml`
- Modify: `scripts/compose-smoke.sh`
- Modify: `tests/scaffold.test.mjs`
- Modify: `README.md`

**Interfaces:**
- Consumes: all earlier tasks.
- Produces: migrations on startup, persistent `content_data`, smoke coverage for HTML and Markdown, and current developer commands.

- [ ] **Step 1: Add failing scaffold assertions for content persistence and migrations**

```js
test('Compose persists document content and migrates before API start', () => {
  assert.match(compose, /content_data:\/data\/content/)
  assert.match(compose, /CONTENT_ROOT:\s*\/data\/content/)
  assert.match(apiDockerfile, /alembic upgrade head/)
  assert.match(apiDockerfile, /mkdir -p \/data\/content/)
  assert.match(apiDockerfile, /chown[^\n]+10001|chown[^\n]+app/)
})
```

- [ ] **Step 2: Run scaffold tests and confirm missing runtime wiring**

Run: `node --test tests/scaffold.test.mjs`

Expected: FAIL because the content volume, migration command, and content setting are absent.

- [ ] **Step 3: Add runtime configuration and migration commands**

Add `CONTENT_ROOT=../../var/content` to `.env.example` for host development and ignore `/var/` in `.gitignore`. Override it with `CONTENT_ROOT: /data/content` in the Compose API environment. Add the named `content_data` volume at `/data/content`. In the image, copy `alembic.ini` and `migrations/`, create `/data/content`, and give UID `10001` ownership before switching to `USER app`.

Add an executable `apps/api/docker-entrypoint.sh`:

```sh
#!/bin/sh
set -eu
uv run --no-sync alembic upgrade head
exec uv run --no-sync uvicorn --factory company_api.main:create_app --host 0.0.0.0 --port 8000
```

Copy the entrypoint with executable permissions in the Dockerfile:

```dockerfile
COPY --chmod=755 docker-entrypoint.sh /app/docker-entrypoint.sh
CMD ["/app/docker-entrypoint.sh"]
```

Add `make db-upgrade` for host development and make `dev-api` depend on it:

```make
db-upgrade: require-env
	cd apps/api && $(UV) run --env-file ../../.env alembic upgrade head

dev-api: db-upgrade
	cd apps/api && $(UV) run --env-file ../../.env uvicorn --factory company_api.main:create_app --reload --host 0.0.0.0 --port 8000
```

- [ ] **Step 4: Extend real smoke coverage**

After health recovery, have `scripts/compose-smoke.sh`:

1. Create a uniquely named company through `POST /api/v1/companies`.
2. Upload `doc/templates/markdown/examples/ceo-interview.md` and `doc/templates/markdown/showcase.html` in one multipart request.
3. Assert two returned items and zero errors.
4. Fetch each `content_url`; assert the Markdown response contains `class="research-document"` and the HTML response contains `通用 Markdown 模板预览`.
5. Delete both documents, then delete the empty company.

Use `python3 -c` only to read response JSON in the smoke script; do not add `jq` as a host dependency.

- [ ] **Step 5: Update root developer documentation**

Change the milestone from “engineering scaffold” to “direct document vertical slice.” Document `make db-upgrade`, `CONTENT_ROOT`, the persistent `content_data` volume, management URL, upload flow, and the explicit local-only authentication limitation.

- [ ] **Step 6: Run the complete quality gate**

Run: `make check`

Expected: root Node tests, Nuxt checks, Vue/Vite checks, Ruff, mypy, and all API tests PASS.

- [ ] **Step 7: Run Compose acceptance and persistence checks**

```bash
make compose-up
make compose-smoke
make compose-down
docker volume inspect company-research-library_content_data
docker volume inspect company-research-library_postgres_data
```

Expected: smoke PASS; all containers stop; both named volumes remain.

- [ ] **Step 8: Commit the integrated vertical slice**

```bash
git add .gitignore .env.example Makefile apps/api/Dockerfile apps/api/docker-entrypoint.sh compose.yaml scripts/compose-smoke.sh tests/scaffold.test.mjs README.md
git commit -m "feat: complete direct document vertical slice"
```

---

## Final Verification

- [ ] Run `make check` and record the test counts.
- [ ] Run `make compose-up && make compose-smoke && make compose-down`.
- [ ] Confirm `docker compose --env-file .env ps --all --quiet` prints nothing.
- [ ] Confirm both PostgreSQL and content volumes still exist.
- [ ] Open `/admin/`, create a company, upload one HTML and one Markdown file, then open both from `/` at desktop and mobile widths.
- [ ] Confirm the HTML file stays unchanged and the Markdown document uses the approved modern-editorial template.
- [ ] Confirm repository status contains no unrelated files before the final review.
