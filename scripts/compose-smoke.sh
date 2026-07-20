#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ENV_FILE=${COMPOSE_ENV_FILE:-.env.example}
BASE_URL=${BASE_URL:-http://127.0.0.1:8080}
SMOKE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/company-smoke.XXXXXX")
BODY_FILE="$SMOKE_DIR/body"
HEADERS_FILE="$SMOKE_DIR/headers"
ADMIN_INDEX_FILE="$SMOKE_DIR/admin-index"
UPLOAD_ITEMS_FILE="$SMOKE_DIR/upload-items"
CLEANUP_IDS_FILE="$SMOKE_DIR/cleanup-document-ids"
postgres_stopped=0
company_id=
company_name=

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
          request_http "$BASE_URL/api/v1/documents/$document_id" 10 --request DELETE
        done < "$CLEANUP_IDS_FILE"
      fi
      request_http "$BASE_URL/api/v1/companies/$company_id" 10 --request DELETE
    fi
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
  HTTP_CODE=$(
    curl --silent --show-error --output "$BODY_FILE" --dump-header "$HEADERS_FILE" --write-out '%{http_code}' --connect-timeout "$connect_timeout" --max-time "$request_timeout" "$@" "$url" || true
  )
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
request_http "$BASE_URL/api/v1/companies" 30 \
  --request POST \
  --header 'Content-Type: application/json' \
  --data "{\"name\":\"$company_name\"}"
[[ "$HTTP_CODE" == "201" ]] || fail "company creation returned ${HTTP_CODE:-no status}"
company_id=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["id"])' "$BODY_FILE" 2>/dev/null) \
  || fail 'could not parse created company'
[[ -n "$company_id" ]] || fail 'company creation returned no id'

request_http "$BASE_URL/api/v1/companies/$company_id/documents" 60 \
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

while IFS=$'\t' read -r document_id _; do
  [[ -n "$document_id" ]] || continue
  request_http "$BASE_URL/api/v1/documents/$document_id" 30 --request DELETE
  [[ "$HTTP_CODE" == "204" ]] || fail "document cleanup returned ${HTTP_CODE:-no status}"
done < "$UPLOAD_ITEMS_FILE"

request_http "$BASE_URL/api/v1/companies/$company_id" 30 --request DELETE
[[ "$HTTP_CODE" == "204" ]] || fail "company cleanup returned ${HTTP_CODE:-no status}"
company_id=
company_name=

printf 'compose smoke passed\n'
