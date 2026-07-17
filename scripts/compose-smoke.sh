#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ENV_FILE=${COMPOSE_ENV_FILE:-.env.example}
BASE_URL=${BASE_URL:-http://127.0.0.1:8080}
SMOKE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/company-smoke.XXXXXX")
BODY_FILE="$SMOKE_DIR/body"
HEADERS_FILE="$SMOKE_DIR/headers"
ADMIN_INDEX_FILE="$SMOKE_DIR/admin-index"
postgres_stopped=0

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
  if (( postgres_stopped )); then
    docker compose --env-file "$ENV_FILE" start postgres >/dev/null 2>&1 || true
  fi
  rm -rf "$SMOKE_DIR"
  return "$status"
}
trap restore_postgres EXIT

request_http() {
  local url=$1 request_timeout=$2
  local connect_timeout=$request_timeout
  (( connect_timeout > 3 )) && connect_timeout=3
  HTTP_CODE=$(
    curl --silent --show-error --output "$BODY_FILE" --dump-header "$HEADERS_FILE" --write-out '%{http_code}' --connect-timeout "$connect_timeout" --max-time "$request_timeout" "$url" || true
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
  printf 'timed out waiting for %s to return %s (last response: %s)\n' "$url" "$expected" "$(cat "$BODY_FILE" 2>/dev/null || true)" >&2
  return 1
}

assert_body() {
  local expected=$1
  [[ "$(cat "$BODY_FILE")" == "$expected" ]] || fail "unexpected body: $(cat "$BODY_FILE")"
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
  [[ -n "$configured_identity" && "$configured_identity" != "0" && "$configured_identity" != "root" ]] || fail "$service has no verifiable non-root user"
  printf '%s configured runtime user: %s (id command unavailable)\n' "$service" "$configured_user"
}

running_services=$(compose ps --status running --services)
for service in edge web admin api postgres; do
  grep -Fx "$service" <<< "$running_services" >/dev/null || fail "$service is not running"
  [[ "$(compose ps "$service" --format '{{.Health}}')" == "healthy" ]] || fail "$service is not healthy"
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
  [[ -z "$(compose port "$1" "$2" 2>/dev/null || true)" ]] || fail "$1:$2 unexpectedly has a host mapping"
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

printf 'compose smoke passed\n'
