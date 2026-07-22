#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT="${1:-/tmp/company-ecs-amd64-images.tar.gz}"
PARTIAL="$OUTPUT.partial"

IMAGES=(
  company-research-library-api:ecs-amd64
  company-research-library-web:ecs-amd64
  company-research-library-admin:ecs-amd64
  postgres:ecs-amd64
  nginxinc/nginx-unprivileged:ecs-amd64
)

cleanup() {
  rm -f "$PARTIAL"
}
trap cleanup EXIT

command -v docker > /dev/null
docker buildx version > /dev/null
mkdir -p "$(dirname "$OUTPUT")"
cd "$ROOT"

docker buildx build --platform linux/amd64 --load \
  -t company-research-library-api:ecs-amd64 \
  apps/api

docker buildx build --platform linux/amd64 --load \
  -t company-research-library-web:ecs-amd64 \
  -f apps/web/Dockerfile \
  .

docker buildx build --platform linux/amd64 --load \
  -t company-research-library-admin:ecs-amd64 \
  -f apps/admin/Dockerfile \
  .

base_context="$(mktemp -d)"
trap 'rm -rf "$base_context"; cleanup' EXIT

printf 'FROM postgres:18.4-alpine\n' > "$base_context/Dockerfile.postgres"
docker buildx build --platform linux/amd64 --load \
  -t postgres:ecs-amd64 \
  -f "$base_context/Dockerfile.postgres" \
  "$base_context"

printf 'FROM nginxinc/nginx-unprivileged:1.30.4-alpine\n' > "$base_context/Dockerfile.nginx"
docker buildx build --platform linux/amd64 --load \
  -t nginxinc/nginx-unprivileged:ecs-amd64 \
  -f "$base_context/Dockerfile.nginx" \
  "$base_context"

for image in "${IMAGES[@]}"; do
  platform="$(docker image inspect "$image" --format '{{.Architecture}}/{{.Os}}')"
  if [[ "$platform" != "amd64/linux" ]]; then
    echo "$image 架构错误：$platform" >&2
    exit 1
  fi
done

docker save "${IMAGES[@]}" | gzip -1 > "$PARTIAL"
gzip -t "$PARTIAL"
mv "$PARTIAL" "$OUTPUT"

(
  cd "$(dirname "$OUTPUT")"
  output_name="$(basename "$OUTPUT")"
  if command -v sha256sum > /dev/null; then
    sha256sum "$output_name" > "$output_name.sha256"
  else
    shasum -a 256 "$output_name" > "$output_name.sha256"
  fi
)

ls -lh "$OUTPUT" "$OUTPUT.sha256"
