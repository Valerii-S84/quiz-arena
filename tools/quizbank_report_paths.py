from __future__ import annotations

from pathlib import Path


def csv_sort_key(path: Path) -> tuple[str, str]:
    return (path.name.casefold(), path.name)


def report_path(path: Path) -> str:
    return path.as_posix()
