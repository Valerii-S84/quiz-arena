from __future__ import annotations

from pathlib import Path

import build_logik500_bank as builder
import pytest

from tests.tools.logik500_test_support import patch_builder, read_output, row, write_source


def test_text_normalizers_strip_versions_whitespace_dashes_and_cues() -> None:
    assert builder.key_family("Alpha_Key-v12") == "alpha_key"
    assert builder.key_family("Beta_Key_2") == "beta_key"
    assert builder.normalize_text("  A\u2011B\u2013C\u2014D   E  ") == "a-b-c-d e"
    assert builder.signature("Was passt logisch? - Sinnvoll ergänzen:  Antwort ") == "antwort"


def test_main_deduplicates_families_and_writes_deterministic_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_one = tmp_path / "source_one.csv"
    source_two = tmp_path / "source_two.csv"
    output_file = tmp_path / "out.csv"
    write_source(
        source_one,
        [
            row("alpha_1", "Was passt logisch? Alpha"),
            row("beta_1", "Beta", level="A2"),
        ],
    )
    write_source(
        source_two,
        [
            row("alpha_2", "Duplicated family loses"),
            row("gamma_1", "Gamma", level="B1"),
        ],
    )
    patch_builder(
        monkeypatch,
        source_files=[("s1", source_one), ("s2", source_two)],
        output_file=output_file,
        target_count=3,
    )

    builder.main()

    rows = read_output(output_file)
    assert [item["quiz_id"] for item in rows] == [
        "logik500_0001",
        "logik500_0002",
        "logik500_0003",
    ]
    assert [item["question"] for item in rows] == ["Was passt logisch? Alpha", "Beta", "Gamma"]
    assert rows[0]["key"] == "logik500_0001_alpha"
    assert "unique_after_family_dedupe=3" in capsys.readouterr().out


def test_main_adds_curated_duplicate_signature_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_file = tmp_path / "source.csv"
    output_file = tmp_path / "out.csv"
    write_source(
        source_file,
        [
            row("alpha_1", "Was passt logisch? Alpha"),
            row("beta_1", "Alpha"),
        ],
    )
    patch_builder(
        monkeypatch,
        source_files=[("s1", source_file)],
        output_file=output_file,
        target_count=2,
        curated_extras={("s1", 3): "Eine neue eindeutige Frage"},
    )

    builder.main()
    capsys.readouterr()

    assert [item["question"] for item in read_output(output_file)] == [
        "Was passt logisch? Alpha",
        "Eine neue eindeutige Frage",
    ]
