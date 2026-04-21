from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _install_fake_ssh(bin_dir: Path) -> None:
    _write_executable(
        bin_dir / "ssh",
        """#!/usr/bin/env bash
set -euo pipefail

remote=$1
shift
command=$1

printf '%s\\n' "$command" >> "${FAKE_SSH_LOG}"

if [[ "$command" == mkdir\\ -p* ]]; then
  mkdir -p "${command#mkdir -p }"
  exit 0
fi

if [[ "$command" == *"[[ -f .env ]]"* ]]; then
  target_dir=${command#cd }
  target_dir=${target_dir%% &&*}
  [[ -f "$target_dir/.env" ]]
  exit $?
fi

if [[ "$command" == cd* && "$command" == *"docker compose"* ]]; then
  printf '%s\\n' "$command" >> "${FAKE_DEPLOY_LOG}"
  exit 0
fi

echo "unexpected ssh command for ${remote}: ${command}" >&2
exit 1
""",
    )


def _install_fake_rsync(bin_dir: Path) -> None:
    _write_executable(
        bin_dir / "rsync",
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "${FAKE_RSYNC_LOG}"
""",
    )


def _run_deploy(tmp_path: Path, *, remote_dir: Path) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_ssh(bin_dir)
    _install_fake_rsync(bin_dir)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_SSH_LOG"] = str(tmp_path / "ssh.log")
    env["FAKE_RSYNC_LOG"] = str(tmp_path / "rsync.log")
    env["FAKE_DEPLOY_LOG"] = str(tmp_path / "deploy.log")

    return subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "deploy@example.com", str(remote_dir)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_deploy_fails_when_remote_env_is_missing(tmp_path: Path) -> None:
    remote_dir = tmp_path / "remote"
    result = _run_deploy(tmp_path, remote_dir=remote_dir)

    assert result.returncode == 1
    assert "missing required remote env file" in result.stderr
    assert "Refusing to deploy without a server-managed .env." in result.stderr
    assert not (tmp_path / "deploy.log").exists()


def test_deploy_continues_when_remote_env_exists(tmp_path: Path) -> None:
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    (remote_dir / ".env").write_text("APP_ENV=production\n", encoding="utf-8")

    result = _run_deploy(tmp_path, remote_dir=remote_dir)

    assert result.returncode == 0
    assert "Deploy finished." in result.stdout
    deploy_command = (tmp_path / "deploy.log").read_text(encoding="utf-8")
    assert "docker compose -f docker-compose.prod.yml up -d postgres redis" in deploy_command
    assert ".env.production.example" not in deploy_command
