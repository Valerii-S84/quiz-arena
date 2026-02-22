from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read_summary(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _metric_values(
    metrics: dict[str, object],
    *,
    metric_name: str,
    flow_tag: str,
) -> dict[str, float] | None:
    exact = metrics.get(metric_name)
    if isinstance(exact, dict):
        values = exact.get("values")
        if isinstance(values, dict):
            return {str(k): float(v) for k, v in values.items()}

    tagged_prefix = f"{metric_name}{{"
    for key, payload in metrics.items():
        if not key.startswith(tagged_prefix):
            continue
        if f"flow:{flow_tag}" not in key:
            continue
        if isinstance(payload, dict):
            values = payload.get("values")
            if isinstance(values, dict):
                return {str(k): float(v) for k, v in values.items()}
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate SLO gate from k6 summary + DB lock waits.")
    parser.add_argument("--summary-file", required=True)
    parser.add_argument("--flow-tag", default="webhook_start")
    parser.add_argument("--max-p95-ms", type=float, required=True)
    parser.add_argument("--max-error-rate", type=float, required=True)
    parser.add_argument("--db-lock-waits", type=int, required=True)
    parser.add_argument("--max-db-lock-waits", type=int, required=True)
    parser.add_argument("--deadlocks-delta", type=int, required=True)
    parser.add_argument("--max-deadlocks-delta", type=int, default=0)
    args = parser.parse_args()

    summary = _read_summary(Path(args.summary_file))
    metrics = summary.get("metrics")
    if not isinstance(metrics, dict):
        raise SystemExit("SLO_FAIL: summary file does not contain metrics payload")

    duration_values = _metric_values(metrics, metric_name="http_req_duration", flow_tag=args.flow_tag)
    failed_values = _metric_values(metrics, metric_name="http_req_failed", flow_tag=args.flow_tag)
    if duration_values is None or failed_values is None:
        raise SystemExit("SLO_FAIL: required metrics not found in k6 summary")

    p95_ms = float(duration_values.get("p(95)", duration_values.get("p95", 0.0)))
    error_rate = float(failed_values.get("rate", 1.0))

    failures: list[str] = []
    if p95_ms > args.max_p95_ms:
        failures.append(f"p95={p95_ms:.2f}ms > {args.max_p95_ms:.2f}ms")
    if error_rate > args.max_error_rate:
        failures.append(f"error_rate={error_rate:.6f} > {args.max_error_rate:.6f}")
    if args.db_lock_waits > args.max_db_lock_waits:
        failures.append(f"db_lock_waits={args.db_lock_waits} > {args.max_db_lock_waits}")
    if args.deadlocks_delta > args.max_deadlocks_delta:
        failures.append(f"deadlocks_delta={args.deadlocks_delta} > {args.max_deadlocks_delta}")

    result = {
        "flow_tag": args.flow_tag,
        "p95_ms": round(p95_ms, 3),
        "max_p95_ms": args.max_p95_ms,
        "error_rate": round(error_rate, 6),
        "max_error_rate": args.max_error_rate,
        "db_lock_waits": args.db_lock_waits,
        "max_db_lock_waits": args.max_db_lock_waits,
        "deadlocks_delta": args.deadlocks_delta,
        "max_deadlocks_delta": args.max_deadlocks_delta,
        "pass": len(failures) == 0,
        "failures": failures,
    }
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    if failures:
        raise SystemExit("SLO_FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
