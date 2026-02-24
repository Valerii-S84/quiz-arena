#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT_DIR"

PYTHON_BIN=".venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

APP_DIR = Path("app")


def _module_name(path: Path) -> str:
    if path.name == "__init__.py":
        return ".".join(path.relative_to(Path(".")).parent.parts)
    return ".".join(path.relative_to(Path(".")).with_suffix("").parts)


def _is_package_module(path: Path) -> bool:
    return path.name == "__init__.py"


def _resolve_from_import(
    *,
    current_module: str,
    import_module: str | None,
    level: int,
    is_package_module: bool,
) -> str | None:
    if level == 0:
        return import_module

    package = current_module if is_package_module else current_module.rsplit(".", 1)[0]
    package_parts = package.split(".")
    anchor_size = len(package_parts) - level + 1
    anchor_parts = package_parts[: max(anchor_size, 0)]
    anchor = ".".join(anchor_parts)

    if import_module:
        return f"{anchor}.{import_module}" if anchor else import_module
    return anchor or None


def _closest_existing_module(candidate: str, known_modules: set[str]) -> str | None:
    module_name = candidate
    while True:
        if module_name in known_modules:
            return module_name
        if "." not in module_name:
            return None
        module_name = module_name.rsplit(".", 1)[0]


def _collect_dependencies(*, path: Path, known_modules: set[str]) -> set[str]:
    content = path.read_text(encoding="utf-8")
    tree = ast.parse(content)
    current_module = _module_name(path)
    dependencies: set[str] = set()

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not alias.name.startswith("app"):
                    continue
                resolved = _closest_existing_module(alias.name, known_modules)
                if resolved is not None and resolved != current_module:
                    dependencies.add(resolved)

        elif isinstance(node, ast.ImportFrom):
            resolved_module = _resolve_from_import(
                current_module=current_module,
                import_module=node.module,
                level=node.level,
                is_package_module=_is_package_module(path),
            )
            candidates: list[str] = []
            if resolved_module is not None:
                candidates.append(resolved_module)
                for alias in node.names:
                    if alias.name != "*":
                        candidates.append(f"{resolved_module}.{alias.name}")

            for candidate in candidates:
                if not candidate.startswith("app"):
                    continue
                resolved = _closest_existing_module(candidate, known_modules)
                if resolved is not None and resolved != current_module:
                    dependencies.add(resolved)

    return dependencies


def _find_scc(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    stack: list[str] = []
    in_stack: set[str] = set()
    node_index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    components: list[list[str]] = []

    def strongconnect(node: str) -> None:
        nonlocal index
        node_index[node] = index
        lowlink[node] = index
        index += 1
        stack.append(node)
        in_stack.add(node)

        for neighbor in sorted(graph[node]):
            if neighbor not in node_index:
                strongconnect(neighbor)
                lowlink[node] = min(lowlink[node], lowlink[neighbor])
            elif neighbor in in_stack:
                lowlink[node] = min(lowlink[node], node_index[neighbor])

        if lowlink[node] == node_index[node]:
            component: list[str] = []
            while True:
                popped = stack.pop()
                in_stack.remove(popped)
                component.append(popped)
                if popped == node:
                    break
            components.append(sorted(component))

    for node in sorted(graph):
        if node not in node_index:
            strongconnect(node)

    return components


python_files = sorted(
    path
    for path in APP_DIR.rglob("*.py")
    if "__pycache__" not in path.parts and path.name != "__init__.py"
)
known_modules = {_module_name(path) for path in python_files}

graph: dict[str, set[str]] = defaultdict(set)
for file_path in python_files:
    module = _module_name(file_path)
    graph[module].update(_collect_dependencies(path=file_path, known_modules=known_modules))

for module in known_modules:
    graph.setdefault(module, set())

cycles = [component for component in _find_scc(graph) if len(component) > 1]

if cycles:
    print("ERROR: cyclic imports detected in app/")
    for index, cycle in enumerate(cycles, start=1):
        print(f"  {index}. {' -> '.join(cycle)}")
    raise SystemExit(1)

print("OK: no import cycles detected in app/")
PY
