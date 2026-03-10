from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO

from fastapi.responses import StreamingResponse

from app.db.repo.promo_repo_admin_runtime import AdminRuntimePromoRepo
from app.db.session import SessionLocal
from app.economy.purchases.catalog import PRODUCTS, get_product, is_product_available_for_sale

from .promo_models import OPEN_ENDED_VALID_UNTIL, serialize_promo


async def list_promo_products() -> dict[str, object]:
    items = []
    for product_code, spec in PRODUCTS.items():
        if not is_product_available_for_sale(product_code):
            continue
        product = get_product(product_code)
        if product is None:
            continue
        items.append(
            {
                "id": product.product_code,
                "title": product.title,
                "product_type": product.product_type,
                "stars_amount": product.stars_amount,
            }
        )
    items.sort(key=lambda item: (str(item["product_type"]), str(item["title"])))
    return {"items": items}


async def export_promos() -> StreamingResponse:
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        rows = await AdminRuntimePromoRepo.list_codes(
            session,
            status=None,
            query=None,
            page=1,
            limit=10_000,
            now_utc=now_utc,
        )

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["code", "campaign_name", "discount_type", "discount_value", "valid_until"])
    for row in rows:
        serialized = serialize_promo(row, now_utc=now_utc)
        writer.writerow(
            [
                serialized["code"],
                serialized["campaign_name"],
                serialized["discount_type"],
                serialized["discount_value"] or "",
                "" if row.valid_until >= OPEN_ENDED_VALID_UNTIL else serialized["valid_until"],
            ]
        )

    headers = {"Content-Disposition": 'attachment; filename="promo_codes.csv"'}
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers=headers)
