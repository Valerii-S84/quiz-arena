from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(slots=True)
class PurchaseInitResult:
    purchase_id: UUID
    invoice_payload: str
    product_code: str
    final_stars_amount: int
    idempotent_replay: bool


@dataclass(slots=True)
class PurchaseCreditResult:
    purchase_id: UUID
    product_code: str
    status: str
    idempotent_replay: bool
