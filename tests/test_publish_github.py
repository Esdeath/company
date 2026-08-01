from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLISHER_SOURCE = PROJECT_ROOT / "scripts" / "publish-github.py"
COMMIT_MESSAGE = "chore: publish project updates"


class PublishGithubTests(unittest.TestCase):
    def setUp(self) -> None:
        if not PUBLISHER_SOURCE.is_file():
            self.fail(f"missing publisher: {PUBLISHER_SOURCE}")

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.workspace = Path(self.temporary_directory.name)
        self.repository = self.workspace / "repository"
        self.remote = self.workspace / "origin.git"
        self.outside_directory = self.workspace / "outside"

        self.repository.mkdir()
        self.outside_directory.mkdir()
        self.git(self.workspace, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.git(self.repository, "init", "--initial-branch=main")
        self.git(self.repository, "config", "user.name", "Publish Test")
        self.git(self.repository, "config", "user.email", "publish@example.com")

        scripts_directory = self.repository / "scripts"
        scripts_directory.mkdir()
        shutil.copy2(PUBLISHER_SOURCE, scripts_directory / PUBLISHER_SOURCE.name)
        (self.repository / "changed.txt").write_text("before\n", encoding="utf-8")
        (self.repository / "deleted.txt").write_text("delete me\n", encoding="utf-8")
        self.git(self.repository, "add", "-A")
        self.git(self.repository, "commit", "-m", "initial")
        self.git(self.repository, "remote", "add", "origin", str(self.remote))
        self.git(self.repository, "push", "--set-upstream", "origin", "main")

    def git(
        self,
        directory: Path,
        *arguments: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(directory), *arguments],
            check=check,
            capture_output=True,
            text=True,
        )

    def run_publisher(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, self.repository / "scripts" / "publish-github.py"],
            cwd=self.outside_directory,
            capture_output=True,
            text=True,
        )

    def remote_head(self) -> str:
        return self.git(
            self.workspace,
            f"--git-dir={self.remote}",
            "rev-parse",
            "refs/heads/main",
        ).stdout.strip()

    def remote_tree(self) -> set[str]:
        output = self.git(
            self.workspace,
            f"--git-dir={self.remote}",
            "ls-tree",
            "-r",
            "--name-only",
            "refs/heads/main",
        ).stdout
        return set(output.splitlines())

    def test_commits_all_change_types_and_pushes(self) -> None:
        (self.repository / "added.txt").write_text("added\n", encoding="utf-8")
        (self.repository / "changed.txt").write_text("after\n", encoding="utf-8")
        (self.repository / "deleted.txt").unlink()

        result = self.run_publisher()

        self.assertEqual(result.returncode, 0, result.stderr)
        subject = self.git(self.repository, "log", "-1", "--format=%s").stdout.strip()
        self.assertEqual(subject, COMMIT_MESSAGE)
        self.assertEqual(
            self.remote_tree(),
            {"added.txt", "changed.txt", "scripts/publish-github.py"},
        )

    def test_pushes_existing_commit_without_creating_empty_commit(self) -> None:
        (self.repository / "unpublished.txt").write_text("local commit\n", encoding="utf-8")
        self.git(self.repository, "add", "unpublished.txt")
        self.git(self.repository, "commit", "-m", "local only")
        before = self.git(self.repository, "rev-parse", "HEAD").stdout.strip()

        result = self.run_publisher()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git(self.repository, "rev-parse", "HEAD").stdout.strip(), before)
        self.assertEqual(self.remote_head(), before)

    def test_sets_upstream_when_current_branch_has_none(self) -> None:
        self.git(self.repository, "branch", "--unset-upstream")
        (self.repository / "added.txt").write_text("new branch state\n", encoding="utf-8")

        result = self.run_publisher()

        self.assertEqual(result.returncode, 0, result.stderr)
        upstream = self.git(
            self.repository,
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{upstream}",
        ).stdout.strip()
        self.assertEqual(upstream, "origin/main")

    def test_fails_without_origin(self) -> None:
        self.git(self.repository, "remote", "remove", "origin")

        result = self.run_publisher()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("origin", result.stderr)

    def test_fails_on_detached_head(self) -> None:
        self.git(self.repository, "checkout", "--detach")

        result = self.run_publisher()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("detached HEAD", result.stderr)


if __name__ == "__main__":
    unittest.main()
