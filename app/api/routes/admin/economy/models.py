from __future__ import annotations

from pydantic import BaseModel


class PurchasesResponse(BaseModel):
    items: list[dict[str, object]]
    total: int
    page: int
    pages: int
    charts: dict[str, list[dict[str, object]]]


class SubscriptionsResponse(BaseModel):
    items: list[dict[str, object]]
    total: int


class CohortsResponse(BaseModel):
    week_offsets: list[int]
    cohorts: list[dict[str, object]]
