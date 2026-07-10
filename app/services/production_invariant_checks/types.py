from __future__ import annotations

from dataclasses import dataclass

SEVERITY_P0 = "P0"
SEVERITY_P1 = "P1"
SEVERITY_P2 = "P2"
STATUS_OK = "OK"
STATUS_FAIL = "FAIL"
BLOCKING_SEVERITIES = frozenset({SEVERITY_P0, SEVERITY_P1})


@dataclass(frozen=True, slots=True)
class InvariantCheck:
    name: str
    severity: str
    sql: str
    params: dict[str, object]
    description: str
    correlation_key: str
    safe_context: dict[str, object]


@dataclass(frozen=True, slots=True)
class InvariantResult:
    name: str
    status: str
    severity: str
    count: int
    description: str
    correlation_key: str
    safe_context: dict[str, object]


def classify_count_result(check: InvariantCheck, *, count: int) -> InvariantResult:
    return InvariantResult(
        name=check.name,
        status=STATUS_OK if count == 0 else STATUS_FAIL,
        severity=check.severity,
        count=count,
        description=check.description,
        correlation_key=check.correlation_key,
        safe_context={**check.safe_context, "count": count},
    )


def build_check(
    *,
    name: str,
    severity: str,
    sql: str,
    description: str,
    params: dict[str, object] | None = None,
    correlation_key: str | None = None,
    safe_context: dict[str, object] | None = None,
) -> InvariantCheck:
    return InvariantCheck(
        name=name,
        severity=severity,
        sql=sql,
        params=params or {},
        description=description,
        correlation_key=correlation_key or name,
        safe_context={"check_name": name, **(safe_context or {})},
    )
