from __future__ import annotations

from pathlib import Path

import build_logik500_bank as builder
import pytest

from tests.tools.logik500_test_support import patch_builder, row, write_source


def test_main_rejects_header_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source_one = tmp_path / "source_one.csv"
    source_two = tmp_path / "source_two.csv"
    write_source(source_one, [row("alpha_1", "Alpha")])
    write_source(source_two, [{"quiz_id": "beta_1", "question": "Beta"}], ["quiz_id", "question"])
    patch_builder(
        monkeypatch,
        source_files=[("s1", source_one), ("s2", source_two)],
        output_file=tmp_path / "out.csv",
        target_count=1,
    )

    with pytest.raises(ValueError, match="Column mismatch"):
        builder.main()


def test_main_rejects_missing_input_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patch_builder(
        monkeypatch,
        source_files=[],
        output_file=tmp_path / "out.csv",
        target_count=0,
    )

    with pytest.raises(ValueError, match="No input data found"):
        builder.main()


def test_main_rejects_missing_curated_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "source.csv"
    write_source(source_file, [row("alpha_1", "Alpha")])
    patch_builder(
        monkeypatch,
        source_files=[("s1", source_file)],
        output_file=tmp_path / "out.csv",
        target_count=2,
        curated_extras={("s1", 99): "Missing"},
    )

    with pytest.raises(ValueError, match="Curated extra marker not found"):
        builder.main()


def test_main_rejects_unexpected_target_size(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "source.csv"
    write_source(source_file, [row("alpha_1", "Alpha")])
    patch_builder(
        monkeypatch,
        source_files=[("s1", source_file)],
        output_file=tmp_path / "out.csv",
        target_count=2,
    )

    with pytest.raises(ValueError, match="Unexpected target size"):
        builder.main()


def test_main_rejects_remaining_signature_duplicates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "source.csv"
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
        output_file=tmp_path / "out.csv",
        target_count=2,
        curated_extras={("s1", 3): "Sinnvoll ergänzen: Alpha"},
    )

    with pytest.raises(ValueError, match="Signature duplicates remained"):
        builder.main()
