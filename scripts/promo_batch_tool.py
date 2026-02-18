from __future__ import annotations

import argparse
import asyncio
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.db.models.promo_codes import PromoCode
from app.db.repo.promo_repo import PromoRepo
from app.db.session import SessionLocal
from app.economy.promo.batch import generate_raw_codes, parse_utc_datetime
from app.services.promo_codes import hash_promo_code, normalize_promo_code


@dataclass(slots=True)
class RawPromo:
    raw_code: str
    normalized_code: str
    code_hash: str
    promo_code_id: int | None = None


def _load_raw_codes_from_csv(path: Path) -> list[str]:
    rows: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if "raw_code" in (reader.fieldnames or []):
            for row in reader:
                raw = (row.get("raw_code") or "").strip()
                if raw:
                    rows.append(raw)
            return rows

    with path.open("r", encoding="utf-8", newline="") as file:
        for line in file:
            raw = line.strip()
            if raw:
                rows.append(raw)
    return rows


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promo code batch generation/import tool")
    parser.add_argument("--campaign-name", required=True)
    parser.add_argument("--promo-type", choices=("PREMIUM_GRANT", "PERCENT_DISCOUNT"), required=True)
    parser.add_argument("--grant-premium-days", type=int)
    parser.add_argument("--discount-percent", type=int)
    parser.add_argument("--target-scope", required=True)
    parser.add_argument("--valid-from", required=True, help="ISO datetime")
    parser.add_argument("--valid-until", required=True, help="ISO datetime")
    parser.add_argument("--max-total-uses", type=int)
    parser.add_argument("--created-by", required=True)
    parser.add_argument("--new-users-only", action="store_true")
    parser.add_argument("--first-purchase-only", action="store_true")
    parser.add_argument("--import-csv", type=Path)
    parser.add_argument("--count", type=int)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--token-length", type=int, default=8)
    parser.add_argument("--output-csv", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _validate_args(args: argparse.Namespace) -> None:
    if args.import_csv and args.count:
        raise ValueError("use either --import-csv or --count")
    if not args.import_csv and not args.count:
        raise ValueError("one of --import-csv or --count is required")

    if args.promo_type == "PREMIUM_GRANT":
        if args.grant_premium_days not in {7, 30, 90}:
            raise ValueError("--grant-premium-days must be one of 7, 30, 90 for PREMIUM_GRANT")
        if args.discount_percent is not None:
            raise ValueError("--discount-percent must not be used for PREMIUM_GRANT")
    else:
        if args.discount_percent is None or not (1 <= args.discount_percent <= 90):
            raise ValueError("--discount-percent must be in range 1..90 for PERCENT_DISCOUNT")
        if args.grant_premium_days is not None:
            raise ValueError("--grant-premium-days must not be used for PERCENT_DISCOUNT")

    valid_from = parse_utc_datetime(args.valid_from)
    valid_until = parse_utc_datetime(args.valid_until)
    if valid_until <= valid_from:
        raise ValueError("--valid-until must be greater than --valid-from")
    if args.max_total_uses is not None and args.max_total_uses <= 0:
        raise ValueError("--max-total-uses must be positive")


async def _build_batch(args: argparse.Namespace) -> list[RawPromo]:
    if args.import_csv:
        raw_codes = _load_raw_codes_from_csv(args.import_csv)
    else:
        prefix = args.prefix.strip().upper()
        if prefix and not prefix.endswith("-"):
            prefix = f"{prefix}-"
        raw_codes = generate_raw_codes(
            count=args.count,
            token_length=args.token_length,
            prefix=prefix,
        )

    if not raw_codes:
        raise ValueError("no promo codes to process")

    pepper = get_settings().promo_secret_pepper
    seen_normalized: set[str] = set()
    batch: list[RawPromo] = []
    for raw_code in raw_codes:
        normalized_code = normalize_promo_code(raw_code)
        if not normalized_code:
            raise ValueError(f"promo code '{raw_code}' becomes empty after normalization")
        if normalized_code in seen_normalized:
            raise ValueError(f"duplicate promo code in batch: {raw_code}")
        seen_normalized.add(normalized_code)
        batch.append(
            RawPromo(
                raw_code=raw_code,
                normalized_code=normalized_code,
                code_hash=hash_promo_code(normalized_code=normalized_code, pepper=pepper),
            )
        )
    return batch


async def _insert_batch(args: argparse.Namespace, batch: list[RawPromo]) -> None:
    valid_from = parse_utc_datetime(args.valid_from)
    valid_until = parse_utc_datetime(args.valid_until)
    now_utc = datetime.now(timezone.utc)

    async with SessionLocal.begin() as session:
        for item in batch:
            existing = await PromoRepo.get_code_by_hash(session, item.code_hash)
            if existing is not None:
                raise ValueError(f"promo code already exists: {item.raw_code}")

            promo_code = PromoCode(
                code_hash=item.code_hash,
                code_prefix=item.normalized_code[:8],
                campaign_name=args.campaign_name,
                promo_type=args.promo_type,
                grant_premium_days=args.grant_premium_days,
                discount_percent=args.discount_percent,
                target_scope=args.target_scope,
                status="ACTIVE",
                valid_from=valid_from,
                valid_until=valid_until,
                max_total_uses=args.max_total_uses,
                used_total=0,
                max_uses_per_user=1,
                new_users_only=args.new_users_only,
                first_purchase_only=args.first_purchase_only,
                created_by=args.created_by,
                created_at=now_utc,
                updated_at=now_utc,
            )
            session.add(promo_code)
            await session.flush()
            item.promo_code_id = promo_code.id


def _write_output(path: Path, batch: list[RawPromo]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["raw_code", "promo_code_id", "normalized_code"])
        for item in batch:
            writer.writerow([item.raw_code, item.promo_code_id or "", item.normalized_code])


async def _run() -> int:
    args = _parse_args()
    _validate_args(args)
    batch = await _build_batch(args)

    if not args.dry_run:
        await _insert_batch(args, batch)

    output_csv = args.output_csv or Path("reports/promo_batch_output.csv")
    _write_output(output_csv, batch)
    print(
        f"processed={len(batch)} inserted={0 if args.dry_run else len(batch)} output={output_csv}"  # noqa: T201
    )
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
