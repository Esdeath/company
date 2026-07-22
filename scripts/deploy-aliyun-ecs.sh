#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_TARGET="${DEPLOY_TARGET:-root@www.ayaseeri.com}"
PUBLIC_URL="${PUBLIC_URL:-https://www.ayaseeri.com}"
REMOTE_ROOT="${REMOTE_ROOT:-/srv/company}"
RUN_CHECKS=1
ROTATE_ADMIN_PASSWORD=0
ASSUME_YES="${DEPLOY_YES:-0}"
DRY_RUN=0

usage() {
  cat <<'EOF'
用法：scripts/deploy-aliyun-ecs.sh [选项]

从 Mac 一键更新已经完成首次初始化的阿里云 ECS。

选项：
  --host USER@HOST          SSH 目标，默认 root@www.ayaseeri.com
  --public-url URL          公网验收地址，默认 https://www.ayaseeri.com
  --rotate-admin-password   本次发布同时更换管理员密码
  --skip-checks             跳过本地 make check
  --yes                     不询问发布确认
  --dry-run                 只显示步骤，不执行
  -h, --help                显示帮助

也可使用环境变量 DEPLOY_TARGET、PUBLIC_URL、REMOTE_ROOT 和 DEPLOY_YES。
EOF
}

while (($#)); do
  case "$1" in
    --host)
      DEPLOY_TARGET="${2:?--host 缺少 USER@HOST}"
      shift 2
      ;;
    --public-url)
      PUBLIC_URL="${2:?--public-url 缺少 URL}"
      shift 2
      ;;
    --rotate-admin-password)
      ROTATE_ADMIN_PASSWORD=1
      shift
      ;;
    --skip-checks)
      RUN_CHECKS=0
      shift
      ;;
    --yes)
      ASSUME_YES=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知选项：$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! "$PUBLIC_URL" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?/?$ ]]; then
  echo "PUBLIC_URL 必须是无路径的 HTTPS 地址" >&2
  exit 2
fi
if [[ ! "$DEPLOY_TARGET" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9._:-]+$ ]]; then
  echo "SSH 目标格式无效，应为 USER@HOST" >&2
  exit 2
fi
if [[ ! "$REMOTE_ROOT" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
  echo "REMOTE_ROOT 必须是普通绝对路径" >&2
  exit 2
fi

echo "部署目标：$DEPLOY_TARGET"
echo "公网地址：$PUBLIC_URL"
echo "远端目录：$REMOTE_ROOT"

if [[ "$DRY_RUN" -eq 1 ]]; then
  cat <<'EOF'

将执行：
1. 检查本地代码与工具
2. 复用一个 SSH 连接登录 ECS
3. 构建 linux/amd64 离线镜像包
4. 在 ECS 创建发布前备份
5. rsync 同步仓库并上传镜像包
6. 安全补齐管理员环境变量
7. 导入镜像、执行数据库迁移并启动服务
8. 更新宿主机 Nginx，验证首页、管理端、认证和未授权写入
EOF
  exit 0
fi

if [[ "$ASSUME_YES" -ne 1 ]]; then
  read -r -p "确认发布到上述服务器？输入 deploy 继续：" confirmation
  if [[ "$confirmation" != "deploy" ]]; then
    echo "已取消"
    exit 0
  fi
fi

for command_name in ssh scp rsync docker uv python3 git; do
  command -v "$command_name" >/dev/null || {
    echo "缺少本地命令：$command_name" >&2
    exit 1
  }
done
docker info >/dev/null
docker buildx version >/dev/null
if [[ -n "$(git -C "$ROOT" status --porcelain)" ]]; then
  echo "提示：当前工作区有未提交修改；脚本会按当前文件内容发布。"
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/company-deploy.XXXXXX")"
CONTROL_SOCKET="$WORK_DIR/ssh-control"
BUNDLE="$WORK_DIR/company-ecs-amd64-images.tar.gz"
AUTH_SNIPPET="$WORK_DIR/admin-auth.env"
SSH=(
  ssh
  -o ControlMaster=auto
  -o ControlPersist=3600
  -o "ControlPath=$CONTROL_SOCKET"
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=6
)
SCP=(
  scp
  -o ControlMaster=auto
  -o ControlPersist=3600
  -o "ControlPath=$CONTROL_SOCKET"
)
RSYNC_RSH="ssh -o ControlMaster=auto -o ControlPersist=3600 -o ControlPath=$CONTROL_SOCKET -o ServerAliveInterval=30 -o ServerAliveCountMax=6"

cleanup() {
  if [[ -S "$CONTROL_SOCKET" ]]; then
    "${SSH[@]}" -O exit "$DEPLOY_TARGET" >/dev/null 2>&1 || true
  fi
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo
echo "[1/8] 连接 ECS（使用密码登录时只需输入这一次）"
"${SSH[@]}" "$DEPLOY_TARGET" bash -s -- "$REMOTE_ROOT" <<'REMOTE_PREFLIGHT'
set -Eeuo pipefail
remote_root=$1
test "$(id -u)" -eq 0
command -v docker >/dev/null
docker compose version >/dev/null
for command_name in python3 rsync sha256sum curl systemctl; do
  command -v "$command_name" >/dev/null
done
test -x /usr/local/nginx/sbin/nginx
test -f /etc/letsencrypt/live/ayaseeri.com/fullchain.pem
test -f "$remote_root/secrets/company.env"
test -f "$remote_root/app/compose.yaml"
mkdir -p "$remote_root/app" "$remote_root/backups" "$remote_root/secrets"
REMOTE_PREFLIGHT

existing_username=$("${SSH[@]}" "$DEPLOY_TARGET" \
  "sed -n 's/^ADMIN_USERNAME=//p' '$REMOTE_ROOT/secrets/company.env' | tail -n 1")
ADMIN_USERNAME="${ADMIN_USERNAME:-${existing_username:-admin}}"
if [[ ! "$ADMIN_USERNAME" =~ ^[A-Za-z0-9_.-]{1,100}$ ]]; then
  echo "ADMIN_USERNAME 只能包含字母、数字、点、下划线和短横线" >&2
  exit 1
fi

has_admin_hash=0
if "${SSH[@]}" "$DEPLOY_TARGET" \
  "grep -q '^ADMIN_PASSWORD_HASH=' '$REMOTE_ROOT/secrets/company.env'"; then
  has_admin_hash=1
fi

password_line=
if [[ "$has_admin_hash" -ne 1 || "$ROTATE_ADMIN_PASSWORD" -eq 1 ]]; then
  echo
  if [[ "$ROTATE_ADMIN_PASSWORD" -eq 1 ]]; then
    echo "本次将更换管理员密码；旧会话会自动失效。"
  else
    echo "服务器尚未配置管理员密码，请创建生产密码。"
  fi
  password_line=$("$ROOT/scripts/hash-admin-password.sh" | tail -n 1)
  [[ "$password_line" == "ADMIN_PASSWORD_HASH='"*"'" ]] || {
    echo "未能生成管理员密码哈希" >&2
    exit 1
  }
fi

{
  printf 'ADMIN_USERNAME=%s\n' "$ADMIN_USERNAME"
  if [[ -n "$password_line" ]]; then
    printf '%s\n' "$password_line"
  fi
  printf '%s\n' \
    'SESSION_COOKIE_SECURE=true' \
    'SESSION_LIFETIME_SECONDS=43200'
} > "$AUTH_SNIPPET"
chmod 600 "$AUTH_SNIPPET"

echo
echo "[2/8] 本地质量检查"
if [[ "$RUN_CHECKS" -eq 1 ]]; then
  make -C "$ROOT" check
else
  echo "已按参数跳过 make check"
fi

echo
echo "[3/8] 构建 ECS 离线镜像包"
build_succeeded=0
for build_attempt in 1 2 3; do
  if "$ROOT/scripts/build-ecs-image-bundle.sh" "$BUNDLE"; then
    build_succeeded=1
    break
  fi
  if [[ "$build_attempt" -lt 3 ]]; then
    echo "镜像构建第 $build_attempt 次失败，重试……" >&2
  fi
done
if [[ "$build_succeeded" -ne 1 ]]; then
  echo "镜像构建连续三次失败，停止发布" >&2
  exit 1
fi

echo
echo "[4/8] 创建 ECS 发布前备份"
"${SSH[@]}" "$DEPLOY_TARGET" bash -s -- "$REMOTE_ROOT" <<'REMOTE_BACKUP'
set -Eeuo pipefail
remote_root=$1
env_file="$remote_root/secrets/company.env"
app_dir="$remote_root/app"

if docker compose --env-file "$env_file" --project-directory "$app_dir" \
  -f "$app_dir/compose.yaml" ps -q postgres 2>/dev/null | grep -q .; then
  if test -x /usr/local/sbin/company-backup; then
    /usr/local/sbin/company-backup
  elif test -x "$app_dir/scripts/company-backup.sh"; then
    "$app_dir/scripts/company-backup.sh"
  else
    echo "检测到运行中的数据库，但没有可用备份脚本；停止发布" >&2
    exit 1
  fi
else
  echo "未检测到运行中的旧数据库，跳过发布前备份"
fi
REMOTE_BACKUP

echo
echo "[5/8] 同步代码和镜像包"
rsync -az --delete \
  -e "$RSYNC_RSH" \
  --exclude='.git/' \
  --exclude='.worktrees/' \
  --exclude='.env' \
  --exclude='node_modules/' \
  --exclude='.venv/' \
  --exclude='.nuxt/' \
  --exclude='.output/' \
  --exclude='dist/' \
  --exclude='var/' \
  "$ROOT/" \
  "$DEPLOY_TARGET:$REMOTE_ROOT/app/"

"${SCP[@]}" \
  "$BUNDLE" \
  "$BUNDLE.sha256" \
  "$AUTH_SNIPPET" \
  "$DEPLOY_TARGET:$REMOTE_ROOT/"

echo
echo "[6/8] 更新生产环境变量"
"${SSH[@]}" "$DEPLOY_TARGET" bash -s -- \
  "$REMOTE_ROOT/secrets/company.env" \
  "$REMOTE_ROOT/$(basename "$AUTH_SNIPPET")" \
  "$REMOTE_ROOT" <<'REMOTE_ENV'
set -Eeuo pipefail
env_file=$1
snippet=$2
remote_root=$3

python3 - "$env_file" "$snippet" <<'PY'
import os
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
snippet_path = Path(sys.argv[2])
updates = {}
for line in snippet_path.read_text(encoding="utf-8").splitlines():
    if line and not line.startswith("#") and "=" in line:
        updates[line.split("=", 1)[0]] = line

result = []
seen = set()
for line in env_path.read_text(encoding="utf-8").splitlines():
    key = line.split("=", 1)[0] if "=" in line and not line.startswith("#") else None
    if key in updates:
        result.append(updates[key])
        seen.add(key)
    else:
        result.append(line)
for key, line in updates.items():
    if key not in seen:
        result.append(line)

temporary = env_path.with_suffix(".tmp")
temporary.write_text("\n".join(result) + "\n", encoding="utf-8")
os.chmod(temporary, 0o600)
temporary.replace(env_path)
PY

chown root:root "$env_file"
rm -f "$snippet"
ln -sfn "$env_file" "$remote_root/app/.env"
REMOTE_ENV

echo
echo "[7/8] 导入镜像、迁移数据库并启动"
"${SSH[@]}" "$DEPLOY_TARGET" bash -s -- "$REMOTE_ROOT" <<'REMOTE_START'
set -Eeuo pipefail
remote_root=$1
cd "$remote_root"
sha256sum -c company-ecs-amd64-images.tar.gz.sha256
"$remote_root/app/scripts/load-ecs-image-bundle.sh" \
  "$remote_root/company-ecs-amd64-images.tar.gz"

install -m 750 "$remote_root/app/scripts/company-backup.sh" /usr/local/sbin/company-backup
install -m 644 \
  "$remote_root/app/infra/aliyun-ecs/systemd/company-backup.service" \
  "$remote_root/app/infra/aliyun-ecs/systemd/company-backup.timer" \
  /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now company-backup.timer
REMOTE_START

echo
echo "[8/8] 更新 Nginx 并做公网验收"
"${SSH[@]}" "$DEPLOY_TARGET" bash -s -- "$REMOTE_ROOT" "$PUBLIC_URL" <<'REMOTE_VERIFY'
set -Eeuo pipefail
remote_root=$1
public_url=${2%/}
nginx_bin=/usr/local/nginx/sbin/nginx
nginx_conf=/usr/local/nginx/conf/nginx.conf
nginx_backup="/usr/local/nginx/conf/nginx.conf.before-company-$(date +%Y%m%d-%H%M%S)"
nginx_switched=0

reload_nginx() {
  if systemctl is-active --quiet nginx; then
    systemctl reload nginx
  else
    "$nginx_bin" -s reload
  fi
}

restore_nginx() {
  if [[ "$nginx_switched" -eq 1 && -f "$nginx_backup" ]]; then
    echo "公网验收失败，恢复上一份 Nginx 配置" >&2
    cp "$nginx_backup" "$nginx_conf"
    "$nginx_bin" -t
    reload_nginx
  fi
}
trap restore_nginx ERR

cp -a "$nginx_conf" "$nginx_backup"
cp "$remote_root/app/infra/aliyun-ecs/nginx.conf" "$nginx_conf"
nginx_switched=1
"$nginx_bin" -t
reload_nginx

curl --fail --silent --show-error --retry 10 --retry-all-errors --retry-delay 2 \
  http://127.0.0.1:8080/api/health/ready >/dev/null
curl --fail --silent --show-error --retry 10 --retry-all-errors --retry-delay 2 \
  "$public_url/" >/dev/null

admin_status=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  "$public_url/admin/")
[[ "$admin_status" == "200" ]]

curl --fail --silent --show-error "$public_url/api/v1/auth/session" | \
  python3 -c 'import json,sys; data=json.load(sys.stdin); raise SystemExit(data.get("authenticated") is not False)'

write_status=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --request POST --header 'Content-Type: application/json' \
  --data '{"name":"unauthorized-deploy-check"}' \
  "$public_url/api/v1/companies")
[[ "$write_status" == "401" ]]

nginx_switched=0
trap - ERR
echo "公网首页、管理端、会话接口和未授权写入保护均通过"
REMOTE_VERIFY

echo
echo "发布完成：$PUBLIC_URL"
echo "管理端：$PUBLIC_URL/admin/"
