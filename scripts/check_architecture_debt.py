from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BASE_REF = "origin/main"
MAX_APP_FILE_LINES = 220
MAX_TEST_FILE_LINES = 400
MAX_TOOL_FILE_LINES = 300
MAX_NEW_BOT_HANDLER_LINES = 180
MAX_FUNCTION_LINES = 60
MAX_FUNCTION_PARAMS = 7
MAX_NESTING = 3

NESTING_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.Match,
)


@dataclass(frozen=True)
class FunctionMetric:
    qualname: str
    lineno: int
    lines: int
    params: int
    nesting: int


@dataclass(frozen=True)
class FileMetric:
    path: str
    lines: int
    functions: dict[str, FunctionMetric]


@dataclass(frozen=True)
class Violation:
    path: str
    label: str
    metric: int
    limit: int
    function: str | None = None
    lineno: int | None = None

    def render(self) -> str:
        location = self.path
        if self.lineno is not None:
            location = f"{location}:{self.lineno}"
        subject = f"{location} {self.function}" if self.function else location
        return f"{self.label} {self.metric}>{self.limit}: {subject}"


def run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )


def base_ref() -> str:
    return sys.argv[1] if len(sys.argv) > 1 else BASE_REF


def base_available(ref: str) -> bool:
    return run_git(["rev-parse", "--verify", ref]).returncode == 0


def changed_paths(ref: str) -> set[str]:
    result = run_git(["diff", "--name-only", f"{ref}...HEAD"])
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def added_paths(ref: str) -> set[str]:
    result = run_git(["diff", "--name-status", "--diff-filter=A", f"{ref}...HEAD"])
    if result.returncode != 0:
        return set()
    return {line.split(maxsplit=1)[1] for line in result.stdout.splitlines() if line.strip()}


def read_base_file(ref: str, path: str) -> str | None:
    result = run_git(["show", f"{ref}:{path}"])
    if result.returncode != 0:
        return None
    return result.stdout


def count_lines(content: str) -> int:
    if not content:
        return 0
    return content.count("\n") + (0 if content.endswith("\n") else 1)


def max_nesting(node: ast.AST, depth: int = 0) -> int:
    current = depth + 1 if isinstance(node, NESTING_NODES) else depth
    children = (
        child
        for child in ast.iter_child_nodes(node)
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    return max(
        (max_nesting(child, current) for child in children),
        default=current,
    )


def param_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    return (
        len(node.args.posonlyargs)
        + len(node.args.args)
        + len(node.args.kwonlyargs)
        + (1 if node.args.vararg else 0)
        + (1 if node.args.kwarg else 0)
    )


def function_metrics(tree: ast.AST) -> dict[str, FunctionMetric]:
    metrics: dict[str, FunctionMetric] = {}

    def visit(node: ast.AST, parents: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, [*parents, child.name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = ".".join([*parents, child.name])
                end_lineno = child.end_lineno or child.lineno
                metrics[qualname] = FunctionMetric(
                    qualname=qualname,
                    lineno=child.lineno,
                    lines=end_lineno - child.lineno + 1,
                    params=param_count(child),
                    nesting=max_nesting(child),
                )
                visit(child, [*parents, child.name])
            else:
                visit(child, parents)

    visit(tree, [])
    return metrics


def parse_file(path: str, content: str) -> FileMetric:
    tree = ast.parse(content, filename=path)
    return FileMetric(path=path, lines=count_lines(content), functions=function_metrics(tree))


def collect_current_metrics() -> dict[str, FileMetric]:
    metrics: dict[str, FileMetric] = {}
    for root in ("app", "tests", "tools"):
        root_path = Path(root)
        if not root_path.exists():
            continue
        for path in sorted(root_path.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            metrics[str(path)] = parse_file(str(path), text)
    return metrics


def collect_base_metrics(ref: str, paths: set[str]) -> dict[str, FileMetric]:
    metrics: dict[str, FileMetric] = {}
    for path in sorted(paths):
        text = read_base_file(ref, path)
        if text is None:
            continue
        metrics[path] = parse_file(path, text)
    return metrics


def file_limit(path: str) -> int | None:
    if path.startswith("app/"):
        return MAX_APP_FILE_LINES
    if path.startswith("tests/"):
        return MAX_TEST_FILE_LINES
    if path.startswith("tools/"):
        return MAX_TOOL_FILE_LINES
    return None


def violations_for(metric: FileMetric) -> list[Violation]:
    violations: list[Violation] = []
    limit = file_limit(metric.path)
    if limit is not None and metric.lines > limit:
        violations.append(Violation(metric.path, "file-lines", metric.lines, limit))

    if metric.path.startswith("app/bot/handlers/") and metric.lines > MAX_NEW_BOT_HANDLER_LINES:
        violations.append(
            Violation(metric.path, "bot-handler-lines", metric.lines, MAX_NEW_BOT_HANDLER_LINES)
        )

    if not metric.path.startswith("app/"):
        return violations

    for function in metric.functions.values():
        if function.lines > MAX_FUNCTION_LINES:
            violations.append(
                Violation(
                    metric.path,
                    "function-lines",
                    function.lines,
                    MAX_FUNCTION_LINES,
                    function.qualname,
                    function.lineno,
                )
            )
        if function.params > MAX_FUNCTION_PARAMS:
            violations.append(
                Violation(
                    metric.path,
                    "function-params",
                    function.params,
                    MAX_FUNCTION_PARAMS,
                    function.qualname,
                    function.lineno,
                )
            )
        if function.nesting > MAX_NESTING:
            violations.append(
                Violation(
                    metric.path,
                    "function-nesting",
                    function.nesting,
                    MAX_NESTING,
                    function.qualname,
                    function.lineno,
                )
            )

    return violations


def baseline_value(base_metric: FileMetric | None, violation: Violation) -> int | None:
    if base_metric is None:
        return None
    if violation.function is None:
        return base_metric.lines
    function = base_metric.functions.get(violation.function)
    if function is None:
        return None
    if violation.label == "function-lines":
        return function.lines
    if violation.label == "function-params":
        return function.params
    if violation.label == "function-nesting":
        return function.nesting
    return None


def is_new_or_worse(violation: Violation, base_metric: FileMetric | None) -> bool:
    previous = baseline_value(base_metric, violation)
    if previous is None:
        return True
    return previous <= violation.limit or violation.metric > previous


def main() -> int:
    ref = base_ref()
    current = collect_current_metrics()
    current_paths = set(current)
    have_base = base_available(ref)
    changed = changed_paths(ref) if have_base else set()
    added = added_paths(ref) if have_base else set()
    base = collect_base_metrics(ref, current_paths & changed) if have_base else {}

    errors: list[str] = []
    warnings: list[str] = []
    totals: dict[str, int] = {}

    for path, metric in current.items():
        for violation in violations_for(metric):
            totals[violation.label] = totals.get(violation.label, 0) + 1
            base_metric = base.get(path)
            path_changed = path in changed or path in added
            if have_base and path_changed and is_new_or_worse(violation, base_metric):
                errors.append(f"ERROR: new architecture debt: {violation.render()}")
            else:
                warnings.append(f"WARNING: legacy architecture debt: {violation.render()}")

    for key in sorted(totals):
        print(f"{key}: {totals[key]}")

    for warning in warnings:
        print(warning, file=sys.stderr)
    for error in errors:
        print(error, file=sys.stderr)

    if not have_base:
        print(f"WARNING: base ref {ref} unavailable; architecture debt guard is warning-only.")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
