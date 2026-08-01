#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMIT_MESSAGE = "chore: publish project updates"


class PublishError(RuntimeError):
    pass


def run_git(
    *arguments: str,
    capture_output: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        check=check,
        capture_output=capture_output,
        text=True,
    )


def verify_repository() -> None:
    result = run_git(
        "rev-parse",
        "--is-inside-work-tree",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise PublishError(f"{ROOT} 不是有效的 Git 仓库")


def verify_origin() -> None:
    result = run_git("remote", "get-url", "origin", capture_output=True, check=False)
    if result.returncode != 0:
        raise PublishError("未配置 Git 远端 origin")


def current_branch() -> str:
    result = run_git(
        "symbolic-ref",
        "--quiet",
        "--short",
        "HEAD",
        capture_output=True,
        check=False,
    )
    branch = result.stdout.strip()
    if result.returncode != 0 or not branch:
        raise PublishError("当前仓库处于 detached HEAD，无法确定要推送的分支")
    return branch


def has_staged_changes() -> bool:
    result = run_git("diff", "--cached", "--quiet", check=False)
    if result.returncode == 0:
        return False
    if result.returncode == 1:
        return True
    raise subprocess.CalledProcessError(result.returncode, result.args)


def has_upstream() -> bool:
    result = run_git(
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    print("检查 Git 仓库...")
    verify_repository()
    verify_origin()
    branch = current_branch()

    print("暂存全部新增、修改和删除...")
    run_git("add", "-A")

    if has_staged_changes():
        print(f"创建提交：{COMMIT_MESSAGE}")
        run_git("commit", "-m", COMMIT_MESSAGE)
    else:
        print("没有新的工作区变更，跳过提交。")

    print(f"推送分支 {branch} 到 origin...")
    if has_upstream():
        run_git("push", "origin", branch)
    else:
        run_git("push", "--set-upstream", "origin", branch)

    print("发布完成。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as error:
        print(f"发布失败：{error}", file=sys.stderr)
        raise SystemExit(1) from error
    except subprocess.CalledProcessError as error:
        print(f"发布失败：Git 命令退出状态为 {error.returncode}", file=sys.stderr)
        raise SystemExit(error.returncode or 1) from error
    except FileNotFoundError as error:
        print("发布失败：找不到 git 命令", file=sys.stderr)
        raise SystemExit(1) from error
