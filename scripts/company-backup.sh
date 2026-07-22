#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

APP_DIR="${APP_DIR:-/srv/company/app}"
ENV_FILE="${ENV_FILE:-/srv/company/secrets/company.env}"
BACKUP_ROOT="${BACKUP_ROOT:-/srv/company/backups}"
CONTENT_VOLUME="${CONTENT_VOLUME:-company-research-library_content_data}"
ARCHIVE_IMAGE="${ARCHIVE_IMAGE:-nginxinc/nginx-unprivileged:1.30.4-alpine}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="$BACKUP_ROOT/$STAMP"

COMPOSE=(
  docker compose
  --env-file "$ENV_FILE"
  --project-directory "$APP_DIR"
  -f "$APP_DIR/compose.yaml"
)

exec 9>/run/lock/company-backup.lock
flock -n 9 || {
  echo "已有备份任务正在运行" >&2
  exit 1
}

mkdir -p "$TARGET"

api_paused=0

cleanup() {
  if [[ "$api_paused" -eq 1 ]]; then
    "${COMPOSE[@]}" unpause api || true
  fi
}
trap cleanup EXIT INT TERM

echo "暂停 API 写入"
"${COMPOSE[@]}" pause api
api_paused=1

echo "备份 PostgreSQL"
"${COMPOSE[@]}" exec -T postgres sh -lc \
  'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$TARGET/postgres.dump"

echo "备份内容卷"
docker run --rm --pull never \
  --user 0:0 \
  -v "$CONTENT_VOLUME:/data:ro" \
  "$ARCHIVE_IMAGE" \
  tar -czf - -C /data . \
  > "$TARGET/content.tar.gz"

"${COMPOSE[@]}" unpause api
api_paused=0

echo "验证备份"
"${COMPOSE[@]}" exec -T postgres pg_restore --list \
  < "$TARGET/postgres.dump" \
  > /dev/null
tar -tzf "$TARGET/content.tar.gz" > /dev/null

date --iso-8601=seconds > "$TARGET/created-at.txt"
"${COMPOSE[@]}" ps > "$TARGET/compose-status.txt"

(
  cd "$TARGET"
  sha256sum postgres.dump content.tar.gz > SHA256SUMS
)

ln -sfn "$STAMP" "$BACKUP_ROOT/latest"

find "$BACKUP_ROOT" \
  -mindepth 1 \
  -maxdepth 1 \
  -type d \
  -name '20??????-??????' \
  -mtime "+$RETENTION_DAYS" \
  -exec rm -rf -- {} +

echo "备份完成：$TARGET"
