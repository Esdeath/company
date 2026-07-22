#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root/apps/api"

uv run python <<'PY'
from getpass import getpass

from pwdlib import PasswordHash

password = getpass("新的管理员密码（至少 12 个字符）：")
if len(password) < 12:
    raise SystemExit("密码太短：至少需要 12 个字符")
if password != getpass("再次输入密码："):
    raise SystemExit("两次输入的密码不一致")

print("\n把下面一整行写入生产 company.env：")
print(f"ADMIN_PASSWORD_HASH='{PasswordHash.recommended().hash(password)}'")
PY
