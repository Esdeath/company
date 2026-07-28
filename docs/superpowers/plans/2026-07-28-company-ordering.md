# Company Ordering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let administrators move companies one position at a time and persist that order for both the management UI and public library.

**Architecture:** Add a non-negative `companies.sort_order` column, return companies in that order, and expose one authenticated endpoint that replaces the complete company order transactionally. The admin reuses the document list's arrow-button and optimistic rollback pattern; the public Web keeps rendering the API array without local sorting.

**Tech Stack:** PostgreSQL, Alembic, SQLAlchemy 2 async, FastAPI, Pydantic 2, Vue 3, Vite, Nuxt 4, TypeScript, Vitest, pytest.

## Global Constraints

- New companies append to the end of the saved order.
- The migration preserves the pre-upgrade name order: `lower(trim(name))`, then company ID.
- `PUT /api/v1/companies/order` accepts the complete unique `company_ids` set and requires administrator session plus CSRF.
- A valid button click moves exactly one position and saves immediately.
- A failed save restores the previous company array and keeps the selected company ID.
- The public Web must not independently sort companies.
- Use `corepack pnpm` for JavaScript commands and `uv run` for Python commands.

---

## File Map

- `apps/api/migrations/versions/20260728_05_company_sort_order.py`: add, backfill, constrain, index, and remove `companies.sort_order`.
- `apps/api/src/company_api/models.py`: declare the persisted company order.
- `apps/api/src/company_api/schemas.py`: expose `sort_order` and validate complete-order payload uniqueness.
- `apps/api/src/company_api/repository.py`: append new companies, list by order, and replace the complete order transactionally.
- `apps/api/src/company_api/library_service.py`: translate repository order mismatch into the public service error.
- `apps/api/src/company_api/routes.py`: register the administrator reorder endpoint.
- `apps/admin/src/types.ts`, `apps/web/app/types/content.ts`: keep the OpenAPI-derived company shape aligned.
- `apps/admin/src/api.ts`: submit complete company order with the existing CSRF request helper.
- `apps/admin/src/components/CompanyPicker.vue`: render and emit one-position order actions.
- `apps/admin/src/App.vue`: own optimistic update, persistence, rollback, and busy state.
- `apps/admin/src/style.css`: provide stable icon-button layout without changing the mobile select.
- `doc/BACKEND.md`, `doc/PRODUCT_UI.md`: record the saved company order contract and interaction.

### Task 1: Persist Company Order

**Files:**
- Create: `apps/api/migrations/versions/20260728_05_company_sort_order.py`
- Modify: `apps/api/src/company_api/models.py`
- Modify: `apps/api/src/company_api/schemas.py`
- Modify: `apps/api/tests/test_models.py`
- Modify: `apps/api/tests/test_routes.py`

**Interfaces:**
- Produces: `Company.sort_order: Mapped[int]`, `CompanyRead.sort_order: int`, and `CompanyOrder.company_ids: list[UUID]`.
- Migration revision: `20260728_05`, down revision `20260724_04`.

- [ ] **Step 1: Write failing model and schema tests**

Add a model assertion that `Company.__table__.c.sort_order` is non-nullable and a schema test at the route boundary:

```python
def test_company_order_rejects_duplicate_ids() -> None:
    duplicate = uuid.uuid4()
    with pytest.raises(ValidationError, match="公司顺序不能包含重复项"):
        CompanyOrder(company_ids=[duplicate, duplicate])
```

Update `company_read()` fixtures to include `sort_order=0`. The production change caught is a company order that can be null or accept ambiguous duplicate positions.

- [ ] **Step 2: Verify RED**

Run:

```bash
cd apps/api
uv run pytest tests/test_models.py tests/test_routes.py -q
```

Expected: FAIL because the column and `CompanyOrder` do not exist and `CompanyRead` has no `sort_order`.

- [ ] **Step 3: Add model, schema, and migration**

Declare:

```python
class CompanyOrder(BaseModel):
    company_ids: list[UUID]

    @field_validator("company_ids")
    @classmethod
    def unique_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("公司顺序不能包含重复项")
        return value
```

Add `sort_order: Mapped[int] = mapped_column(BigInteger)` to `Company` and `sort_order: int` to `CompanyRead`. In the migration, add the column nullable, backfill with `row_number() over (order by lower(trim(name)), id) - 1`, make it non-null, add `ck_companies_sort_order_nonnegative`, and create `ix_companies_sort_order` on `sort_order`. The downgrade drops the index and check constraint before dropping the column.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/migrations/versions/20260728_05_company_sort_order.py apps/api/src/company_api/models.py apps/api/src/company_api/schemas.py apps/api/tests/test_models.py apps/api/tests/test_routes.py
git commit -m "feat(api): add company sort order"
```

### Task 2: Implement Transactional Company Ordering

**Files:**
- Modify: `apps/api/src/company_api/repository.py`
- Modify: `apps/api/src/company_api/library_service.py`
- Modify: `apps/api/tests/test_repository.py`
- Modify: `apps/api/tests/test_library_service.py`

**Interfaces:**
- Consumes: `Company.sort_order` and `CompanyRead.sort_order` from Task 1.
- Produces: `InvalidCompanyOrder`, `LibraryRepository.reorder_companies(company_ids)`, `CompanyOrderMismatch`, and `LibraryOperations.reorder_companies(company_ids)`.

- [ ] **Step 1: Write failing repository and service tests**

Cover these literal outcomes:

```python
def test_company_list_preserves_repository_sort_order(tmp_path: Path) -> None:
    repository = FakeRepository(companies=[company(COMPANY_ID, "Zulu", 0), company(OTHER_COMPANY_ID, "Alpha", 1)])
    result = run(LibraryService(repository, ContentStore(tmp_path)).list_companies())
    assert [item.id for item in result] == [COMPANY_ID, OTHER_COMPANY_ID]

def test_reorder_companies_replaces_complete_order(tmp_path: Path) -> None:
    repository = FakeRepository(companies=[company(COMPANY_ID, "One", 0), company(OTHER_COMPANY_ID, "Two", 1)])
    result = run(LibraryService(repository, ContentStore(tmp_path)).reorder_companies([OTHER_COMPANY_ID, COMPANY_ID]))
    assert [(item.id, item.sort_order) for item in result] == [(OTHER_COMPANY_ID, 0), (COMPANY_ID, 1)]
```

Add mismatch coverage for a missing/unknown ID set. In repository tests assert that create obtains the company-order table lock, reads `max(Company.sort_order)`, and assigns `max + 1`; list orders by `Company.sort_order` then ID; reorder obtains the same lock before validating the complete set. The production changes caught are alphabetical re-sorting, duplicate positions from concurrent writes, non-appending creates, and partial-order acceptance.

- [ ] **Step 2: Verify RED**

```bash
cd apps/api
uv run pytest tests/test_repository.py tests/test_library_service.py -q
```

Expected: FAIL because company records have no order and company reorder methods do not exist.

- [ ] **Step 3: Implement repository behavior**

Extend `CompanyRecord` and `_company_record()` with `sort_order`. In both `create_company()` and `reorder_companies()`, serialize company-order writes before reading the collection:

```python
await session.execute(text("LOCK TABLE companies IN SHARE ROW EXCLUSIVE MODE"))
```

This also serializes creation in an empty table, where row locking cannot. Then calculate the current maximum in `create_company()` and construct:

```python
company = Company(
    name=data.name,
    ticker=data.ticker,
    market=data.market,
    sort_order=(current_max if current_max is not None else -1) + 1,
)
```

Change list ordering to `Company.sort_order.asc(), Company.id.asc()`. Add:

```python
async def reorder_companies(self, company_ids: list[UUID]) -> list[CompanyRecord]:
    async with self._session_factory() as session:
        await session.execute(text("LOCK TABLE companies IN SHARE ROW EXCLUSIVE MODE"))
        companies = (await session.scalars(select(Company))).all()
        by_id = {company.id: company for company in companies}
        if len(company_ids) != len(set(company_ids)) or set(company_ids) != set(by_id):
            raise InvalidCompanyOrder
        ordered = []
        for sort_order, company_id in enumerate(company_ids):
            company = by_id[company_id]
            company.sort_order = sort_order
            ordered.append(company)
        await session.flush()
        records = [_company_record(company) for company in ordered]
        await session.commit()
        return records
```

- [ ] **Step 4: Implement service behavior**

Remove the alphabetical `records.sort(...)` from `list_companies()`. Translate `InvalidCompanyOrder` to `CompanyOrderMismatch` in `reorder_companies()` and map repository records with `_company_read()` including `sort_order`.

- [ ] **Step 5: Verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/company_api/repository.py apps/api/src/company_api/library_service.py apps/api/tests/test_repository.py apps/api/tests/test_library_service.py
git commit -m "feat(api): persist complete company order"
```

### Task 3: Expose the Reorder API and Clients

**Files:**
- Modify: `apps/api/src/company_api/routes.py`
- Modify: `apps/api/tests/test_routes.py`
- Modify: `apps/api/tests/test_auth.py`
- Modify: `apps/admin/src/api.ts`
- Modify: `apps/admin/src/types.ts`
- Modify: `apps/admin/tests/api.test.ts`
- Modify: `apps/web/app/types/content.ts`

**Interfaces:**
- Consumes: `CompanyOrder`, `CompanyOrderMismatch`, `LibraryOperations.reorder_companies()`.
- Produces: `PUT /api/v1/companies/order` and `reorderCompanies(companyIds: string[]): Promise<Company[]>`.

- [ ] **Step 1: Write failing route and client tests**

Add a fake-service order capture and assert:

```python
response = client.put(
    "/api/v1/companies/order",
    json={"company_ids": [str(OTHER_COMPANY_ID), str(COMPANY_ID)]},
    headers=admin_csrf_headers(),
)
assert response.status_code == 200
assert [item["id"] for item in response.json()] == [str(OTHER_COMPANY_ID), str(COMPANY_ID)]
```

Cover mismatch as `422` with “公司顺序与当前目录不一致”, plus missing admin session and CSRF rejection using the existing mutation parameterization. In the admin client test assert the exact PUT URL and `{ company_ids: [...] }` JSON body. The production change caught is an unprotected, misrouted, or differently-shaped mutation.

- [ ] **Step 2: Verify RED**

```bash
cd apps/api && uv run pytest tests/test_routes.py tests/test_auth.py -q
cd ../.. && corepack pnpm --filter @company/admin exec vitest run tests/api.test.ts
```

Expected: FAIL with route `404` and missing `reorderCompanies` export.

- [ ] **Step 3: Implement route, client, and shared types**

Register before `/{company_id}` routes:

```python
@router.put("/companies/order", response_model=list[CompanyRead])
async def reorder_companies(
    data: CompanyOrder,
    service: LibraryServiceDependency,
    _admin: AdminCsrfDependency,
) -> list[CompanyRead]:
    try:
        return await service.reorder_companies(data.company_ids)
    except CompanyOrderMismatch as error:
        raise HTTPException(status_code=422, detail="公司顺序与当前目录不一致") from error
```

Add `sort_order: number` to both frontend `Company` types and implement the admin client using the existing `request()` helper and CSRF state.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 commands. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/company_api/routes.py apps/api/tests/test_routes.py apps/api/tests/test_auth.py apps/admin/src/api.ts apps/admin/src/types.ts apps/admin/tests/api.test.ts apps/web/app/types/content.ts
git commit -m "feat(api): expose company ordering endpoint"
```

### Task 4: Add Company Order Controls

**Files:**
- Modify: `apps/admin/src/components/CompanyPicker.vue`
- Create: `apps/admin/tests/CompanyPicker.test.ts`
- Modify: `apps/admin/src/style.css`
- Modify: `apps/admin/tests/style.test.ts`

**Interfaces:**
- Consumes: ordered `companies: Company[]` and `busy?: boolean`.
- Produces: `reorder: [companyIds: string[]]` from `CompanyPicker`.

- [ ] **Step 1: Write failing component and layout tests**

Mount three companies and assert first-up and last-down are disabled, busy disables all six controls, and:

```typescript
await wrapper.get('button[aria-label="下移 第一公司"]').trigger('click')
expect(wrapper.emitted('reorder')).toEqual([[['company-2', 'company-1', 'company-3']]])
expect(wrapper.get('[role="status"]').text()).toContain('已移到第 2 项')
```

Assert the style sheet gives `.company-order-actions` a stable inline-flex track and `.company-order-button` a fixed inline/block size. The production change caught is a wrong one-step permutation or controls that shift/overlap the company label.

- [ ] **Step 2: Verify RED**

```bash
corepack pnpm --filter @company/admin exec vitest run tests/CompanyPicker.test.ts tests/style.test.ts
```

Expected: FAIL because no order controls or event exist.

- [ ] **Step 3: Implement one-position controls**

Add a `move(companyId, delta)` helper equivalent to the tested document implementation: reject busy/out-of-range moves, swap exactly two IDs, update a component status message, and emit the complete ID array. Render two icon buttons per desktop company row using `↑` and `↓`, `title`, and company-specific `aria-label`; keep the mobile `<select>` unchanged.

- [ ] **Step 4: Implement stable styles**

Use the existing restrained document-order control dimensions and colors. Make each `.folio-tab` contain a label wrapper plus `.company-order-actions`; hide ordering controls in the existing mobile breakpoint together with `.folio-tabs`.

- [ ] **Step 5: Verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/admin/src/components/CompanyPicker.vue apps/admin/tests/CompanyPicker.test.ts apps/admin/src/style.css apps/admin/tests/style.test.ts
git commit -m "feat(admin): add company order controls"
```

### Task 5: Save and Roll Back Company Order

**Files:**
- Modify: `apps/admin/src/App.vue`
- Modify: `apps/admin/tests/App.test.ts`

**Interfaces:**
- Consumes: `CompanyPicker`'s complete `companyIds` event and `reorderCompanies()` from Task 3.
- Produces: optimistic company ordering, success feedback, rollback feedback, and ordering busy state.

- [ ] **Step 1: Write failing App tests**

Test a deferred reorder request. Immediately after moving the first company down, assert the visible tab order changed, selected company and document title stayed the same, all company order buttons plus the mobile select and new-company toggle are disabled, and only one API call was issued. Resolve with server data and assert “公司顺序已保存”. Reject in a separate test and assert the old order returns with “顺序保存失败，已恢复原顺序”.

Change the successful-create expectation from prepend to append:

```typescript
expect(wrapper.findAll('.folio-tab').map((node) => node.text())).toEqual([
  expect.stringContaining('山河研究'),
  expect.stringContaining('远望科技'),
  expect.stringContaining('新岸资本'),
])
```

The production changes caught are stale rollback, selection loss, duplicate saves, and new companies appearing at the top.

- [ ] **Step 2: Verify RED**

```bash
corepack pnpm --filter @company/admin exec vitest run tests/App.test.ts
```

Expected: FAIL because App does not handle company reorder and still prepends a newly created company.

- [ ] **Step 3: Implement optimistic persistence**

Add `companyReordering`, feedback sequence, and `reorderCompaniesInApp(companyIds)`. Validate length, uniqueness, and local membership; capture `previous`; assign the reordered array; set busy; call `reorderCompanies`; use the server response on success; restore `previous` on failure. Do not call `refreshDocuments()` or change `selectedCompanyId`.

Pass `companyReordering` through `CompanyPicker.busy`, bind `@reorder`, and make create success append locally:

```typescript
companies.value = [...companies.value.filter((item) => item.id !== company.id), company]
```

Give `CompanyPicker` the feedback object so its polite status watcher can announce save or rollback without colliding with its local movement announcement.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/admin/src/App.vue apps/admin/tests/App.test.ts
git commit -m "feat(admin): save company order with rollback"
```

### Task 6: Lock the Public Order Contract and Update Docs

**Files:**
- Modify: `apps/web/tests/LibraryDirectory.test.ts`
- Modify: `apps/web/tests/app.test.ts`
- Modify: `doc/BACKEND.md`
- Modify: `doc/PRODUCT_UI.md`

**Interfaces:**
- Consumes: ordered `Company[]` from `GET /api/v1/companies`.
- Produces: explicit regression coverage that Web renders API order unchanged.

- [ ] **Step 1: Write the public-order regression test**

Use a deliberately non-alphabetical fixture with `sort_order: 0` on “远望科技” and `sort_order: 1` on “山河研究”. Assert `LibraryDirectory` renders both desktop company buttons in that literal order and, after opening the mobile drawer, renders the same order there. In the App test assert first-load selection requests documents for the first API item. The production change caught is any future client-side alphabetical sort.

- [ ] **Step 2: Verify the regression test**

```bash
corepack pnpm --filter @company/web exec vitest run tests/LibraryDirectory.test.ts tests/app.test.ts
```

Expected: PASS because Web already preserves array order; this is a characterization test, so no Web production change is required.

- [ ] **Step 3: Update current documentation**

In `doc/BACKEND.md`, document `companies.sort_order`, append-at-end creation, and complete-order replacement. In `doc/PRODUCT_UI.md`, state that company arrows move one position, save immediately, roll back on failure, and drive desktop plus mobile public order.

- [ ] **Step 4: Run focused project checks**

```bash
corepack pnpm --filter @company/web check
corepack pnpm --filter @company/admin check
cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest
```

Expected: all commands exit `0`.

- [ ] **Step 5: Run repository contract checks**

```bash
cd /Users/ruimin/Desktop/code/company
node --test tests/docs.test.mjs tests/prototype.test.mjs tests/scaffold.test.mjs
git diff --check
```

Expected: all Node tests pass and `git diff --check` prints nothing.

- [ ] **Step 6: Commit**

```bash
git add apps/web/tests/LibraryDirectory.test.ts apps/web/tests/app.test.ts doc/BACKEND.md doc/PRODUCT_UI.md
git commit -m "test(web): preserve saved company order"
```

### Task 7: Manual Responsive Verification

**Files:**
- No source changes expected; fix only issues discovered by verification and rerun the owning task's tests.

**Interfaces:**
- Consumes: completed Admin and Web builds.
- Produces: visual evidence that controls do not overlap and both public layouts share the saved order.

- [ ] **Step 1: Start development services**

Start the repository's development infrastructure and `make dev` with a development database upgraded through `20260728_05`. Use alternate ports only if the documented ports are occupied.

- [ ] **Step 2: Verify the management UI**

At desktop width, create a company and confirm it appears last. Move it up once, refresh, and confirm persistence. Check first/last disabled states, keyboard activation, focus visibility, and that a selected company's documents remain loaded while the company moves.

- [ ] **Step 3: Verify public desktop and mobile order**

Refresh Web at desktop and 390px widths. Confirm the company order matches Admin, the first returned company is initially selected, and the mobile drawer uses the same order without horizontal overflow or overlapping text.

- [ ] **Step 4: Record final state**

Run `git status --short` and retain unrelated user changes. If verification required fixes, run the owning focused test plus all Task 6 checks before committing those fixes.
