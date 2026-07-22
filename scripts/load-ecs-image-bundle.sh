#!/usr/bin/env bash
set -Eeuo pipefail

BUNDLE="${1:?用法：load-ecs-image-bundle.sh /path/to/images.tar.gz}"
APP_DIR="${APP_DIR:-/srv/company/app}"
ENV_FILE="${ENV_FILE:-/srv/company/secrets/company.env}"
ROLLBACK_TAG="rollback-$(date +%Y%m%d-%H%M%S)"
rollback_created=0

SOURCE_IMAGES=(
  company-research-library-api:ecs-amd64
  company-research-library-web:ecs-amd64
  company-research-library-admin:ecs-amd64
  postgres:ecs-amd64
  nginxinc/nginx-unprivileged:ecs-amd64
)

TARGET_IMAGES=(
  company-research-library-api:latest
  company-research-library-web:latest
  company-research-library-admin:latest
  postgres:18.4-alpine
  nginxinc/nginx-unprivileged:1.30.4-alpine
)

test -f "$BUNDLE"
test -f "$ENV_FILE"
test -f "$APP_DIR/compose.yaml"
gzip -t "$BUNDLE"

for image in "${TARGET_IMAGES[@]:0:3}"; do
  if docker image inspect "$image" > /dev/null 2>&1; then
    docker tag "$image" "${image%:*}:$ROLLBACK_TAG"
    rollback_created=1
  fi
done

gzip -dc "$BUNDLE" | docker load

for index in "${!SOURCE_IMAGES[@]}"; do
  source_image="${SOURCE_IMAGES[$index]}"
  target_image="${TARGET_IMAGES[$index]}"
  platform="$(docker image inspect "$source_image" --format '{{.Architecture}}/{{.Os}}')"
  if [[ "$platform" != "amd64/linux" ]]; then
    echo "$source_image 架构错误：$platform" >&2
    exit 1
  fi
  docker tag "$source_image" "$target_image"
done

docker compose \
  --env-file "$ENV_FILE" \
  --project-directory "$APP_DIR" \
  -f "$APP_DIR/compose.yaml" \
  up -d --no-build --pull never

docker compose \
  --env-file "$ENV_FILE" \
  --project-directory "$APP_DIR" \
  -f "$APP_DIR/compose.yaml" \
  ps

ready=0
for _ in {1..60}; do
  if curl --fail --silent --connect-timeout 2 --max-time 5 \
    http://127.0.0.1:8080/healthz > /dev/null \
    && curl --fail --silent --connect-timeout 2 --max-time 5 \
      http://127.0.0.1:8080/api/health/ready > /dev/null; then
    ready=1
    break
  fi
  sleep 2
done

if [[ "$ready" -ne 1 ]]; then
  echo "部署后健康检查未在 120 秒内通过" >&2
  exit 1
fi

echo
if [[ "$rollback_created" -eq 1 ]]; then
  echo "部署完成；应用回滚标签：$ROLLBACK_TAG"
else
  echo "首次部署完成；没有可保留的上一版应用镜像"
fi
