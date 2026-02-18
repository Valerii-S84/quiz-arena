from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OfferTemplate:
    offer_code: str
    trigger_code: str
    priority: int
    text_key: str
    cta_product_codes: tuple[str, ...]
    blocking_modal: bool = True


@dataclass(frozen=True, slots=True)
class OfferSelection:
    impression_id: int
    offer_code: str
    trigger_code: str
    priority: int
    text_key: str
    cta_product_codes: tuple[str, ...]
    idempotent_replay: bool
