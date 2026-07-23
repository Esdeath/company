# User Accounts and Article Comments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add verified site accounts and a moderated, one-level article comment system beneath every document reader, with account management, reports, in-site notifications, retryable email, and administrator workflows.

**Architecture:** FastAPI keeps ordinary-user authentication separate from the existing administrator authentication while both use the existing PostgreSQL service. Focused account, comment, notification, rate-limit, and mail modules expose protocols to routes and tests; Nuxt renders comments outside the sandboxed iframe; the existing Admin SPA gains moderation and user workspaces. An in-process dispatcher leases transactional email-outbox rows, so production remains a five-service deployment.

**Tech Stack:** Python 3.13, FastAPI 0.139.2, SQLAlchemy 2.0.51, PostgreSQL 18.4, Alembic, pwdlib/Argon2, Pydantic 2.13.4, Vue 3.5.40, Nuxt 4.4.8, Vite 8.1.5, TypeScript 5.9.3, Vitest 4.1.10, Vue Test Utils 2.4.11, lucide-vue-next, Nginx 1.30.4

## Global Constraints

- Use Node `24.18.0`, pnpm `10.34.5` through `corepack pnpm`, uv `0.11.29`, and Python `3.13` through `uv run`.
- Execute this plan in an isolated worktree created with `superpowers:using-git-worktrees`; the current checkout contains unrelated user changes that must not enter these commits.
- Treat `docs/superpowers/specs/2026-07-23-user-comments-design.md` as the product contract.
- Keep the uploaded HTML/Markdown reader in an empty `sandbox` iframe. Render comments in the parent Nuxt page after `DocumentReader`.
- Use email login, a private email address, and one case-insensitive unique public username of 3-30 NFKC-normalized Unicode letters, digits, `_`, or `-`.
- Store passwords with Argon2. Store session, CSRF-challenge, verification, reset, and unsubscribe secrets only as SHA-256 hashes.
- Use a dedicated `USER_TOKEN_SIGNING_KEY` to derive reconstructable HMAC link tokens from token-row UUIDs. The outbox stores the UUID, never the raw link token.
- Use separate cookie names, session tables, CSRF dependencies, and route prefixes for ordinary users and administrators.
- User sessions last 30 days. Verification links last 24 hours. Password-reset links last 30 minutes.
- Comments contain 1-2,000 characters of plain text. Permit top-level comments and one reply level only.
- A user's comments remain pending until an administrator approves one. Approval trusts future submissions but does not publish that user's other pending comments.
- Soft-delete comments; anonymize retained comments when an account is deleted.
- Top-level comments sort newest first in pages of 20. Replies sort oldest first. Public counts include only published rows.
- Preserve in-site notifications when SMTP fails. The email dispatcher must resume pending rows after API restart.
- `USER_REGISTRATION_ENABLED=false` keeps registration closed. `COMMENT_WRITES_ENABLED=false` keeps comment reads available while rejecting writes.
- Do not add avatars, anonymous comments, social login, likes, follows, multi-level threads, HTML/Markdown comments, image uploads, public profiles, or automated content moderation.
- Follow RED -> GREEN -> REFACTOR. Each task stages only its declared files and ends with its own commit.

---

### Task 1: Add community configuration, database models, and migration

**Files:**
- Modify: `apps/api/pyproject.toml`
- Modify: `apps/api/uv.lock`
- Modify: `apps/api/src/company_api/config.py`
- Modify: `apps/api/src/company_api/models.py`
- Create: `apps/api/migrations/versions/20260723_03_user_comments.py`
- Modify: `apps/api/tests/test_config.py`
- Modify: `apps/api/tests/test_models.py`

**Interfaces:**
- Produces SQLAlchemy models `User`, `UserSession`, `UserAuthChallenge`, `UserToken`, `Comment`, `CommentReport`, `Notification`, `EmailOutbox`, and `RateLimitBucket`.
- Produces enums `UserStatus`, `UserTokenPurpose`, `CommentStatus`, `ReportStatus`, and `NotificationType`.
- Produces settings properties `user_session_cookie_name: str` and `smtp_configured: bool`.

- [ ] **Step 1: Add failing model and settings tests**

Add assertions that the nine new table names exist, every foreign key has the specified `CASCADE` or `SET NULL`, normalized email/username and `(comment_id, reporter_id)` are unique, comment length has a check constraint, and production rejects `console`/`file` mail backends. Use concrete settings cases:

```python
def test_production_rejects_non_smtp_email_backend() -> None:
    with pytest.raises(ValidationError, match="SMTP"):
        settings(app_environment="production", email_backend="console")


def test_user_cookie_is_separate_from_admin_cookie() -> None:
    configured = settings(session_cookie_secure=True)
    assert configured.user_session_cookie_name == "__Host-company-user-session"
    assert configured.user_session_cookie_name != configured.session_cookie_name
```

Update the model-table assertion to include all existing and new tables. Assert `comments.parent_id` references `comments.id`, `comments.document_id` cascades, and `comments.author_id` uses `SET NULL`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd apps/api && uv run pytest tests/test_config.py tests/test_models.py -q
```

Expected: FAIL because the community settings, enums, and models do not exist.

- [ ] **Step 3: Add the email validation dependency and locked resolution**

Run:

```bash
cd apps/api && uv add 'email-validator>=2.2,<3'
```

Commit both `pyproject.toml` and `uv.lock`; do not bypass the lock with a non-frozen setup command.

- [ ] **Step 4: Implement settings and models**

Add these setting names with validation bounds and secret types:

```python
app_environment: Literal["development", "test", "production"] = "development"
user_registration_enabled: bool = False
comment_writes_enabled: bool = True
user_session_lifetime_seconds: int = Field(default=2_592_000, ge=3_600, le=2_592_000)
user_token_signing_key: SecretStr = SecretStr("local-development-only-signing-key")
email_backend: Literal["console", "file", "smtp"] = "console"
email_capture_path: Path | None = None
smtp_host: str = ""
smtp_port: int = Field(default=587, ge=1, le=65_535)
smtp_username: str = ""
smtp_password: SecretStr = SecretStr("")
smtp_starttls: bool = True
smtp_sender: str = ""
public_base_url: str = "http://127.0.0.1:3000"
email_dispatch_interval_seconds: float = Field(default=2.0, ge=0.1, le=60)
email_max_attempts: int = Field(default=8, ge=1, le=20)
```

Use UUID primary keys, timezone-aware timestamps, named constraints, and indexed foreign keys. `EmailOutbox` must contain `token_id`, `template`, `recipient`, JSON `payload`, `attempts`, `available_at`, `lease_id`, `lease_expires_at`, `sent_at`, and `last_error`. `RateLimitBucket` uses `(action, subject_hash, window_started_at)` as its composite primary key.

Add a model-level settings validator: production rejects the local signing key and every non-SMTP backend; production registration requires a complete SMTP host, sender, and public HTTPS base URL. Test registration may use the file backend and development may use the console backend.

- [ ] **Step 5: Write the additive Alembic migration**

Create all new PostgreSQL enums, tables, constraints, and indexes in dependency order. The downgrade drops only these new objects in reverse order. Do not alter existing company, document, admin-session, or login-challenge columns.

- [ ] **Step 6: Run model, config, format, and migration syntax checks**

Run:

```bash
cd apps/api && uv run pytest tests/test_config.py tests/test_models.py -q
cd apps/api && uv run ruff check src/company_api/config.py src/company_api/models.py migrations/versions/20260723_03_user_comments.py
cd apps/api && uv run ruff format --check src/company_api/config.py src/company_api/models.py migrations/versions/20260723_03_user_comments.py
```

Expected: all commands PASS.

- [ ] **Step 7: Commit the schema foundation**

```bash
git add apps/api/pyproject.toml apps/api/uv.lock apps/api/src/company_api/config.py apps/api/src/company_api/models.py apps/api/migrations/versions/20260723_03_user_comments.py apps/api/tests/test_config.py apps/api/tests/test_models.py
git commit -m "feat(api): add community data model"
```

---

### Task 2: Implement reusable account rate limiting

**Files:**
- Create: `apps/api/src/company_api/rate_limit.py`
- Create: `apps/api/tests/test_rate_limit.py`

**Interfaces:**
- Produces async `RateLimiter.consume(action: str, subject: str, *, limit: int, window: timedelta, now: datetime) -> bool`.
- `True` means the action may proceed; `False` means callers return HTTP 429.

- [ ] **Step 1: Write failing fixed-window and hashing tests**

```python
def test_limiter_blocks_the_next_action_inside_the_window() -> None:
    limiter = InMemoryRateLimiter()
    now = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)
    assert run(limiter.consume("comment", "user-1", limit=2, window=timedelta(minutes=1), now=now))
    assert run(limiter.consume("comment", "user-1", limit=2, window=timedelta(minutes=1), now=now))
    assert not run(limiter.consume("comment", "user-1", limit=2, window=timedelta(minutes=1), now=now))
    assert run(limiter.consume("comment", "user-2", limit=2, window=timedelta(minutes=1), now=now))
```

Also assert that the SQL repository receives `sha256(subject)` rather than the raw email or user identifier.

- [ ] **Step 2: Run the test and verify RED**

```bash
cd apps/api && uv run pytest tests/test_rate_limit.py -q
```

Expected: FAIL because `company_api.rate_limit` does not exist.

- [ ] **Step 3: Implement the protocol and PostgreSQL atomic upsert**

Use a PostgreSQL `INSERT ... ON CONFLICT ... DO UPDATE` that increments only the current fixed window and returns the new count. Delete expired buckets opportunistically. Provide `InMemoryRateLimiter` in the test module, not production code.

- [ ] **Step 4: Run focused tests and static checks**

```bash
cd apps/api && uv run pytest tests/test_rate_limit.py -q
cd apps/api && uv run ruff check src/company_api/rate_limit.py tests/test_rate_limit.py
cd apps/api && uv run mypy src/company_api/rate_limit.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/company_api/rate_limit.py apps/api/tests/test_rate_limit.py
git commit -m "feat(api): add account rate limiter"
```

---

### Task 3: Build signed email links and the retryable mail outbox

**Files:**
- Create: `apps/api/src/company_api/email_tokens.py`
- Create: `apps/api/src/company_api/mailer.py`
- Create: `apps/api/src/company_api/email_outbox.py`
- Create: `apps/api/tests/test_email_tokens.py`
- Create: `apps/api/tests/test_mailer.py`
- Create: `apps/api/tests/test_email_outbox.py`

**Interfaces:**
- Produces `EmailTokenSigner.issue(token_id: UUID, purpose: UserTokenPurpose) -> str`, `digest(raw_token: str) -> str`, and `matches(token_id: UUID, purpose: UserTokenPurpose, expected_digest: str, submitted_token: str) -> bool`.
- Produces async `Mailer.send(message: EmailMessage) -> None` with `SmtpMailer`, `ConsoleMailer`, and `FileCaptureMailer` implementations.
- Produces `EmailOutboxRepository.claim_batch(now: datetime, lease_id: UUID, limit: int) -> list[EmailJob]`, `mark_sent`, and `reschedule`.
- Produces `EmailDispatcher.run(stop: asyncio.Event) -> None`.

- [ ] **Step 1: Write failing token tests**

Use a fixed signing key and UUID. Assert deterministic reconstruction, purpose separation, constant-time validation, malformed-token rejection, and no raw secret in a queued job:

```python
def test_signer_reconstructs_without_storing_the_raw_token() -> None:
    signer = EmailTokenSigner("x" * 32)
    token_id = UUID("00000000-0000-0000-0000-000000000123")
    issued = signer.issue(token_id, UserTokenPurpose.VERIFY_EMAIL)
    assert issued == signer.issue(token_id, UserTokenPurpose.VERIFY_EMAIL)
    assert signer.matches(token_id, UserTokenPurpose.VERIFY_EMAIL, signer.digest(issued), issued)
    assert not signer.matches(token_id, UserTokenPurpose.RESET_PASSWORD, signer.digest(issued), issued)
```

- [ ] **Step 2: Write failing mail and dispatcher tests**

Assert RFC-compliant sender/recipient headers, HTML escaping, file capture only in `test`, lease recovery, exponential retry, maximum-attempt stopping, and safe fixed log messages without recipient, token, payload, or SMTP password.

- [ ] **Step 3: Run tests and verify RED**

```bash
cd apps/api && uv run pytest tests/test_email_tokens.py tests/test_mailer.py tests/test_email_outbox.py -q
```

Expected: FAIL because the three modules do not exist.

- [ ] **Step 4: Implement signing and mail backends**

Build a token as `<uuid>.<base64url-hmac>`, where HMAC-SHA256 covers `purpose.value + ":" + token_id`. Use `hmac.compare_digest`. `SmtpMailer` calls standard-library `smtplib` through `asyncio.to_thread`; STARTTLS and authentication follow settings. `FileCaptureMailer` writes one JSON object per line with mode `0o600` and refuses non-test environments.

- [ ] **Step 5: Implement leasing and dispatch**

Claim rows with `FOR UPDATE SKIP LOCKED`, set a unique lease and expiry, commit, then send outside the transaction. On failure, clear the lease and set `available_at = now + min(2 ** attempts, 3600 seconds)`. Store only a fixed exception class name in `last_error`. On success, set `sent_at` and scrub `recipient`, `payload`, `token_id`, lease fields, and `last_error` so delivered mail does not retain addresses, comment excerpts, or link material.

- [ ] **Step 6: Run focused tests and static checks**

```bash
cd apps/api && uv run pytest tests/test_email_tokens.py tests/test_mailer.py tests/test_email_outbox.py -q
cd apps/api && uv run ruff check src/company_api/email_tokens.py src/company_api/mailer.py src/company_api/email_outbox.py
cd apps/api && uv run mypy src/company_api/email_tokens.py src/company_api/mailer.py src/company_api/email_outbox.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/company_api/email_tokens.py apps/api/src/company_api/mailer.py apps/api/src/company_api/email_outbox.py apps/api/tests/test_email_tokens.py apps/api/tests/test_mailer.py apps/api/tests/test_email_outbox.py
git commit -m "feat(api): add transactional email delivery"
```

---

### Task 4: Implement ordinary-user authentication and account operations

**Files:**
- Create: `apps/api/src/company_api/user_auth.py`
- Create: `apps/api/src/company_api/user_auth_repository.py`
- Create: `apps/api/tests/test_user_auth.py`
- Create: `apps/api/tests/test_user_auth_repository.py`

**Interfaces:**
- Produces immutable `UserRecord`, `UserSessionRecord`, `NewUserSession`, and `CurrentUser` dataclasses.
- Produces `UserAuthOperations` methods `issue_challenge`, `register`, `verify_email`, `login`, `authenticate`, `logout`, `request_password_reset`, `reset_password`, `update_username`, `update_password`, `update_preferences`, and `delete_account`.
- Produces exceptions `ChallengeInvalid`, `CredentialsInvalid`, `RegistrationClosed`, `UsernameUnavailable`, `TokenInvalid`, `AccountSuspended`, `UsernameChangeTooSoon`, and `RateLimitExceeded`.

- [ ] **Step 1: Write failing service tests with an in-memory repository**

Cover one-time anonymous CSRF, generic duplicate-email registration, case-insensitive email/username matching, Argon2 storage, 24-hour verification, login, 30-day server session, password-reset expiry, session revocation, 30-day username cooldown, notification preference, suspension, and deletion/anonymization.

Use the exact trust-neutral account shape:

```python
assert current == CurrentUser(
    id=USER_ID,
    email="reader@example.com",
    username="价值读者",
    email_verified_at=NOW,
    first_comment_approved_at=None,
    reply_email_enabled=True,
)
```

- [ ] **Step 2: Run service tests and verify RED**

```bash
cd apps/api && uv run pytest tests/test_user_auth.py -q
```

Expected: FAIL because `company_api.user_auth` does not exist.

- [ ] **Step 3: Implement the service and repository protocol**

Normalize usernames with NFKC plus `casefold()`. Validate email with `email-validator`. Consume the anonymous challenge before checking credentials. Use the shared `RateLimiter` for register, login, resend, reset, and account changes. Enqueue verification/reset messages in the same repository transaction that creates the token row.

- [ ] **Step 4: Write repository transaction tests**

Assert registration creates user, token hash, and outbox row before one commit; verification consumes the token and activates the user atomically; reset updates the hash and deletes sessions; deletion nulls comment authors and removes user-owned private data.

- [ ] **Step 5: Implement `SqlAlchemyUserAuthRepository`**

Use `DELETE ... RETURNING` for one-time challenges, row locks for token consumption and account deletion, and constant response paths for unknown emails. Materialize return dataclasses before committing, matching the existing repository convention.

- [ ] **Step 6: Run authentication tests and static checks**

```bash
cd apps/api && uv run pytest tests/test_user_auth.py tests/test_user_auth_repository.py -q
cd apps/api && uv run ruff check src/company_api/user_auth.py src/company_api/user_auth_repository.py
cd apps/api && uv run mypy src/company_api/user_auth.py src/company_api/user_auth_repository.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/company_api/user_auth.py apps/api/src/company_api/user_auth_repository.py apps/api/tests/test_user_auth.py apps/api/tests/test_user_auth_repository.py
git commit -m "feat(api): add site user accounts"
```

---

### Task 5: Expose user-authentication and account HTTP contracts

**Files:**
- Create: `apps/api/src/company_api/user_schemas.py`
- Create: `apps/api/src/company_api/user_auth_routes.py`
- Modify: `apps/api/src/company_api/main.py`
- Modify: `apps/api/tests/test_health.py`
- Create: `apps/api/tests/test_user_auth_routes.py`

**Interfaces:**
- Produces `/api/v1/user-auth/*`, `/api/v1/users/me`, and account mutation routes from the approved design.
- Produces FastAPI dependencies `OptionalUserSession`, `UserSessionDependency`, and `UserCsrfDependency`.
- `GET /api/v1/user-auth/session` returns `{authenticated, user, csrf_token, expires_at, registration_enabled}`.

- [ ] **Step 1: Write failing route tests**

Use a fake `UserAuthOperations`. Assert anonymous session challenge, generic registration response, verification cookie, login cookie, logout deletion, password-reset response, profile/password/preferences updates, account deletion, 401/403 separation, `Cache-Control: no-store`, and the user cookie never authenticates an administrator route.

- [ ] **Step 2: Run route tests and verify RED**

```bash
cd apps/api && uv run pytest tests/test_user_auth_routes.py -q
```

Expected: FAIL because the router and schemas do not exist.

- [ ] **Step 3: Implement schemas and routes**

Use `EmailStr` and explicit bounds. All anonymous POSTs consume `X-CSRF-Token`; authenticated PATCH/DELETE routes require the session-bound token. Map domain errors to 401, 403, 409, 422, 429, or 503 with fixed Chinese messages. Set the ordinary-user cookie with `HttpOnly`, configured `Secure`, `SameSite=Strict`, `Path=/`, and a 30-day `Max-Age`.

- [ ] **Step 4: Refactor `create_app` composition without breaking injection tests**

Add optional injected user-auth and mail-dispatcher dependencies. When the app owns the database engine, construct the SQL repositories from the shared session factory. Start one dispatcher task in lifespan and stop/await it before disposing the engine. When tests inject dependencies, do not create or dispose an external engine.

- [ ] **Step 5: Run routes, health, and existing admin-auth regression tests**

```bash
cd apps/api && uv run pytest tests/test_user_auth_routes.py tests/test_health.py tests/test_auth.py tests/test_routes.py -q
cd apps/api && uv run mypy src/company_api/main.py src/company_api/user_auth_routes.py src/company_api/user_schemas.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/company_api/user_schemas.py apps/api/src/company_api/user_auth_routes.py apps/api/src/company_api/main.py apps/api/tests/test_health.py apps/api/tests/test_user_auth_routes.py
git commit -m "feat(api): expose site account API"
```

---

### Task 6: Implement public comment listing, posting, and one-level replies

**Files:**
- Create: `apps/api/src/company_api/comment_schemas.py`
- Create: `apps/api/src/company_api/comment_service.py`
- Create: `apps/api/src/company_api/comment_repository.py`
- Create: `apps/api/src/company_api/comment_routes.py`
- Modify: `apps/api/src/company_api/main.py`
- Create: `apps/api/tests/test_comment_service.py`
- Create: `apps/api/tests/test_comment_repository.py`
- Create: `apps/api/tests/test_comment_routes.py`

**Interfaces:**
- Produces `CommentRead`, `CommentThreadRead`, and `CommentPage(items, viewer_pending, next_cursor, total_count)`.
- Produces `CommentOperations.list_comments(document_id, viewer_id, cursor)`, `create_comment(document_id, actor, body, parent_id)`, and `get_thread(comment_id, viewer_id)`.
- Produces `GET/POST /api/v1/documents/{document_id}/comments` and `GET /api/v1/comments/{comment_id}/thread`.

- [ ] **Step 1: Write failing domain tests**

Cover missing documents, 2,000-character boundary, whitespace-only rejection, untrusted pending status, trusted immediate publication, pending visibility, same-document parent validation, reply-to-reply flattening, deleted-parent rejection, newest top-level order, oldest reply order, stable `(created_at, id)` cursors, and public counts.

- [ ] **Step 2: Run service tests and verify RED**

```bash
cd apps/api && uv run pytest tests/test_comment_service.py -q
```

Expected: FAIL because comment modules do not exist.

- [ ] **Step 3: Implement schemas, service, and repository transaction boundary**

Return author summaries without email. Return `body=None` for deleted comments. Expose `can_edit`, `can_delete`, and `can_report` from viewer context. When a trusted reply publishes, insert the reply notification and optional email job in the same transaction; do not notify self-replies.

- [ ] **Step 4: Write repository and route tests**

Assert cursor predicates, optional-user pending visibility, thread lookup beyond page one, comment-write feature flag, CSRF on POST, 404 privacy for non-visible threads, and no response fields named `email`, `password_hash`, `token_hash`, `source_path`, or `rendered_path`.

- [ ] **Step 5: Implement routes and app wiring**

Public GET accepts an optional user session. POST requires `UserCsrfDependency` and returns 201. `COMMENT_WRITES_ENABLED=false` returns 503 with “评论区暂时只读”. Include the router in `create_app` and construct `CommentService` from `SqlAlchemyCommentRepository`.

- [ ] **Step 6: Run focused and regression tests**

```bash
cd apps/api && uv run pytest tests/test_comment_service.py tests/test_comment_repository.py tests/test_comment_routes.py tests/test_routes.py -q
cd apps/api && uv run ruff check src/company_api/comment_schemas.py src/company_api/comment_service.py src/company_api/comment_repository.py src/company_api/comment_routes.py
cd apps/api && uv run mypy src/company_api/comment_schemas.py src/company_api/comment_service.py src/company_api/comment_repository.py src/company_api/comment_routes.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/company_api/comment_schemas.py apps/api/src/company_api/comment_service.py apps/api/src/company_api/comment_repository.py apps/api/src/company_api/comment_routes.py apps/api/src/company_api/main.py apps/api/tests/test_comment_service.py apps/api/tests/test_comment_repository.py apps/api/tests/test_comment_routes.py
git commit -m "feat(api): add article comments"
```

---

### Task 7: Add author actions, reports, moderation, and user administration

**Files:**
- Create: `apps/api/src/company_api/moderation_schemas.py`
- Create: `apps/api/src/company_api/moderation_routes.py`
- Modify: `apps/api/src/company_api/comment_service.py`
- Modify: `apps/api/src/company_api/comment_repository.py`
- Modify: `apps/api/src/company_api/comment_routes.py`
- Modify: `apps/api/src/company_api/main.py`
- Create: `apps/api/tests/test_comment_actions.py`
- Create: `apps/api/tests/test_moderation_routes.py`

**Interfaces:**
- Adds `update_comment`, `delete_comment`, and `report_comment` to `CommentOperations`.
- Produces `ModerationOperations.list_comments`, `approve`, `reject`, `remove`, `list_reports`, `resolve_report`, `list_users`, `suspend_user`, and `restore_user`.
- Produces approved `/api/v1/admin/comments`, `/api/v1/admin/comment-reports`, and `/api/v1/admin/users` routes.

- [ ] **Step 1: Write failing author-action tests**

Assert author-only edit/delete, pending edits remain pending, published edits stay published with `edited_at`, soft deletion removes body, self-report rejection, one report per user/comment, report-does-not-hide, and write-switch enforcement.

- [ ] **Step 2: Write failing moderation tests**

Assert approve publishes one row and trusts its active author atomically, other pending rows remain pending, reply notifications appear only on publication, rejection records a required reason and notifies the author, removal resolves open reports, concurrent state changes return 409, suspension revokes sessions, restore retains the prior trust timestamp, and existing comments remain public.

- [ ] **Step 3: Run tests and verify RED**

```bash
cd apps/api && uv run pytest tests/test_comment_actions.py tests/test_moderation_routes.py -q
```

Expected: FAIL because action and moderation methods/routes are missing.

- [ ] **Step 4: Implement author actions and moderation transactions**

Lock comment and author rows during approve/reject/remove. Require rejection reasons of 1-500 characters. Resolve reports idempotently; return conflict only when a stale action would change a terminal comment state. Suspend by updating user status and deleting sessions in one transaction.

- [ ] **Step 5: Implement administrator routes**

Use only `AdminCsrfDependency` for mutations and `AdminSessionDependency` for reads. Paginate moderation lists with stable cursors. User search accepts a 1-100 character query and matches normalized username or email without returning hashes or tokens.

- [ ] **Step 6: Run focused and admin-auth regression tests**

```bash
cd apps/api && uv run pytest tests/test_comment_actions.py tests/test_moderation_routes.py tests/test_auth.py tests/test_routes.py -q
cd apps/api && uv run mypy src/company_api/comment_service.py src/company_api/comment_repository.py src/company_api/moderation_routes.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/company_api/moderation_schemas.py apps/api/src/company_api/moderation_routes.py apps/api/src/company_api/comment_service.py apps/api/src/company_api/comment_repository.py apps/api/src/company_api/comment_routes.py apps/api/src/company_api/main.py apps/api/tests/test_comment_actions.py apps/api/tests/test_moderation_routes.py
git commit -m "feat(api): add comment moderation"
```

---

### Task 8: Expose notifications, email preferences, and unsubscribe flow

**Files:**
- Create: `apps/api/src/company_api/notification_service.py`
- Create: `apps/api/src/company_api/notification_routes.py`
- Modify: `apps/api/src/company_api/user_schemas.py`
- Modify: `apps/api/src/company_api/main.py`
- Create: `apps/api/tests/test_notifications.py`
- Create: `apps/api/tests/test_notification_routes.py`

**Interfaces:**
- Produces `NotificationOperations.list`, `mark_read`, `mark_all_read`, and `unsubscribe`.
- Produces `GET /api/v1/users/me/notifications`, `PATCH /api/v1/users/me/notifications/{id}`, `POST /api/v1/users/me/notifications/read-all`, and `POST /api/v1/user-auth/unsubscribe`.
- Notification responses include `company_id`, `document_id`, `comment_id`, actor username, safe excerpt, `created_at`, and `read_at`.

- [ ] **Step 1: Write failing notification tests**

Assert unread-first/newest order, user ownership, mark-one/all idempotency, approval/rejection wording, escaped email content, default reply email, preference opt-out, one-time unsubscribe, and notification survival after email exhaustion.

- [ ] **Step 2: Run tests and verify RED**

```bash
cd apps/api && uv run pytest tests/test_notifications.py tests/test_notification_routes.py -q
```

Expected: FAIL because notification modules do not exist.

- [ ] **Step 3: Implement service and routes**

Use authenticated CSRF for read-state mutations. Unsubscribe uses an anonymous challenge plus a purpose-bound signed token; it only changes `reply_email_enabled`. Do not expose outbox state or SMTP errors to the user.

- [ ] **Step 4: Run notification, comment, and auth tests**

```bash
cd apps/api && uv run pytest tests/test_notifications.py tests/test_notification_routes.py tests/test_comment_service.py tests/test_user_auth.py -q
cd apps/api && uv run mypy src/company_api/notification_service.py src/company_api/notification_routes.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/company_api/notification_service.py apps/api/src/company_api/notification_routes.py apps/api/src/company_api/user_schemas.py apps/api/src/company_api/main.py apps/api/tests/test_notifications.py apps/api/tests/test_notification_routes.py
git commit -m "feat(api): add comment notifications"
```

---

### Task 9: Add the public community client and account session UI

**Files:**
- Modify: `apps/web/package.json`
- Modify: `pnpm-lock.yaml`
- Create: `apps/web/app/types/community.ts`
- Create: `apps/web/app/api/community.ts`
- Create: `apps/web/app/composables/useUserSession.ts`
- Create: `apps/web/app/components/AuthDialog.vue`
- Create: `apps/web/tests/community-api.test.ts`
- Create: `apps/web/tests/useUserSession.test.ts`
- Create: `apps/web/tests/AuthDialog.test.ts`

**Interfaces:**
- Produces TypeScript types mirroring user, comment, report, notification, and pagination OpenAPI shapes.
- Produces a community API client that remembers ordinary-user CSRF only in module memory and throws typed `UserAuthenticationRequiredError`, `ConflictError`, and `RateLimitedError`.
- Produces `useUserSession()` with `state`, `loading`, `restore`, `register`, `verifyEmail`, `login`, `logout`, and `requireLogin`.
- `AuthDialog` emits `authenticated` and `close`; it never stores passwords or tokens in browser storage.

- [ ] **Step 1: Add Lucide and write failing client tests**

Run:

```bash
corepack pnpm --filter @company/web add lucide-vue-next
```

Test same-origin credentials, anonymous challenge headers, session-CSRF headers, 204 handling, typed errors, and CSRF clearing on logout. Assert `localStorage` and `sessionStorage` are never called.

- [ ] **Step 2: Run client tests and verify RED**

```bash
corepack pnpm --filter @company/web exec vitest run tests/community-api.test.ts tests/useUserSession.test.ts
```

Expected: FAIL because the community client and composable do not exist.

- [ ] **Step 3: Implement types, client, and composable**

Keep one module-local CSRF string, matching the existing Admin client pattern. A 401 clears authenticated user state but preserves the current comment draft through the caller. `restore()` deduplicates concurrent session requests.

- [ ] **Step 4: Write and implement the account dialog**

Cover login, register, verification-sent state, password-reset request/confirmation, Escape, focus restoration, busy state, field errors, registration-disabled copy, and successful authentication. Use native labels and inputs; use `X` and `ArrowLeft` Lucide icon buttons with tooltips/accessible names.

- [ ] **Step 5: Run frontend tests and checks**

```bash
corepack pnpm --filter @company/web exec vitest run tests/community-api.test.ts tests/useUserSession.test.ts tests/AuthDialog.test.ts
corepack pnpm --filter @company/web exec vue-tsc --noEmit
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/package.json pnpm-lock.yaml apps/web/app/types/community.ts apps/web/app/api/community.ts apps/web/app/composables/useUserSession.ts apps/web/app/components/AuthDialog.vue apps/web/tests/community-api.test.ts apps/web/tests/useUserSession.test.ts apps/web/tests/AuthDialog.test.ts
git commit -m "feat(web): add site account session"
```

---

### Task 10: Build the article comment section

**Files:**
- Create: `apps/web/app/components/CommentItem.vue`
- Create: `apps/web/app/components/CommentSection.vue`
- Create: `apps/web/app/utils/linkifyComment.ts`
- Create: `apps/web/tests/CommentItem.test.ts`
- Create: `apps/web/tests/CommentSection.test.ts`
- Create: `apps/web/tests/linkifyComment.test.ts`

**Interfaces:**
- `CommentSection` consumes `documentId: string`, `currentUser: CurrentUser | null`, and `targetCommentId: string | null`.
- It emits `login-required`, `unread-count-changed`, and `target-resolved`.
- `CommentItem` emits `reply`, `edit`, `delete`, and `report` using comment UUIDs.
- `linkifyComment(text: string) -> CommentSegment[]` emits only text or `http`/`https` link segments.

- [ ] **Step 1: Write failing safe-link tests**

Assert line breaks, punctuation boundaries, `https`/`http`, and rejection of `javascript:`, `data:`, HTML tags, and malformed URLs. Rendering must use Vue text nodes, never `v-html`.

- [ ] **Step 2: Write failing component tests**

Cover loading/error/retry, logged-out prompt, 2,000-character counter, pending private preview, newest top-level/oldest replies, one-level reply UI, stale-request protection after document switch, cursor load-more, draft retention across 401/login, edit marker, delete confirmation, report once, and target-thread insertion.

- [ ] **Step 3: Run tests and verify RED**

```bash
corepack pnpm --filter @company/web exec vitest run tests/linkifyComment.test.ts tests/CommentItem.test.ts tests/CommentSection.test.ts
```

Expected: FAIL because components and utility do not exist.

- [ ] **Step 4: Implement `CommentItem` and safe rendering**

Use semantic `<article>`, `<time>`, nested `<ol>`, and text/icon buttons only for clear commands. Pending rows show “待审核”; deleted rows show “此评论已删除”; anonymized authors show “已注销用户”. Disable reply on deleted/non-published parents.

- [ ] **Step 5: Implement `CommentSection` state machine**

Keep request-generation counters for list and thread requests. Store drafts in component memory keyed by document ID, not browser storage. On 401 emit `login-required` and keep text. After authentication, retry only when the user presses Publish. Render `viewer_pending` separately and merge pending replies under their public parent.

- [ ] **Step 6: Run component tests, typecheck, and lint**

```bash
corepack pnpm --filter @company/web exec vitest run tests/linkifyComment.test.ts tests/CommentItem.test.ts tests/CommentSection.test.ts
corepack pnpm --filter @company/web lint
corepack pnpm --filter @company/web exec vue-tsc --noEmit
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/web/app/components/CommentItem.vue apps/web/app/components/CommentSection.vue apps/web/app/utils/linkifyComment.ts apps/web/tests/CommentItem.test.ts apps/web/tests/CommentSection.test.ts apps/web/tests/linkifyComment.test.ts
git commit -m "feat(web): add article comment section"
```

---

### Task 11: Integrate accounts, notifications, deep links, and responsive layout

**Files:**
- Create: `apps/web/app/components/SiteUserControls.vue`
- Create: `apps/web/app/components/NotificationMenu.vue`
- Create: `apps/web/app/components/AccountDialog.vue`
- Modify: `apps/web/app/app.vue`
- Modify: `apps/web/app/assets/css/main.css`
- Modify: `apps/web/tests/app.test.ts`
- Create: `apps/web/tests/SiteUserControls.test.ts`
- Create: `apps/web/tests/NotificationMenu.test.ts`
- Create: `apps/web/tests/AccountDialog.test.ts`
- Modify: `apps/web/tests/layout.test.ts`

**Interfaces:**
- Header controls use Lucide `Bell`, `UserRound`, `LogIn`, `Settings`, and `LogOut` icons with accessible names.
- Notification links use `/?company=<uuid>&document=<uuid>&comment=<uuid>`.
- `app.vue` owns selected IDs and deep-link restoration; `CommentSection` owns only comment data for the selected document.

- [ ] **Step 1: Write failing user-control, notification, and account tests**

Cover unread badge, mark-read, empty/error states, login entry, logout, username/password/preferences updates, username cooldown error, password-confirmed deletion, and focus return from dialogs/menus.

- [ ] **Step 2: Write failing app/deep-link/layout tests**

Assert startup restores user session in parallel with companies, selects deep-linked company/document instead of defaults, fetches an off-page target thread, scrolls after render, removes stale URL target state, displays a missing-target message, and keeps the article available when comments fail.

Update CSS contract tests to require an outer scrolling page, a stable iframe reader height, comments after the reader, and no horizontal overflow at 320px. Before editing, inspect the source checkout's pre-existing `apps/web/app/assets/css/main.css` diff and untracked `apps/web/tests/layout.test.ts`; port compatible intent by hand and never overwrite or stage unrelated user work.

- [ ] **Step 3: Run tests and verify RED**

```bash
corepack pnpm --filter @company/web exec vitest run tests/SiteUserControls.test.ts tests/NotificationMenu.test.ts tests/AccountDialog.test.ts tests/app.test.ts tests/layout.test.ts
```

Expected: FAIL because shell components and integration are missing.

- [ ] **Step 4: Implement controls and account settings**

Use menus for account actions, an icon button for notifications, toggles for reply email, and confirmation input for destructive account deletion. Do not add a public profile page or explanatory feature text.

- [ ] **Step 5: Integrate the page and change scrolling ownership**

Render `DocumentReader` and `CommentSection` in the reading column. Replace `height: 100svh` with a minimum-height page shell; give `.document-reader` a responsive fixed reading viewport such as `height: clamp(32rem, 72svh, 58rem)` without viewport-scaled font sizes. Keep the desktop directory sticky and bound its maximum height to the viewport. Add an unframed comment band after the reader.

- [ ] **Step 6: Run all Web checks**

```bash
corepack pnpm --filter @company/web check
```

Expected: lint, typecheck, all Vitest tests, and production build PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/web/app/components/SiteUserControls.vue apps/web/app/components/NotificationMenu.vue apps/web/app/components/AccountDialog.vue apps/web/app/app.vue apps/web/app/assets/css/main.css apps/web/tests/app.test.ts apps/web/tests/SiteUserControls.test.ts apps/web/tests/NotificationMenu.test.ts apps/web/tests/AccountDialog.test.ts apps/web/tests/layout.test.ts
git commit -m "feat(web): integrate account comments and notifications"
```

---

### Task 12: Add Admin moderation and user workspaces

**Files:**
- Modify: `apps/admin/src/types.ts`
- Modify: `apps/admin/src/api.ts`
- Create: `apps/admin/src/components/AdminSectionNav.vue`
- Create: `apps/admin/src/components/CommentModeration.vue`
- Create: `apps/admin/src/components/UserManagement.vue`
- Modify: `apps/admin/src/App.vue`
- Modify: `apps/admin/src/style.css`
- Modify: `apps/admin/tests/api.test.ts`
- Modify: `apps/admin/tests/App.test.ts`
- Create: `apps/admin/tests/CommentModeration.test.ts`
- Create: `apps/admin/tests/UserManagement.test.ts`

**Interfaces:**
- `AdminSectionNav` emits `select: ['documents' | 'comments' | 'users']`.
- `CommentModeration` owns pending/report/all pagination and emits no cross-workspace state.
- `UserManagement` owns search, suspend, and restore.
- Admin API continues to use the existing in-memory administrator CSRF token.

- [ ] **Step 1: Write failing API tests**

Assert exact moderation/user URLs, administrator CSRF on mutations, 401 conversion to `AuthenticationRequiredError`, 409 typed conflict, cursor query encoding, and no ordinary-user CSRF dependency.

- [ ] **Step 2: Write failing component and App tests**

Cover section navigation, pending counts, approve, required rejection reason, report keep/remove, 409 row refresh, user search, suspend confirmation, restore, authentication expiry, and preservation of the existing document workspace.

- [ ] **Step 3: Run tests and verify RED**

```bash
corepack pnpm --filter @company/admin exec vitest run tests/api.test.ts tests/App.test.ts tests/CommentModeration.test.ts tests/UserManagement.test.ts
```

Expected: FAIL because moderation contracts and components do not exist.

- [ ] **Step 4: Implement API/types and focused workspaces**

Keep moderation and user request/loading/error generations inside their components. `App.vue` owns only the active section and authentication boundary. Use tabs for the three top-level workspaces, tabs for moderation filters, and text commands for approve/reject/remove/suspend/restore.

- [ ] **Step 5: Add responsive styles and run Admin checks**

Use unframed row lists, no nested cards, headings sized for a work surface, and stable controls at 320px. Then run:

```bash
corepack pnpm --filter @company/admin check
```

Expected: lint, typecheck, all Vitest tests, and build PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/admin/src/types.ts apps/admin/src/api.ts apps/admin/src/components/AdminSectionNav.vue apps/admin/src/components/CommentModeration.vue apps/admin/src/components/UserManagement.vue apps/admin/src/App.vue apps/admin/src/style.css apps/admin/tests/api.test.ts apps/admin/tests/App.test.ts apps/admin/tests/CommentModeration.test.ts apps/admin/tests/UserManagement.test.ts
git commit -m "feat(admin): add comment moderation workspace"
```

---

### Task 13: Configure deployment, rate limits, documentation, and Compose smoke coverage

**Files:**
- Modify: `.env.example`
- Modify: `compose.yaml`
- Modify: `infra/aliyun-ecs/nginx.conf`
- Modify: `infra/aliyun-ecs/nginx-bootstrap.conf`
- Modify: `scripts/deploy-aliyun-ecs.sh`
- Modify: `scripts/compose-smoke.sh`
- Modify: `doc/AUTHENTICATION.md`
- Modify: `doc/BACKEND.md`
- Modify: `doc/DEPLOYMENT.md`
- Modify: `doc/PRODUCT_UI.md`
- Modify: `tests/docs.test.mjs`
- Modify: `tests/scaffold.test.mjs`

**Interfaces:**
- Compose passes every Task 1 setting without adding a production service.
- Production Nginx rate-limits registration, session challenge, login/reset, comment writes, and reports by IP; API rate limiting covers account subjects.
- Smoke uses `APP_ENVIRONMENT=test`, `EMAIL_BACKEND=file`, and a temporary capture path to complete verification without SMTP.

- [ ] **Step 1: Write failing repository-contract tests**

Assert new environment keys, two independent feature flags, a persistent signing key, no SMTP password in committed defaults, Nginx 429 zones, no sixth production service, updated authentication boundaries, and deployment instructions that keep registration closed until SMTP works.

- [ ] **Step 2: Run tests and verify RED**

```bash
node --test tests/docs.test.mjs tests/scaffold.test.mjs
```

Expected: FAIL because infrastructure and docs omit community contracts.

- [ ] **Step 3: Update environment and deployment wiring**

Add safe local defaults with registration off. Make the deployment script generate and preserve a 32-byte URL-safe `USER_TOKEN_SIGNING_KEY` on first install, never print it, and retain existing SMTP credentials during routine deploys. Bootstrap Nginx continues to reject public writes before TLS is established.

- [ ] **Step 4: Add production rate-limit locations**

Create separate zones for auth-email actions and comment writes. Apply precise locations before the catch-all `/api/` block. Return 429 without proxying excess requests. Keep admin login/session zones intact.

- [ ] **Step 5: Extend Compose smoke end to end**

After document upload, use a distinct ordinary-user cookie jar to: obtain a challenge, register, read the captured verification URL inside the API container, verify, submit a pending comment, approve it with the administrator cookie, publish a reply from a second verified user, assert the notification, mark it read, and clean up users/comments through account deletion and document deletion. The trap must remove capture files and test records on failure.

- [ ] **Step 6: Update operator and product documentation**

Document cookies, CSRF, token lifetimes, flags, SMTP fields, first-comment moderation, account deletion, comment storage, mail retry behavior, rollout order, rollback to read-only comments, and backup coverage. State that SPF/DKIM configuration belongs to the chosen SMTP provider.

- [ ] **Step 7: Run repository tests and shell syntax checks**

```bash
node --test tests/docs.test.mjs tests/prototype.test.mjs tests/scaffold.test.mjs
bash -n scripts/deploy-aliyun-ecs.sh scripts/compose-smoke.sh
docker compose config --quiet
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add .env.example compose.yaml infra/aliyun-ecs/nginx.conf infra/aliyun-ecs/nginx-bootstrap.conf scripts/deploy-aliyun-ecs.sh scripts/compose-smoke.sh doc/AUTHENTICATION.md doc/BACKEND.md doc/DEPLOYMENT.md doc/PRODUCT_UI.md tests/docs.test.mjs tests/scaffold.test.mjs
git commit -m "ops: configure user comments rollout"
```

---

### Task 14: Run full verification and review the finished feature

**Files:**
- Modify only files required to fix failures caused by Tasks 1-13.

**Interfaces:**
- Produces a clean, reviewable branch where every approved design acceptance criterion has an automated or manual verification record.

- [ ] **Step 1: Run the full non-Docker quality gate**

```bash
make check
```

Expected: root contract tests, Web check, Admin check, Ruff, format check, Mypy, and all Pytest tests PASS.

- [ ] **Step 2: Run migration and Compose smoke**

```bash
make compose-up
make compose-smoke
make compose-down
```

Expected: migration succeeds and the complete account/comment/approval/reply/notification smoke path prints `compose smoke passed`.

- [ ] **Step 3: Verify security invariants manually**

Confirm browser cookies use distinct names and correct flags; ordinary-user Cookie/CSRF cannot mutate administrator routes; administrator Cookie/CSRF cannot post comments; iframe retains `sandbox=""`; API responses and logs contain no email tokens, passwords, Cookie values, SMTP password, filesystem paths, or stack traces.

- [ ] **Step 4: Verify visual behavior with Playwright screenshots**

Capture public and Admin views at 320x800, 768x1024, 1024x768, and 1280x900. Inspect article/comment boundaries, directory stickiness, dialogs, comment composer, one-level replies, moderation rows, focus visibility, text wrapping, and horizontal overflow. Confirm a comment-list failure leaves the iframe readable.

- [ ] **Step 5: Review the diff and commit verification fixes**

```bash
git status --short
git diff --check
git diff --stat
```

If verification required source changes, stage only those exact files and commit:

```bash
git commit -m "fix: complete user comments verification"
```

If no source changes were needed, do not create an empty commit.

---

## Definition of Done

- A reader can register by email, verify, log in, reset the password, manage username/email preference, and delete the account.
- Every selected document renders comments after the unchanged sandboxed iframe.
- The first comment or reply is private pending content; approval publishes only that row and trusts future submissions.
- Authors can edit/delete; other users can report; administrators can approve, reject, remove, resolve reports, suspend, and restore.
- Replies and moderation results create in-site notifications; reply email can be disabled or unsubscribed and retries after SMTP failure.
- Deep links restore company/document context and load an off-page target thread.
- Registration and comment writes can be disabled independently without hiding published comments.
- The five-service production topology, private ports, backup flow, admin authentication, and existing document behavior remain intact.
- `make check` and `make compose-smoke` pass, and screenshots show no overlap or horizontal scrolling at the required viewports.
