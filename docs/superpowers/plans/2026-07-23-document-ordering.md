# Document Ordering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let administrators drag documents into an explicit per-company order, persist that order atomically, append new uploads at the bottom, and render the same order on the public site.

**Architecture:** PostgreSQL owns ordering through a non-negative `sort_order` column. Repository transactions lock the company row while assigning an upload position or replacing the complete order; FastAPI exposes one full-order `PUT` endpoint. The admin applies a local reorder, saves it immediately, and rolls back on failure, while the public Web app keeps rendering the API array without a second sorting rule.

**Tech Stack:** PostgreSQL, SQLAlchemy 2 async, Alembic, FastAPI/Pydantic, Vue 3 Composition API, Pointer Events, TypeScript, Vitest, pytest.

## Global Constraints

- Existing documents must retain the current `uploaded_at DESC, id DESC` display order after migration.
- Successful uploads append in request order; failed files do not reserve positions.
- Reordering is limited to one company and submits that company's complete document ID list.
- Mouse, touch, and keyboard ordering must not break rename or delete controls.
- The public Web app must consume API order without client-side sorting.
- Do not modify or revert unrelated existing worktree changes.

---

## File Map

- Create `apps/api/migrations/versions/20260723_03_document_sort_order.py`: add, backfill, constrain, and index `documents.sort_order`.
- Modify `apps/api/src/company_api/models.py`: map `Document.sort_order`.
- Modify `apps/api/src/company_api/repository.py`: carry sort order through records, append under a company lock, list by sort order, and atomically replace a company's order.
- Modify `apps/api/src/company_api/schemas.py`: expose `sort_order` and define the full-order request.
- Modify `apps/api/src/company_api/library_service.py`: expose reorder operation and map repository validation to domain errors.
- Modify `apps/api/src/company_api/routes.py`: add the authenticated reorder route and status mapping.
- Modify `apps/admin/src/api.ts`, `apps/admin/src/types.ts`, `apps/admin/src/App.vue`: call the reorder route and own optimistic state/rollback.
- Modify `apps/admin/src/components/DocumentList.vue`, `apps/admin/src/style.css`: implement whole-row pointer and keyboard sorting with stable feedback.
- Modify `apps/web/app/types/content.ts`: accept the API's `sort_order` field.
- Modify existing API, Admin, and Web tests next to the behavior they cover.

### Task 1: Persist and Append Document Order

**Files:**
- Create: `apps/api/migrations/versions/20260723_03_document_sort_order.py`
- Modify: `apps/api/src/company_api/models.py`
- Modify: `apps/api/src/company_api/repository.py`
- Modify: `apps/api/tests/test_models.py`
- Modify: `apps/api/tests/test_repository.py`

**Interfaces:**
- Produces: `Document.sort_order: int` and `DocumentRecord.sort_order: int`; upload callers keep using the existing `NewDocumentRecord` without choosing positions.
- Produces: `SqlAlchemyLibraryRepository.insert_document(record)` assigns `max(sort_order) + 1` while holding `SELECT companies.id ... FOR UPDATE`.

- [ ] **Step 1: Write failing model and repository tests**

Add `sort_order` to the expected document columns in `test_models.py`. Extend the repository fake session so it records `execute`, returns a locked company ID and current maximum position, then assert:

```python
saved = run(repository.insert_document(new_document()))

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
```

Add a migration contract test that imports revision `20260723_03`, captures Alembic operations, and verifies the backfill SQL contains:

```sql
row_number() OVER (
    PARTITION BY company_id
    ORDER BY uploaded_at DESC, id DESC
) - 1
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd apps/api
uv run pytest tests/test_models.py tests/test_repository.py -q
```

Expected: failures report the missing `sort_order` column/revision and missing append queries.

- [ ] **Step 3: Add the migration and minimal persistence code**

Create revision `20260723_03` with `down_revision = "20260721_02"`. Its upgrade must:

```python
op.add_column("documents", sa.Column("sort_order", sa.BigInteger(), nullable=True))
op.execute(sa.text("""
    WITH ranked AS (
        SELECT id,
               row_number() OVER (
                   PARTITION BY company_id
                   ORDER BY uploaded_at DESC, id DESC
               ) - 1 AS position
        FROM documents
    )
    UPDATE documents
    SET sort_order = ranked.position
    FROM ranked
    WHERE documents.id = ranked.id
"""))
op.alter_column("documents", "sort_order", nullable=False)
op.create_check_constraint("ck_documents_sort_order_nonnegative", "documents", "sort_order >= 0")
op.create_index("ix_documents_company_sort_order", "documents", ["company_id", "sort_order"])
```

Map the column with `BigInteger` and include it in `_document_record`. In `insert_document`, lock `Company.id`, calculate `coalesce(max(Document.sort_order), -1) + 1`, and pass that value into `Document(...)`. Keep file/database compensation semantics unchanged.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the command from Step 2. Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add apps/api/migrations/versions/20260723_03_document_sort_order.py apps/api/src/company_api/models.py apps/api/src/company_api/repository.py apps/api/tests/test_models.py apps/api/tests/test_repository.py
git commit -m "feat(api): persist document order"
```

### Task 2: Atomically Replace a Company's Order

**Files:**
- Modify: `apps/api/src/company_api/repository.py`
- Modify: `apps/api/src/company_api/schemas.py`
- Modify: `apps/api/src/company_api/library_service.py`
- Modify: `apps/api/src/company_api/routes.py`
- Modify: `apps/api/tests/test_library_service.py`
- Modify: `apps/api/tests/test_routes.py`

**Interfaces:**
- Consumes: `DocumentRecord.sort_order` from Task 1.
- Produces: `DocumentOrder(document_ids: list[UUID])` with Pydantic duplicate rejection.
- Produces: `LibraryRepository.reorder_documents(company_id, document_ids) -> list[DocumentRecord] | None`; `None` means the company does not exist, while `InvalidDocumentOrder` means the ID set differs.
- Produces: `LibraryOperations.reorder_documents(company_id, document_ids) -> list[DocumentRead]`.

- [ ] **Step 1: Write failing service tests**

Extend `FakeRepository` with a reorder call log. Add tests for a successful full reorder, an unknown company, and a mismatched set:

```python
result = run(service.reorder_documents(COMPANY_ID, [second.id, first.id]))

assert [item.id for item in result] == [second.id, first.id]
assert [item.sort_order for item in result] == [0, 1]
```

Also change the existing list-order test to provide positions that conflict with timestamps and assert position order wins.

- [ ] **Step 2: Run service tests and verify RED**

```bash
cd apps/api
uv run pytest tests/test_library_service.py -q
```

Expected: failures report missing `reorder_documents`, `sort_order`, and position-based list behavior.

- [ ] **Step 3: Implement repository and service behavior**

Define repository exception `InvalidDocumentOrder`. The SQL repository method must lock the company row, load every company document, compare `len(ids)`, `len(set(ids))`, and UUID sets, assign positions with `enumerate(document_ids)`, flush, materialize results in requested order, and commit once. Change list ordering to:

```python
.order_by(Document.sort_order.asc(), Document.id.asc())
```

Remove the service's timestamp sort. Map a missing company to `CompanyNotFound` and `InvalidDocumentOrder` to domain exception `DocumentOrderMismatch`.

- [ ] **Step 4: Run service tests and verify GREEN**

Run the command from Step 2. Expected: all service tests pass.

- [ ] **Step 5: Write failing route and schema tests**

Add route tests that call:

```python
response = client.put(
    f"/api/v1/companies/{COMPANY_ID}/documents/order",
    json={"document_ids": [str(SECOND_DOCUMENT_ID), str(DOCUMENT_ID)]},
    headers=csrf_headers(),
)
```

Assert ordered response data, `422` for duplicate/mismatched IDs, `404` for a missing company, `401` without a session, and `403` without CSRF.

- [ ] **Step 6: Run route tests and verify RED**

```bash
cd apps/api
uv run pytest tests/test_routes.py -q
```

Expected: the reorder request returns `405` or validation fields are missing.

- [ ] **Step 7: Add schema and route**

Add:

```python
class DocumentOrder(BaseModel):
    document_ids: list[UUID]

    @field_validator("document_ids")
    @classmethod
    def unique_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("资料顺序不能包含重复项")
        return value
```

Expose `sort_order` on `DocumentRead`. Add the `PUT` route before `/{document_id}` routes, require the existing write dependency, and map `DocumentOrderMismatch` to `HTTPException(422, "资料顺序与当前目录不一致")`.

- [ ] **Step 8: Run focused API tests and commit Task 2**

```bash
cd apps/api
uv run pytest tests/test_library_service.py tests/test_routes.py -q
git add src/company_api/repository.py src/company_api/schemas.py src/company_api/library_service.py src/company_api/routes.py tests/test_library_service.py tests/test_routes.py
git commit -m "feat(api): reorder company documents"
```

Expected: all selected tests pass and the commit contains only Task 2 files.

### Task 3: Save and Roll Back Admin Reorders

**Files:**
- Modify: `apps/admin/src/types.ts`
- Modify: `apps/admin/src/api.ts`
- Modify: `apps/admin/src/App.vue`
- Modify: `apps/admin/tests/api.test.ts`
- Modify: `apps/admin/tests/App.test.ts`

**Interfaces:**
- Consumes: `PUT /api/v1/companies/{company_id}/documents/order` and ordered `DocumentItem[]` from Task 2.
- Produces: `reorderDocuments(companyId: string, documentIds: string[], fetcher?: Fetcher): Promise<DocumentItem[]>`.
- Produces: `DocumentList` event contract `reorder: [documentIds: string[]]`.

- [ ] **Step 1: Write failing API test**

Add a request assertion:

```typescript
await reorderDocuments('company-1', ['document-2', 'document-1'], fetchMock)

expect(fetchMock).toHaveBeenCalledWith(
  '/api/v1/companies/company-1/documents/order',
  expect.objectContaining({
    method: 'PUT',
    body: JSON.stringify({ document_ids: ['document-2', 'document-1'] }),
  }),
)
```

- [ ] **Step 2: Run API test and verify RED**

```bash
corepack pnpm --filter @company/admin exec vitest run tests/api.test.ts
```

Expected: TypeScript/Vitest reports that `reorderDocuments` is not exported.

- [ ] **Step 3: Add the admin API and type field**

Add `sort_order: number` to `DocumentItem` and implement `reorderDocuments` with JSON headers through the existing authenticated `request` helper.

- [ ] **Step 4: Run API test and verify GREEN**

Run the command from Step 2. Expected: the API test passes.

- [ ] **Step 5: Write failing App state tests**

Mock `reorderDocuments`. Emit `reorder` from `DocumentList` and assert:

```typescript
expect(wrapper.findAll('.document-row').map((row) => row.text())).toEqual([
  expect.stringContaining('Second'),
  expect.stringContaining('First'),
])
expect(api.reorderDocuments).toHaveBeenCalledWith('company-1', ['document-2', 'document-1'])
```

Add separate tests proving the response replaces the optimistic order, a rejected request restores the snapshot and shows the error, duplicate reorder events are ignored while saving, and a response for a company that is no longer selected cannot replace the new company's list.

- [ ] **Step 6: Run App tests and verify RED**

```bash
corepack pnpm --filter @company/admin exec vitest run tests/App.test.ts
```

Expected: the component does not handle the emitted event and the API mock is untouched.

- [ ] **Step 7: Implement optimistic state and rollback**

Import `reorderDocuments`, add `reordering = ref(false)`, and implement `reorder(documentIds)` that validates the IDs against the current array, snapshots it, maps IDs to documents for immediate display, awaits the API, applies the response only when the selected company still matches, restores the snapshot on a same-company failure, and always clears `reordering`. Pass `busy || reordering` to `DocumentList` and bind `@reorder="reorder"`.

- [ ] **Step 8: Run Admin state tests and commit Task 3**

```bash
corepack pnpm --filter @company/admin exec vitest run tests/api.test.ts tests/App.test.ts
git add apps/admin/src/types.ts apps/admin/src/api.ts apps/admin/src/App.vue apps/admin/tests/api.test.ts apps/admin/tests/App.test.ts
git commit -m "feat(admin): save document order"
```

Expected: all selected tests pass.

### Task 4: Implement Whole-Row Pointer and Keyboard Sorting

**Files:**
- Modify: `apps/admin/src/components/DocumentList.vue`
- Modify: `apps/admin/src/style.css`
- Modify: `apps/admin/tests/App.test.ts`
- Modify: `apps/admin/tests/style.test.ts`

**Interfaces:**
- Consumes: `documents`, `busy`, and `pendingIds` props.
- Produces: `reorder(documentIds: string[])` after pointer release or keyboard movement.

- [ ] **Step 1: Write failing interaction tests**

Mount the app, stub each row's `getBoundingClientRect`, dispatch `pointerdown`, `pointermove`, and `pointerup`, and assert the emitted/API ID order changes. Add tests that pointerdown on an input or button does not start sorting; `Alt+ArrowDown` moves the focused row; first-up and last-down are no-ops; and the live region reports the destination.

- [ ] **Step 2: Run interaction tests and verify RED**

```bash
corepack pnpm --filter @company/admin exec vitest run tests/App.test.ts tests/style.test.ts
```

Expected: no reorder event, draggable state class, or ordering styles exist.

- [ ] **Step 3: Implement pointer ordering**

In `DocumentList.vue`, keep a local `previewIds`, pointer ID, start Y, and dragged ID. Ignore starts whose target has `closest('input, button, a, select, textarea')`. After a 6px threshold, capture the pointer, compare `clientY` with row rectangle midpoints, and move the dragged ID in `previewIds`. On release, emit only when the sequence differs from `props.documents.map(({ id }) => id)`; on cancel, restore props order.

Render rows from `previewIds` mapped back to documents, set `data-document-id`, `tabindex="0"`, `aria-describedby`, and state classes. Handle `Alt+ArrowUp/Down` through the same pure move helper and update an `aria-live="polite"` message.

- [ ] **Step 4: Add stable visual feedback**

Add styles for `cursor: grab`, `cursor: grabbing`, reduced opacity on the dragged row, a two-pixel green insertion line, visible keyboard focus, and `user-select: none` only while dragging. Preserve existing grid widths and interactive control cursors. Respect `prefers-reduced-motion` and avoid layout-changing transforms.

- [ ] **Step 5: Run Admin tests and commit Task 4**

```bash
corepack pnpm --filter @company/admin check
git add apps/admin/src/components/DocumentList.vue apps/admin/src/style.css apps/admin/tests/App.test.ts apps/admin/tests/style.test.ts
git commit -m "feat(admin): drag document rows to reorder"
```

Expected: lint, typecheck, tests, and production build pass.

### Task 5: Preserve API Order on the Public Site and Verify the Feature

**Files:**
- Modify: `apps/web/app/types/content.ts`
- Modify: `apps/web/tests/LibraryDirectory.test.ts`
- Modify: `apps/web/tests/DocumentReader.test.ts`
- Modify: `apps/web/tests/LibraryDirectory.test.ts`
- Modify: `apps/web/tests/app.test.ts`
- Modify: `apps/admin/tests/api.test.ts`
- Modify: `apps/admin/tests/App.test.ts`

**Interfaces:**
- Consumes: `DocumentRead.sort_order` from Task 2.
- Produces: Web `DocumentItem.sort_order: number`; no Web sorting helper.

- [ ] **Step 1: Write a failing Web order contract test**

Create fixtures whose upload timestamps conflict with their array order, mount `LibraryDirectory`, and assert:

```typescript
expectTypeOf<DocumentItem>().toHaveProperty('sort_order')
expect(wrapper.findAll('[data-document-id]').map((node) => node.attributes('data-document-id')))
  .toEqual(['older-but-first', 'newer-but-second'])
```

- [ ] **Step 2: Run the Web test and verify RED for the contract update**

```bash
corepack pnpm --filter @company/web exec vitest run tests/LibraryDirectory.test.ts
corepack pnpm --filter @company/web typecheck
```

Expected: typecheck fails because `DocumentItem` has no `sort_order`; the render assertion documents server-order behavior.

- [ ] **Step 3: Update shared fixtures and types**

Add `sort_order: number` to Web and Admin `DocumentItem` fixtures, with values matching array order. Do not add `.sort()` calls in Web production code.

- [ ] **Step 4: Run focused and full verification**

```bash
corepack pnpm --filter @company/web check
corepack pnpm --filter @company/admin check
cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest
cd ../../ && node --test tests/docs.test.mjs tests/prototype.test.mjs tests/scaffold.test.mjs
git diff --check
```

Expected: every command exits zero with no failures.

- [ ] **Step 5: Run browser verification**

Start the API, Admin, and Web development servers with `make dev`. In the in-app browser, verify at desktop and mobile widths that rows reorder from non-interactive areas, inputs/buttons still work, touch simulation reorders, failed API requests visibly restore order, and the Web directory matches the saved order. Capture screenshots before stopping the servers.

- [ ] **Step 6: Commit Task 5**

```bash
git add apps/web/app/types/content.ts apps/web/tests/DocumentReader.test.ts apps/web/tests/LibraryDirectory.test.ts apps/web/tests/app.test.ts apps/admin/tests/api.test.ts apps/admin/tests/App.test.ts
git commit -m "test: verify public document order"
```

Expected: only fixture/type/order-contract changes remain for this task.
