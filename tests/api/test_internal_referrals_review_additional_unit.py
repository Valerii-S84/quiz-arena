from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.api.routes.internal_referrals_review as review
from app.api.routes.internal_referrals_models import ReferralReviewActionRequest
from tests.api.test_internal_referrals_review_unit import _SessionLocal
from tests.type_helpers import build_request

UTC = timezone.utc


def _referral(**overrides: object) -> SimpleNamespace:
    now_utc = datetime.now(UTC)
    payload: dict[str, object] = {
        "id": 17,
        "referrer_user_id": 101,
        "referred_user_id": 202,
        "status": "STARTED",
        "fraud_score": Decimal("0"),
        "created_at": now_utc,
        "qualified_at": None,
        "rewarded_at": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _payload(decision: str, *, reason: str = "manual", expected: str | None = None):
    return ReferralReviewActionRequest(
        decision=decision,
        reason=reason,
        expected_current_status=expected,
    )


def _install_auth_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _assert_access(_request) -> None:
        return None

    monkeypatch.setattr(review, "_assert_ops_surface_access", _assert_access)


def _install_referral(monkeypatch: pytest.MonkeyPatch, referral: SimpleNamespace) -> None:
    session = object()
    monkeypatch.setattr(review, "SessionLocal", _SessionLocal(session))

    async def _get_by_id_for_update(_session, *, referral_id: int):
        assert _session is session
        assert referral_id == 17
        return referral

    monkeypatch.setattr(review.ReferralsRepo, "get_by_id_for_update", _get_by_id_for_update)


@pytest.mark.asyncio
async def test_reopen_started_case_is_idempotent_when_everything_is_already_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    referral = _referral(status="STARTED", fraud_score=Decimal("0"))
    logged: list[dict[str, object]] = []
    _install_auth_bypass(monkeypatch)
    _install_referral(monkeypatch, referral)
    monkeypatch.setattr(review.logger, "info", lambda event, **payload: logged.append(payload))

    response = await review.apply_referral_review_decision(
        referral_id=17,
        payload=_payload("REOPEN"),
        request=build_request(),
    )

    assert referral.status == "STARTED"
    assert response.idempotent_replay is True
    assert logged == []


@pytest.mark.asyncio
async def test_cancel_canceled_case_is_idempotent_when_fields_are_already_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    referral = _referral(status="CANCELED")
    _install_auth_bypass(monkeypatch)
    _install_referral(monkeypatch, referral)

    response = await review.apply_referral_review_decision(
        referral_id=17,
        payload=_payload("cancel"),
        request=build_request(),
    )

    assert referral.status == "CANCELED"
    assert response.idempotent_replay is True


@pytest.mark.asyncio
async def test_confirm_fraud_normalizes_reason_and_expected_status_before_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    referral = _referral(
        status="STARTED",
        fraud_score=Decimal("95"),
        qualified_at=None,
        rewarded_at=None,
    )
    logged: list[dict[str, object]] = []
    _install_auth_bypass(monkeypatch)
    _install_referral(monkeypatch, referral)
    monkeypatch.setattr(review.logger, "info", lambda event, **payload: logged.append(payload))

    response = await review.apply_referral_review_decision(
        referral_id=17,
        payload=_payload(" confirm_fraud ", reason="   ", expected=" started "),
        request=build_request(),
    )

    assert referral.status == "REJECTED_FRAUD"
    assert referral.fraud_score == Decimal("95")
    assert response.idempotent_replay is False
    assert logged[0]["reason"] is None
