#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SOURCE_ENV_FILE=${COMPOSE_ENV_FILE:-.env.example}
BASE_URL=${BASE_URL:-http://127.0.0.1:8080}
SMOKE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/company-smoke.XXXXXX")
ENV_FILE="$SMOKE_DIR/compose.env"
BODY_FILE="$SMOKE_DIR/body"
HEADERS_FILE="$SMOKE_DIR/headers"
COOKIE_FILE="$SMOKE_DIR/cookies"
USER_COOKIE_FILE="$SMOKE_DIR/user-cookies"
SECOND_USER_COOKIE_FILE="$SMOKE_DIR/second-user-cookies"
ADMIN_INDEX_FILE="$SMOKE_DIR/admin-index"
UPLOAD_ITEMS_FILE="$SMOKE_DIR/upload-items"
CLEANUP_IDS_FILE="$SMOKE_DIR/cleanup-document-ids"
postgres_stopped=0
test_environment_started=0
company_id=
company_name=
csrf_token=
user_csrf_token=
second_user_csrf_token=
comment_id=
reply_id=
EMAIL_CAPTURE_PATH="/tmp/company-compose-smoke-email-$$-$RANDOM.jsonl"
SMOKE_ADMIN_USERNAME=${SMOKE_ADMIN_USERNAME:-admin}
SMOKE_ADMIN_PASSWORD=${SMOKE_ADMIN_PASSWORD:-company_local_only}
SMOKE_USER_PASSWORD=${SMOKE_USER_PASSWORD:-compose-smoke-user-password}

cp "$SOURCE_ENV_FILE" "$ENV_FILE"
cat >> "$ENV_FILE" <<EOF
APP_ENVIRONMENT=test
USER_REGISTRATION_ENABLED=true
COMMENT_WRITES_ENABLED=true
USER_TOKEN_SIGNING_KEY=compose-smoke-only-signing-key-32-bytes
EMAIL_BACKEND=file
EMAIL_CAPTURE_PATH=$EMAIL_CAPTURE_PATH
PUBLIC_BASE_URL=$BASE_URL
EMAIL_DISPATCH_INTERVAL_SECONDS=0.1
EOF

cd "$ROOT_DIR"

compose() {
  docker compose --env-file "$ENV_FILE" "$@"
}

fail() {
  printf 'smoke failure: %s\n' "$*" >&2
  exit 1
}

restore_postgres() {
  local status=$?
  local candidate_id deadline document_id
  trap - EXIT
  set +e

  if (( postgres_stopped )); then
    docker compose --env-file "$ENV_FILE" start postgres >/dev/null 2>&1 || true
    postgres_stopped=0
  fi

  if [[ -n "$second_user_csrf_token" ]]; then
    request_user "$SECOND_USER_COOKIE_FILE" "$second_user_csrf_token" \
      "$BASE_URL/api/v1/users/me" 10 --request DELETE \
      --header 'Content-Type: application/json' \
      --data "{\"password\":\"$SMOKE_USER_PASSWORD\"}"
  fi
  if [[ -n "$user_csrf_token" ]]; then
    request_user "$USER_COOKIE_FILE" "$user_csrf_token" \
      "$BASE_URL/api/v1/users/me" 10 --request DELETE \
      --header 'Content-Type: application/json' \
      --data "{\"password\":\"$SMOKE_USER_PASSWORD\"}"
  fi

  if [[ -n "$company_name" ]]; then
    deadline=$((SECONDS + 30))
    while (( SECONDS < deadline )); do
      request_http "$BASE_URL/api/health/ready" 3
      [[ "$HTTP_CODE" == "200" ]] && break
      sleep 1
    done

    if [[ -z "$company_id" ]]; then
      request_http "$BASE_URL/api/v1/companies" 10
      if [[ "$HTTP_CODE" == "200" ]]; then
        candidate_id=$(python3 -c 'import json, sys, uuid
items = json.load(open(sys.argv[1], encoding="utf-8"))
matches = [item for item in items if isinstance(item, dict) and item.get("name") == sys.argv[2]]
if len(matches) != 1:
    raise SystemExit(1)
raw_id = matches[0].get("id")
if not isinstance(raw_id, str) or str(uuid.UUID(raw_id)) != raw_id.lower():
    raise SystemExit(1)
print(raw_id)' "$BODY_FILE" "$company_name" 2>/dev/null) || candidate_id=
        [[ -n "$candidate_id" ]] && company_id=$candidate_id
      fi
    fi

    if [[ -n "$company_id" ]]; then
      request_http "$BASE_URL/api/v1/companies/$company_id/documents" 10
      if [[ "$HTTP_CODE" == "200" ]]; then
        python3 -c 'import json, sys; print(*(item["id"] for item in json.load(open(sys.argv[1], encoding="utf-8"))), sep="\n")' "$BODY_FILE" > "$CLEANUP_IDS_FILE" 2>/dev/null || true
        while IFS= read -r document_id; do
          [[ -n "$document_id" ]] || continue
          request_admin "$BASE_URL/api/v1/documents/$document_id" 10 --request DELETE
        done < "$CLEANUP_IDS_FILE"
      fi
      request_admin "$BASE_URL/api/v1/companies/$company_id" 10 --request DELETE
    fi
  fi

  if [[ -n "${first_email:-}" || -n "${second_email:-}" ]]; then
    compose exec -T api python -c 'import os, sys
import psycopg
database_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
with psycopg.connect(database_url) as connection:
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM users WHERE normalized_email IN (%s, %s)", sys.argv[1:3])' \
      "${first_email:-unused@example.invalid}" "${second_email:-unused@example.invalid}" \
      >/dev/null 2>&1 || true
  fi

  docker compose --env-file "$ENV_FILE" exec -T api rm -f "$EMAIL_CAPTURE_PATH" >/dev/null 2>&1 || true
  if (( test_environment_started )); then
    docker compose --env-file "$SOURCE_ENV_FILE" up -d --force-recreate api edge >/dev/null 2>&1 || true
  fi

  rm -rf "$SMOKE_DIR"
  exit "$status"
}
trap restore_postgres EXIT

request_http() {
  local url=$1 request_timeout=$2
  shift 2
  local connect_timeout=$request_timeout
  (( connect_timeout > 3 )) && connect_timeout=3
  local request_cookie=${REQUEST_COOKIE_FILE:-$COOKIE_FILE}
  HTTP_CODE=$(
    curl --silent --show-error --output "$BODY_FILE" --dump-header "$HEADERS_FILE" --cookie "$request_cookie" --cookie-jar "$request_cookie" --write-out '%{http_code}' --connect-timeout "$connect_timeout" --max-time "$request_timeout" "$@" "$url" || true
  )
}

request_admin() {
  local url=$1 request_timeout=$2
  shift 2
  request_http "$url" "$request_timeout" --header "X-CSRF-Token: $csrf_token" "$@"
}

request_user() {
  local cookie_file=$1 csrf=$2 url=$3 request_timeout=$4
  shift 4
  REQUEST_COOKIE_FILE="$cookie_file" request_http "$url" "$request_timeout" \
    --header "X-CSRF-Token: $csrf" "$@"
}

obtain_user_challenge() {
  local cookie_file=$1
  REQUEST_COOKIE_FILE="$cookie_file" request_http "$BASE_URL/api/v1/user-auth/session" 30
  [[ "$HTTP_CODE" == "200" ]] || fail "ordinary-user session returned ${HTTP_CODE:-no status}"
  python3 -c 'import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
token = data.get("csrf_token")
if data.get("authenticated") is not False or not isinstance(token, str) or not token:
    raise SystemExit(1)
print(token)' "$BODY_FILE" 2>/dev/null || fail 'could not obtain ordinary-user challenge'
}

read_verification_token() {
  local email=$1 deadline=$((SECONDS + 30)) token=
  while (( SECONDS < deadline )); do
    token=$(compose exec -T api python -c 'import json, sys
from urllib.parse import parse_qs, urlsplit
path, recipient = sys.argv[1:]
try:
    records = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
except FileNotFoundError:
    raise SystemExit(1)
for record in reversed(records):
    if record.get("recipient") != recipient:
        continue
    for word in record.get("text_body", "").split():
        value = parse_qs(urlsplit(word).query).get("verify-email")
        if value:
            print(value[0])
            raise SystemExit(0)
raise SystemExit(1)' "$EMAIL_CAPTURE_PATH" "$email" 2>/dev/null) || token=
    [[ -n "$token" ]] && {
      printf '%s\n' "$token"
      return 0
    }
    sleep 1
  done
  return 1
}

register_and_verify_user() {
  local cookie_file=$1 email=$2 username=$3 challenge token detail
  challenge=$(obtain_user_challenge "$cookie_file")
  request_user "$cookie_file" "$challenge" "$BASE_URL/api/v1/user-auth/register" 30 \
    --request POST \
    --header 'Content-Type: application/json' \
    --data "{\"email\":\"$email\",\"username\":\"$username\",\"password\":\"$SMOKE_USER_PASSWORD\"}"
  if [[ "$HTTP_CODE" != "202" ]]; then
    detail=$(python3 -c 'import json, sys
try:
    value = json.load(open(sys.argv[1], encoding="utf-8")).get("detail", "unknown error")
except (OSError, ValueError, AttributeError):
    value = "unknown error"
print(value if isinstance(value, str) else "unknown error")' "$BODY_FILE" 2>/dev/null || true)
    fail "ordinary-user registration for $username returned ${HTTP_CODE:-no status} (${detail:-unknown error})"
  fi

  token=$(read_verification_token "$email") || fail 'verification email was not captured'
  challenge=$(obtain_user_challenge "$cookie_file")
  request_user "$cookie_file" "$challenge" "$BASE_URL/api/v1/user-auth/verify-email" 30 \
    --request POST \
    --header 'Content-Type: application/json' \
    --data "{\"token\":\"$token\"}"
  [[ "$HTTP_CODE" == "200" ]] || fail "email verification returned ${HTTP_CODE:-no status}"
  python3 -c 'import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
token = data.get("csrf_token")
if data.get("authenticated") is not True or not isinstance(token, str) or not token:
    raise SystemExit(1)
print(token)' "$BODY_FILE" 2>/dev/null || fail 'could not validate verified user session'
}

wait_for_http() {
  local url=$1 expected=$2 timeout=${3:-60}
  local deadline=$((SECONDS + timeout))
  local remaining
  while (( SECONDS < deadline )); do
    remaining=$((deadline - SECONDS))
    request_http "$url" "$remaining"
    [[ "$HTTP_CODE" == "$expected" ]] && return 0
    (( SECONDS < deadline )) && sleep 1
  done
  printf 'timed out waiting for %s to return %s (last status: %s)\n' "$url" "$expected" "${HTTP_CODE:-none}" >&2
  return 1
}

assert_body() {
  local expected=$1
  [[ "$(cat "$BODY_FILE")" == "$expected" ]] || fail "unexpected response body"
}

assert_non_root_uid() {
  local service=$1 uid container_id configured_user configured_identity
  if uid=$(compose exec -T "$service" id -u 2>/dev/null) && [[ "$uid" =~ ^[0-9]+$ ]]; then
    [[ "$uid" != "0" ]] || fail "$service runs as root"
    printf '%s runtime uid: %s\n' "$service" "$uid"
    return
  fi

  container_id=$(compose ps -q "$service")
  [[ -n "$container_id" ]] || fail "cannot find $service container for UID inspection"
  configured_user=$(docker inspect --format '{{.Config.User}}' "$container_id")
  configured_identity=${configured_user%%:*}
  [[ -n "$configured_identity" && ! "$configured_identity" =~ ^0+$ && "$configured_identity" != "root" ]] || fail "$service has no verifiable non-root user"
  printf '%s configured runtime user: %s (id command unavailable)\n' "$service" "$configured_user"
}

assert_no_host_mapping() {
  local service=$1 port=$2 container_id port_bindings
  container_id=$(compose ps -q "$service")
  [[ -n "$container_id" ]] || fail "cannot find $service container for port inspection"
  port_bindings=$(docker inspect --format "{{json (index .NetworkSettings.Ports \"${port}/tcp\")}}" "$container_id") || fail "cannot inspect $service:$port bindings"
  [[ "$port_bindings" == "null" ]] || fail "$service:$port unexpectedly has a host mapping"
}

wait_for_service_healthy() {
  local service=$1 timeout=${2:-60}
  local deadline=$((SECONDS + timeout))
  local running_services state health
  while (( SECONDS < deadline )); do
    running_services=$(compose ps --status running --services 2>/dev/null || true)
    state=$(compose ps --all "$service" --format '{{.State}}' 2>/dev/null || true)
    health=$(compose ps --all "$service" --format '{{.Health}}' 2>/dev/null || true)
    case "$state:$health" in
      exited:*|dead:*|removing:*|*:unhealthy)
        fail "$service reached terminal state (state=${state:-unknown}, health=${health:-none})"
        ;;
    esac
    if grep -Fx "$service" <<< "$running_services" >/dev/null && [[ "$health" == "healthy" ]]; then
      return 0
    fi
    (( SECONDS < deadline )) && sleep 1
  done
  fail "$service did not become healthy (last state=${state:-unknown}, health=${health:-none})"
}

compose up -d --force-recreate api edge >/dev/null
test_environment_started=1

for service in edge web admin api postgres; do
  wait_for_service_healthy "$service"
done

wait_for_http "$BASE_URL/healthz" 200 60 || fail 'edge health check failed'

wait_for_http "$BASE_URL/" 200 60 || fail 'web route failed'
grep -Fq '企业研究资料库' "$BODY_FILE" || fail 'web marker missing'

wait_for_http "$BASE_URL/admin" 308 30 || fail '/admin redirect failed'
[[ "$HTTP_CODE" == "308" ]] || fail "/admin returned $HTTP_CODE instead of 308"
redirect_location=$(awk 'tolower($1) == "location:" { sub(/\r$/, "", $2); print $2 }' "$HEADERS_FILE")
[[ "$redirect_location" == "/admin/" ]] || fail "/admin Location was $redirect_location"

wait_for_http "$BASE_URL/admin/" 200 60 || fail 'admin route failed'
grep -Fq '资料管理后台' "$BODY_FILE" || fail 'admin marker missing'
cp "$BODY_FILE" "$ADMIN_INDEX_FILE"

seen_admin_js=0
seen_admin_css=0
while IFS= read -r asset_path; do
  [[ -n "$asset_path" ]] || continue
  wait_for_http "$BASE_URL$asset_path" 200 30 || fail "admin asset failed: $asset_path"
  [[ -s "$BODY_FILE" ]] || fail "admin asset was empty: $asset_path"
  content_type=$(awk 'tolower($1) == "content-type:" { sub(/\r$/, "", $2); print tolower($2) }' "$HEADERS_FILE")
  case "$asset_path" in
    *.js)
      [[ "$content_type" =~ ^(application|text)/javascript ]] || fail "wrong Content-Type for $asset_path: $content_type"
      seen_admin_js=1
      ;;
    *.css)
      [[ "$content_type" == "text/css" ]] || fail "wrong Content-Type for $asset_path: $content_type"
      seen_admin_css=1
      ;;
  esac
done < <(grep -Eo '/admin/assets/[^"[:space:]]+\.(js|css)' "$ADMIN_INDEX_FILE" | sort -u)
(( seen_admin_js )) || fail 'admin index did not reference a JavaScript asset under /admin/assets/'
(( seen_admin_css )) || fail 'admin index did not reference a CSS asset under /admin/assets/'

wait_for_http "$BASE_URL/admin/review/example" 200 30 || fail 'deep admin SPA route failed'
cmp -s "$BODY_FILE" "$ADMIN_INDEX_FILE" || fail 'deep admin route did not return the SPA index'

wait_for_http "$BASE_URL/api/health/live" 200 60 || fail 'API liveness failed'
assert_body '{"status":"live"}'

wait_for_http "$BASE_URL/api/health/ready" 200 60 || fail 'API readiness failed'
assert_body '{"status":"ready"}'

request_http "$BASE_URL/api/v1/auth/session" 30
[[ "$HTTP_CODE" == "200" ]] || fail "anonymous auth session returned ${HTTP_CODE:-no status}"
login_challenge=$(python3 -c 'import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
token = data.get("csrf_token")
if data.get("authenticated") is not False or not isinstance(token, str) or not token:
    raise SystemExit(1)
print(token)' "$BODY_FILE" 2>/dev/null) || fail 'could not obtain login challenge'

request_http "$BASE_URL/api/v1/auth/login" 30 \
  --request POST \
  --header 'Content-Type: application/json' \
  --header "X-CSRF-Token: $login_challenge" \
  --data "{\"username\":\"$SMOKE_ADMIN_USERNAME\",\"password\":\"$SMOKE_ADMIN_PASSWORD\"}"
[[ "$HTTP_CODE" == "200" ]] || fail "administrator login returned ${HTTP_CODE:-no status}"
csrf_token=$(python3 -c 'import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
token = data.get("csrf_token")
if data.get("authenticated") is not True or not isinstance(token, str) or not token:
    raise SystemExit(1)
print(token)' "$BODY_FILE" 2>/dev/null) || fail 'could not validate administrator login'

for mapping in 'web 3000' 'admin 8080' 'api 8000'; do
  set -- $mapping
  assert_no_host_mapping "$1" "$2"
done

for service in web admin api edge; do
  assert_non_root_uid "$service"
done

postgres_stopped=1
docker compose --env-file "$ENV_FILE" stop postgres
wait_for_http "$BASE_URL/api/health/ready" 503 60 || fail 'API did not become not-ready after postgres stopped'
assert_body '{"status":"not_ready"}'
grep -Eiq 'postgres|sqlalchemy|traceback|password|connection' "$BODY_FILE" && fail 'readiness response leaked connection details'

docker compose --env-file "$ENV_FILE" start postgres
postgres_stopped=0
wait_for_http "$BASE_URL/api/health/ready" 200 60 || fail 'API readiness did not recover'
assert_body '{"status":"ready"}'

company_name="compose-smoke-$(date +%s)-$$-$RANDOM"
request_admin "$BASE_URL/api/v1/companies" 30 \
  --request POST \
  --header 'Content-Type: application/json' \
  --data "{\"name\":\"$company_name\"}"
[[ "$HTTP_CODE" == "201" ]] || fail "company creation returned ${HTTP_CODE:-no status}"
company_id=$(python3 -c 'import json, sys, uuid
data = json.load(open(sys.argv[1], encoding="utf-8"))
if not isinstance(data, dict) or data.get("name") != sys.argv[2]:
    raise SystemExit(1)
raw_id = data.get("id")
if not isinstance(raw_id, str) or str(uuid.UUID(raw_id)) != raw_id:
    raise SystemExit(1)
print(raw_id)' "$BODY_FILE" "$company_name" 2>/dev/null) \
  || fail 'could not validate created company'
[[ -n "$company_id" ]] || fail 'could not validate created company'

request_admin "$BASE_URL/api/v1/companies/$company_id/documents" 60 \
  --request POST \
  --form "files=@$ROOT_DIR/doc/templates/markdown/examples/ceo-interview.md;type=text/markdown" \
  --form "files=@$ROOT_DIR/doc/templates/markdown/showcase.html;type=text/html"
[[ "$HTTP_CODE" == "200" ]] || fail "document upload returned ${HTTP_CODE:-no status}"
python3 -c 'from collections import Counter
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
items = data.get("items", [])
errors = data.get("errors", [])
if len(items) != 2 or errors != []:
    raise SystemExit(1)
if Counter(item.get("format") for item in items if isinstance(item, dict)) != Counter({"markdown": 1, "html": 1}):
    raise SystemExit(1)
for item in items:
    document_id = item.get("id")
    if not isinstance(document_id, str) or item.get("content_url") != f"/api/v1/documents/{document_id}/content":
        raise SystemExit(1)
    print(item["id"], item["format"], item["content_url"], sep="\t")' "$BODY_FILE" > "$UPLOAD_ITEMS_FILE" \
  2>/dev/null || fail 'upload response did not contain exactly one Markdown, one HTML, and zero errors with canonical content URLs'

while IFS=$'\t' read -r document_id document_format content_url; do
  [[ -n "$document_id" && "$content_url" == "/api/v1/documents/$document_id/content" ]] \
    || fail 'upload response contained an invalid document reference'
  request_http "$BASE_URL$content_url" 30
  [[ "$HTTP_CODE" == "200" ]] || fail "$document_format content returned ${HTTP_CODE:-no status}"
  case "$document_format" in
    markdown)
      markdown_document_id=$document_id
      grep -Fq 'class="research-document"' "$BODY_FILE" || fail 'Markdown content marker missing'
      ;;
    html)
      grep -Fq '通用 Markdown 模板预览' "$BODY_FILE" || fail 'HTML source marker missing'
      ;;
    *)
      fail 'upload response contained an unexpected document format'
      ;;
  esac
done < "$UPLOAD_ITEMS_FILE"

[[ -n "${markdown_document_id:-}" ]] || fail 'smoke upload did not produce a Markdown document'
smoke_suffix="$(date +%s)-$$-$RANDOM"
first_email="compose-smoke-$smoke_suffix@example.com"
second_email="compose-smoke-second-$smoke_suffix@example.com"
username_suffix=${smoke_suffix//-/}
user_csrf_token=$(register_and_verify_user "$USER_COOKIE_FILE" "$first_email" "smoke_$username_suffix")

request_user "$USER_COOKIE_FILE" "$user_csrf_token" \
  "$BASE_URL/api/v1/documents/$markdown_document_id/comments" 30 \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{"body":"Compose smoke pending comment"}'
[[ "$HTTP_CODE" == "201" ]] || fail "pending comment creation returned ${HTTP_CODE:-no status}"
comment_id=$(python3 -c 'import json, sys, uuid
data = json.load(open(sys.argv[1], encoding="utf-8"))
raw_id = data.get("id")
if data.get("status") != "pending" or not isinstance(raw_id, str) or str(uuid.UUID(raw_id)) != raw_id:
    raise SystemExit(1)
print(raw_id)' "$BODY_FILE" 2>/dev/null) || fail 'first comment was not pending'

request_admin "$BASE_URL/api/v1/admin/comments/$comment_id/approve" 30 --request POST
[[ "$HTTP_CODE" == "200" ]] || fail "comment approval returned ${HTTP_CODE:-no status}"
python3 -c 'import json, sys
raise SystemExit(json.load(open(sys.argv[1], encoding="utf-8")).get("status") != "published")' \
  "$BODY_FILE" 2>/dev/null || fail 'approved comment was not published'

second_user_csrf_token=$(register_and_verify_user \
  "$SECOND_USER_COOKIE_FILE" "$second_email" "reply_$username_suffix")
request_user "$SECOND_USER_COOKIE_FILE" "$second_user_csrf_token" \
  "$BASE_URL/api/v1/documents/$markdown_document_id/comments" 30 \
  --request POST \
  --header 'Content-Type: application/json' \
  --data "{\"body\":\"Compose smoke reply\",\"parent_id\":\"$comment_id\"}"
[[ "$HTTP_CODE" == "201" ]] || fail "reply creation returned ${HTTP_CODE:-no status}"
reply_id=$(python3 -c 'import json, sys, uuid
data = json.load(open(sys.argv[1], encoding="utf-8"))
raw_id = data.get("id")
if data.get("status") != "pending" or data.get("parent_id") != sys.argv[2] or not isinstance(raw_id, str) or str(uuid.UUID(raw_id)) != raw_id:
    raise SystemExit(1)
print(raw_id)' "$BODY_FILE" "$comment_id" 2>/dev/null) || fail 'second user reply was not pending'

request_admin "$BASE_URL/api/v1/admin/comments/$reply_id/approve" 30 --request POST
[[ "$HTTP_CODE" == "200" ]] || fail "reply approval returned ${HTTP_CODE:-no status}"

request_user "$USER_COOKIE_FILE" "$user_csrf_token" \
  "$BASE_URL/api/v1/users/me/notifications" 30
[[ "$HTTP_CODE" == "200" ]] || fail "notification list returned ${HTTP_CODE:-no status}"
notification_id=$(python3 -c 'import json, sys, uuid
data = json.load(open(sys.argv[1], encoding="utf-8"))
matches = [item for item in data.get("items", []) if item.get("type") == "reply" and item.get("comment_id") == sys.argv[2]]
if len(matches) != 1 or matches[0].get("read_at") is not None:
    raise SystemExit(1)
raw_id = matches[0].get("id")
if not isinstance(raw_id, str) or str(uuid.UUID(raw_id)) != raw_id:
    raise SystemExit(1)
print(raw_id)' "$BODY_FILE" "$reply_id" 2>/dev/null) || fail 'reply notification was not present and unread'

request_user "$USER_COOKIE_FILE" "$user_csrf_token" \
  "$BASE_URL/api/v1/users/me/notifications/$notification_id" 30 --request PATCH
[[ "$HTTP_CODE" == "200" ]] || fail "notification read returned ${HTTP_CODE:-no status}"
python3 -c 'import json, sys
raise SystemExit(json.load(open(sys.argv[1], encoding="utf-8")).get("read_at") is None)' \
  "$BODY_FILE" 2>/dev/null || fail 'notification was not marked read'

request_user "$SECOND_USER_COOKIE_FILE" "$second_user_csrf_token" \
  "$BASE_URL/api/v1/users/me" 30 --request DELETE \
  --header 'Content-Type: application/json' \
  --data "{\"password\":\"$SMOKE_USER_PASSWORD\"}"
[[ "$HTTP_CODE" == "204" ]] || fail "second user cleanup returned ${HTTP_CODE:-no status}"
second_user_csrf_token=

request_user "$USER_COOKIE_FILE" "$user_csrf_token" \
  "$BASE_URL/api/v1/users/me" 30 --request DELETE \
  --header 'Content-Type: application/json' \
  --data "{\"password\":\"$SMOKE_USER_PASSWORD\"}"
[[ "$HTTP_CODE" == "204" ]] || fail "first user cleanup returned ${HTTP_CODE:-no status}"
user_csrf_token=

while IFS=$'\t' read -r document_id _; do
  [[ -n "$document_id" ]] || continue
  request_admin "$BASE_URL/api/v1/documents/$document_id" 30 --request DELETE
  [[ "$HTTP_CODE" == "204" ]] || fail "document cleanup returned ${HTTP_CODE:-no status}"
done < "$UPLOAD_ITEMS_FILE"

request_admin "$BASE_URL/api/v1/companies/$company_id" 30 --request DELETE
[[ "$HTTP_CODE" == "204" ]] || fail "company cleanup returned ${HTTP_CODE:-no status}"
company_id=
company_name=

printf 'compose smoke passed\n'
