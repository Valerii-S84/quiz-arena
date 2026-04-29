from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from scripts.promo_batch_tool import (
    RawPromo,
    _build_batch,
    _load_raw_codes_from_csv,
    _validate_args,
    _write_output,
)


def _args(**overrides: object) -> Namespace:
    values = {
        "campaign_name": "Launch",
        "promo_type": "PREMIUM_GRANT",
        "grant_premium_days": 7,
        "discount_percent": None,
        "target_scope": "ALL",
        "valid_from": "2026-04-29T10:00:00Z",
        "valid_until": "2026-05-29T10:00:00Z",
        "max_total_uses": None,
        "created_by": "test",
        "new_users_only": False,
        "first_purchase_only": False,
        "import_csv": None,
        "count": 1,
        "prefix": "",
        "token_length": 8,
        "output_csv": None,
        "dry_run": True,
    }
    values.update(overrides)
    return Namespace(**values)


def test_load_raw_codes_from_csv_prefers_raw_code_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("raw_code,note\n ALPHA-1 ,keep\n,skip\nBETA-2,keep\n", encoding="utf-8")

    assert _load_raw_codes_from_csv(csv_path) == ["ALPHA-1", "BETA-2"]


def test_load_raw_codes_from_plain_lines_when_no_raw_code_header(tmp_path: Path) -> None:
    csv_path = tmp_path / "codes.txt"
    csv_path.write_text("ALPHA-1\n\nBETA-2\n", encoding="utf-8")

    assert _load_raw_codes_from_csv(csv_path) == ["ALPHA-1", "BETA-2"]


def test_validate_args_rejects_conflicting_sources(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="either --import-csv or --count"):
        _validate_args(_args(import_csv=tmp_path / "codes.csv", count=3))


def test_validate_args_requires_import_or_count() -> None:
    with pytest.raises(ValueError, match="one of --import-csv or --count is required"):
        _validate_args(_args(import_csv=None, count=None))


def test_validate_args_rejects_premium_discount_mix() -> None:
    with pytest.raises(ValueError, match="--discount-percent must not be used"):
        _validate_args(_args(discount_percent=10))


def test_validate_args_rejects_invalid_percent_discount() -> None:
    with pytest.raises(ValueError, match="--discount-percent must be in range"):
        _validate_args(
            _args(
                promo_type="PERCENT_DISCOUNT",
                grant_premium_days=None,
                discount_percent=0,
            )
        )


def test_validate_args_rejects_invalid_date_window() -> None:
    with pytest.raises(ValueError, match="--valid-until must be greater"):
        _validate_args(
            _args(
                valid_from="2026-05-29T10:00:00Z",
                valid_until="2026-04-29T10:00:00Z",
            )
        )


def test_validate_args_rejects_non_positive_max_total_uses() -> None:
    with pytest.raises(ValueError, match="--max-total-uses must be positive"):
        _validate_args(_args(max_total_uses=0))


@pytest.mark.asyncio
async def test_build_batch_imports_and_hashes_unique_codes(tmp_path: Path) -> None:
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("raw_code\n alpha-1 \nBETA 2\n", encoding="utf-8")

    batch = await _build_batch(_args(import_csv=csv_path, count=None))

    assert [item.raw_code for item in batch] == ["alpha-1", "BETA 2"]
    assert [item.normalized_code for item in batch] == ["ALPHA1", "BETA2"]
    assert all(len(item.code_hash) == 64 for item in batch)


@pytest.mark.asyncio
async def test_build_batch_generates_codes_with_normalized_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    def fake_generate_raw_codes(*, count: int, token_length: int, prefix: str) -> list[str]:
        calls.update({"count": count, "token_length": token_length, "prefix": prefix})
        return ["VIP-ABC123"]

    monkeypatch.setattr("scripts.promo_batch_tool.generate_raw_codes", fake_generate_raw_codes)

    batch = await _build_batch(_args(count=1, prefix=" vip ", token_length=6))

    assert calls == {"count": 1, "token_length": 6, "prefix": "VIP-"}
    assert [item.raw_code for item in batch] == ["VIP-ABC123"]
    assert [item.normalized_code for item in batch] == ["VIPABC123"]


@pytest.mark.asyncio
async def test_build_batch_rejects_duplicate_normalized_codes(tmp_path: Path) -> None:
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("raw_code\nalpha-1\nALPHA 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate promo code"):
        await _build_batch(_args(import_csv=csv_path, count=None))


@pytest.mark.asyncio
async def test_build_batch_rejects_empty_input_file(tmp_path: Path) -> None:
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("raw_code\n\n", encoding="utf-8")

    with pytest.raises(ValueError, match="no promo codes to process"):
        await _build_batch(_args(import_csv=csv_path, count=None))


def test_write_output_creates_parent_and_serializes_rows(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "codes.csv"

    _write_output(
        output_path,
        [RawPromo("Alpha-1", "ALPHA1", "hash", promo_code_id=42)],
    )

    assert output_path.read_text(encoding="utf-8") == (
        "raw_code,promo_code_id,normalized_code\nAlpha-1,42,ALPHA1\n"
    )
