# GitHub One-Command Publish Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an executable `./deploy.sh` that stages every repository change, creates a fixed-message commit when needed, and pushes the current branch to GitHub.

**Architecture:** A minimal Bash launcher resolves the repository root and invokes a Python standard-library program. The Python program runs Git commands with `subprocess`, stops on the first failure, and conditionally creates a commit or configures an upstream before pushing. Black-box `unittest` cases copy the scripts into temporary repositories backed by local bare remotes.

**Tech Stack:** Bash, Python 3 standard library, Git, `unittest`

## Global Constraints

- The user-facing entry point is exactly `./deploy.sh`.
- Stage all additions, modifications, and deletions with `git add -A`.
- Use the fixed commit message `chore: publish project updates`.
- Do not create an empty commit when there are no staged changes.
- Push existing unpublished commits even when the worktree has no new changes.
- Never force-push, rewrite remote history, or run `make check` automatically.
- Do not contact the real GitHub remote during automated tests.

---

### Task 1: Publish Workflow

**Files:**
- Create: `scripts/publish-github.py`
- Test: `tests/test_publish_github.py`

**Interfaces:**
- Consumes: Git executable available on `PATH`; repository root derived from `Path(__file__).resolve().parents[1]`.
- Produces: `main() -> int`, returning `0` after a successful push and a nonzero process status when Git rejects an operation.

- [ ] **Step 1: Write failing black-box tests**

Create temporary local repositories and a bare `origin`. Copy `scripts/publish-github.py` into each repository, configure a test Git identity, and assert these concrete outcomes:

```python
def test_commits_all_change_types_and_pushes():
    result = run_publisher(repository)
    assert result.returncode == 0
    assert git(repository, "log", "-1", "--format=%s").stdout.strip() == COMMIT_MESSAGE
    assert remote_tree(repository) == {"added.txt", "changed.txt"}

def test_pushes_existing_commit_without_creating_empty_commit():
    before = git(repository, "rev-parse", "HEAD").stdout.strip()
    result = run_publisher(repository)
    assert result.returncode == 0
    assert git(repository, "rev-parse", "HEAD").stdout.strip() == before
    assert remote_head(repository) == before

def test_fails_without_origin():
    result = run_publisher(repository_without_origin)
    assert result.returncode != 0

def test_fails_on_detached_head():
    result = run_publisher(detached_repository)
    assert result.returncode != 0
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 tests/test_publish_github.py -v`

Expected: FAIL because `scripts/publish-github.py` does not exist in the test fixture source.

- [ ] **Step 3: Implement the Python workflow**

Implement a `run_git(*args, check=True)` helper with `subprocess.run`, preserving inherited stdout and stderr for mutating commands. In `main()`:

```python
verify_repository()
verify_origin()
branch = current_branch()
run_git("add", "-A")
if has_staged_changes():
    run_git("commit", "-m", COMMIT_MESSAGE)
if has_upstream():
    run_git("push", "origin", branch)
else:
    run_git("push", "--set-upstream", "origin", branch)
return 0
```

Catch `subprocess.CalledProcessError` only at the CLI boundary and return its nonzero status. Print short Chinese progress messages before staging, committing, and pushing; let Git print its own diagnostics.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python3 tests/test_publish_github.py -v`

Expected: all workflow tests PASS without network access.

- [ ] **Step 5: Commit the workflow**

```bash
git add scripts/publish-github.py tests/test_publish_github.py
git commit -m "feat: add GitHub publish workflow"
```

### Task 2: Executable Entry Point

**Files:**
- Create: `deploy.sh`
- Modify: `tests/test_publish_github.py`

**Interfaces:**
- Consumes: `python3` on `PATH` and `scripts/publish-github.py` relative to the launcher.
- Produces: executable command `./deploy.sh` that works regardless of the caller's current directory.

- [ ] **Step 1: Write a failing launcher test**

Add a test that copies both files into a temporary repository, invokes the launcher from a directory outside that repository, and checks that the local bare remote receives the new commit:

```python
def test_deploy_launcher_works_outside_repository_directory():
    result = subprocess.run([repository / "deploy.sh"], cwd=outside_directory)
    assert result.returncode == 0
    assert remote_head(repository) == git(repository, "rev-parse", "HEAD").stdout.strip()
```

- [ ] **Step 2: Run the launcher test and verify RED**

Run: `python3 tests/test_publish_github.py PublishGithubTests.test_deploy_launcher_works_outside_repository_directory -v`

Expected: FAIL because `deploy.sh` does not exist.

- [ ] **Step 3: Implement the launcher**

Create an executable file with this behavior:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$ROOT/scripts/publish-github.py"
```

Set its executable bit with `chmod +x deploy.sh`.

- [ ] **Step 4: Run focused and repository contract tests**

Run: `python3 tests/test_publish_github.py -v`

Expected: all publish tests PASS.

Run: `node --test tests/docs.test.mjs tests/prototype.test.mjs tests/scaffold.test.mjs`

Expected: all repository contract tests PASS.

- [ ] **Step 5: Commit the launcher**

```bash
git add deploy.sh tests/test_publish_github.py
git commit -m "feat: add one-command GitHub publisher"
```

### Task 3: Final Verification

**Files:**
- Verify: `deploy.sh`
- Verify: `scripts/publish-github.py`
- Verify: `tests/test_publish_github.py`

**Interfaces:**
- Consumes: completed Tasks 1 and 2.
- Produces: verified publishing command without executing it against the real repository.

- [ ] **Step 1: Check syntax and formatting**

Run: `bash -n deploy.sh && python3 -m py_compile scripts/publish-github.py tests/test_publish_github.py && git diff --check`

Expected: exit status `0` with no diagnostics.

- [ ] **Step 2: Run the complete isolated test suite**

Run: `python3 tests/test_publish_github.py -v`

Expected: all tests PASS and every push targets a temporary local bare repository.

- [ ] **Step 3: Inspect final repository state**

Run: `git status --short --branch`

Expected: the pre-existing user changes remain visible; no test artifact is left behind and the real `origin` remains untouched.
