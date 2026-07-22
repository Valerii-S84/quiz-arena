from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_growth_delta.sh"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "ci@example.test")
    _git(repo, "config", "user.name", "CI Test")


def _commit_file(repo: Path, relative_path: str, content: str, message: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", relative_path)
    _git(repo, "commit", "-m", message)


def _run_guard(repo: Path, *, path_prefix: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({"CI": "1", "BASE_REF": "origin/main"})
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_growth_guard_fails_closed_for_shallow_checkout_without_merge_base(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    _init_repo(source)
    _commit_file(source, "README.md", "base\n", "base")
    _git(source, "branch", "-M", "main")
    _git(source, "checkout", "-b", "feature")
    _commit_file(source, "app/new.py", "value = 1\n", "feature")

    checkout = tmp_path / "checkout"
    subprocess.run(
        ["git", "clone", "--depth=1", "--branch", "feature", source.as_uri(), str(checkout)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(
        checkout,
        "fetch",
        "--depth=1",
        "origin",
        "main:refs/remotes/origin/main",
    )

    result = _run_guard(checkout)

    assert result.returncode == 1
    assert "requires a merge base for origin/main and HEAD" in result.stderr


def test_growth_guard_propagates_git_diff_failure(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "README.md", "base\n", "base")
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", base_sha)
    _commit_file(repo, "README.md", "head\n", "head")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git_wrapper = bin_dir / "git"
    git_wrapper.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == "diff" ]]; then\n'
        '  echo "forced git diff failure" >&2\n'
        "  exit 42\n"
        "fi\n"
        'exec "$REAL_GIT" "$@"\n',
        encoding="utf-8",
    )
    git_wrapper.chmod(0o755)
    real_git = shutil.which("git")
    assert real_git is not None
    env = os.environ.copy()
    env["REAL_GIT"] = real_git
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env.update({"CI": "1", "BASE_REF": "origin/main"})

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 1
    assert "forced git diff failure" in result.stderr
    assert "failed to diff origin/main...HEAD" in result.stderr


def test_github_ci_fetches_full_history_for_growth_guard() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "uses: actions/checkout@v4\n        with:\n          fetch-depth: 0" in workflow
