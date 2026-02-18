from __future__ import annotations

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.db.models import (  # noqa: F401
    EnergyState,
    Entitlement,
    LedgerEntry,
    ModeAccess,
    OfferImpression,
    OutboxEvent,
    ProcessedUpdate,
    PromoAttempt,
    PromoCode,
    PromoCodeBatch,
    PromoRedemption,
    Purchase,
    QuizAttempt,
    QuizSession,
    ReconciliationRun,
    Referral,
    StreakState,
    User,
)
from app.db.models.base import Base


def test_all_m2_tables_registered() -> None:
    expected_tables = {
        "users",
        "energy_state",
        "streak_state",
        "purchases",
        "ledger_entries",
        "entitlements",
        "mode_access",
        "quiz_sessions",
        "quiz_attempts",
        "offers_impressions",
        "promo_codes",
        "promo_redemptions",
        "promo_attempts",
        "referrals",
        "processed_updates",
        "outbox_events",
        "reconciliation_runs",
        "promo_code_batches",
    }
    assert expected_tables.issubset(set(Base.metadata.tables))


def test_critical_constraints_present() -> None:
    purchases = Base.metadata.tables["purchases"]
    purchase_check_names = {
        constraint.name for constraint in purchases.constraints if isinstance(constraint, CheckConstraint)
    }
    assert "ck_purchases_final_amount" in purchase_check_names
    purchase_index_names = {index.name for index in purchases.indexes}
    assert "uq_purchases_active_invoice_user_product" in purchase_index_names

    entitlements = Base.metadata.tables["entitlements"]
    entitlements_indexes = {index.name for index in entitlements.indexes}
    assert "uq_entitlements_active_premium_per_user" in entitlements_indexes

    promo_redemptions = Base.metadata.tables["promo_redemptions"]
    promo_unique_constraints = {
        constraint.name
        for constraint in promo_redemptions.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert "uq_promo_redemptions_code_user" in promo_unique_constraints
