from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts import evaluate_slo_gate as slo


def _write_summary(path: Path, metrics: object) -> None:
    path.write_text(json.dumps({"metrics": metrics}), encoding="utf-8")


def _argv(summary_file: Path, *extra: str) -> list[str]:
    return [
        "evaluate_slo_gate.py",
        "--summary-file",
        str(summary_file),
        "--max-p95-ms",
        "250",
        "--max-error-rate",
        "0.01",
        "--db-lock-waits",
        "0",
        "--max-db-lock-waits",
        "0",
        "--deadlocks-delta",
        "0",
        *extra,
    ]


def test_read_summary_loads_json_payload(tmp_path: Path) -> None:
    summary_file = tmp_path / "summary.json"
    summary_file.write_text('{"metrics": {}}', encoding="utf-8")

    assert slo._read_summary(summary_file) == {"metrics": {}}


def test_metric_values_extracts_nested_exact_values() -> None:
    metrics: dict[str, object] = {"http_req_duration": {"values": {"p(95)": 123, "avg": "45.5"}}}

    assert slo._metric_values(metrics, metric_name="http_req_duration", flow_tag="start") == {
        "p(95)": 123.0,
        "avg": 45.5,
    }


def test_metric_values_prefers_matching_tagged_metric() -> None:
    metrics = {
        "http_req_duration": {"values": {"p(95)": 500}},
        "http_req_duration{flow:webhook_start,status:ok}": {"p95": 120, "type": "trend"},
    }

    assert slo._metric_values(
        metrics,
        metric_name="http_req_duration",
        flow_tag="webhook_start",
    ) == {"p95": 120.0}


def test_metric_values_falls_back_to_exact_metric_when_tag_payload_is_empty() -> None:
    metrics = {
        "http_req_failed": {"rate": 0},
        "http_req_failed{flow:webhook_start}": {"type": "rate"},
    }

    assert slo._metric_values(metrics, metric_name="http_req_failed", flow_tag="webhook_start") == {
        "rate": 0.0
    }


def test_metric_values_returns_none_for_non_mapping_payload() -> None:
    assert (
        slo._metric_values({"http_req_duration": []}, metric_name="http_req_duration", flow_tag="x")
        is None
    )


def test_main_prints_passing_gate_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary_file = tmp_path / "summary.json"
    _write_summary(
        summary_file,
        {
            "http_req_duration{flow:webhook_start}": {"values": {"p(95)": 200}},
            "http_req_failed{flow:webhook_start}": {"values": {"rate": 0.001}},
        },
    )
    monkeypatch.setattr(sys, "argv", _argv(summary_file))

    assert slo.main() == 0

    result = json.loads(capsys.readouterr().out)
    assert result["pass"] is True
    assert result["p95_ms"] == 200.0
    assert result["error_rate"] == 0.001
    assert result["failures"] == []


def test_main_reports_all_failing_slo_dimensions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary_file = tmp_path / "summary.json"
    _write_summary(
        summary_file,
        {
            "http_req_duration": {"p95": 251},
            "http_req_failed": {"value": 0.02},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        _argv(
            summary_file,
            "--db-lock-waits",
            "2",
            "--deadlocks-delta",
            "1",
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        slo.main()

    assert exc_info.value.code == "SLO_FAIL"
    result = json.loads(capsys.readouterr().out)
    assert result["pass"] is False
    assert result["failures"] == [
        "p95=251.00ms > 250.00ms",
        "error_rate=0.020000 > 0.010000",
        "db_lock_waits=2 > 0",
        "deadlocks_delta=1 > 0",
    ]


def test_main_rejects_summary_without_metrics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    summary_file = tmp_path / "summary.json"
    summary_file.write_text('{"not_metrics": {}}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", _argv(summary_file))

    with pytest.raises(SystemExit, match="summary file does not contain metrics"):
        slo.main()


def test_main_rejects_missing_required_metrics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    summary_file = tmp_path / "summary.json"
    _write_summary(summary_file, {"http_req_duration": {"values": {"p(95)": 1}}})
    monkeypatch.setattr(sys, "argv", _argv(summary_file))

    with pytest.raises(SystemExit, match="required metrics not found"):
        slo.main()
