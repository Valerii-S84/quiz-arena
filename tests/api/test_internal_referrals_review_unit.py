from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api.routes.internal_referrals_review as review
from app.api.routes.internal_referrals_models import ReferralReviewActionRequest
from app.economy.referrals.constants import FRAUD_SCORE_VELOCITY
from tests.type_helpers import AsyncBeginContext, build_request


class _SessionLocal:
    def __init__(self, session: object) -> None:
        self._session = session

    def begin(self) -> AsyncBeginContext[object]:
        return AsyncBeginContext(self._session)


def _referral(**overrides: object) -> SimpleNamespace:
    now_utc = datetime.now(timezone.utc)
    payload: dict[str, object] = {
        "id": 17,
        "referrer_user_id": 101,
        "referred_user_id": 202,
        "status": "STARTED",
        "fraud_score": Decimal("0"),
        "created_at": now_utc,
        "qualified_at": now_utc,
        "rewarded_at": now_utc,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _payload(
    decision: str,
    *,
    expected_current_status: str | None = None,
) -> ReferralReviewActionRequest:
    return ReferralReviewActionRequest(
        decision=decision,
        reason="manual review",
        expected_current_status=expected_current_status,
    )


def _install_auth_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _assert_access(_request) -> None:
        return None

    monkeypatch.setattr(review, "_assert_ops_surface_access", _assert_access)


def _install_referral(monkeypatch: pytest.MonkeyPatch, referral: SimpleNamespace | None) -> None:
    session = object()
    monkeypatch.setattr(review, "SessionLocal", _SessionLocal(session))

    async def _get_by_id_for_update(_session, *, referral_id: int):
        assert _session is session
        assert referral_id == 17
        return referral

    monkeypatch.setattr(review.ReferralsRepo, "get_by_id_for_update", _get_by_id_for_update)


@pytest.mark.asyncio
async def test_confirm_fraud_updates_status_score_and_clears_reward_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    referral = _referral(fraud_score=Decimal("5.00"))
    logged: list[dict[str, object]] = []
    _install_auth_bypass(monkeypatch)
    _install_referral(monkeypatch, referral)
    monkeypatch.setattr(
        review.logger,
        "info",
        lambda event, **payload: logged.append({"event": event, **payload}),
    )

    response = await review.apply_referral_review_decision(
        referral_id=17,
        payload=_payload("confirm_fraud", expected_current_status="started"),
        request=build_request(),
    )

    assert referral.status == "REJECTED_FRAUD"
    assert referral.fraud_score == FRAUD_SCORE_VELOCITY
    assert referral.qualified_at is None
    assert referral.rewarded_at is None
    assert response.referral.status == "REJECTED_FRAUD"
    assert response.idempotent_replay is False
    assert logged[0]["event"] == "internal_referral_review_decision_applied"
    assert logged[0]["previous_status"] == "STARTED"


@pytest.mark.asyncio
async def test_confirm_fraud_rejected_case_is_idempotent_when_no_fields_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    referral = _referral(
        status="REJECTED_FRAUD",
        fraud_score=FRAUD_SCORE_VELOCITY,
        qualified_at=None,
        rewarded_at=None,
    )
    logged: list[dict[str, object]] = []
    _install_auth_bypass(monkeypatch)
    _install_referral(monkeypatch, referral)
    monkeypatch.setattr(
        review.logger,
        "info",
        lambda event, **payload: logged.append({"event": event, **payload}),
    )

    response = await review.apply_referral_review_decision(
        referral_id=17,
        payload=_payload("CONFIRM_FRAUD"),
        request=build_request(),
    )

    assert referral.status == "REJECTED_FRAUD"
    assert response.idempotent_replay is True
    assert logged == []


@pytest.mark.asyncio
async def test_reopen_resets_status_score_and_reward_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    referral = _referral(status="REJECTED_FRAUD", fraud_score=FRAUD_SCORE_VELOCITY)
    _install_auth_bypass(monkeypatch)
    _install_referral(monkeypatch, referral)

    response = await review.apply_referral_review_decision(
        referral_id=17,
        payload=_payload("REOPEN"),
        request=build_request(),
    )

    assert referral.status == "STARTED"
    assert referral.fraud_score == Decimal("0")
    assert referral.qualified_at is None
    assert referral.rewarded_at is None
    assert response.referral.status == "STARTED"
    assert response.idempotent_replay is False


@pytest.mark.asyncio
async def test_cancel_started_case_clears_reward_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    referral = _referral()
    _install_auth_bypass(monkeypatch)
    _install_referral(monkeypatch, referral)

    response = await review.apply_referral_review_decision(
        referral_id=17,
        payload=_payload("CANCEL"),
        request=build_request(),
    )

    assert referral.status == "CANCELED"
    assert referral.qualified_at is None
    assert referral.rewarded_at is None
    assert response.referral.status == "CANCELED"
    assert response.idempotent_replay is False


@pytest.mark.asyncio
async def test_invalid_decision_is_rejected_before_loading_referral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_auth_bypass(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        await review.apply_referral_review_decision(
            referral_id=17,
            payload=_payload("APPROVE"),
            request=build_request(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == {"code": "E_REFERRAL_REVIEW_DECISION_INVALID"}


@pytest.mark.asyncio
async def test_invalid_expected_status_is_rejected_before_loading_referral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_auth_bypass(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        await review.apply_referral_review_decision(
            referral_id=17,
            payload=_payload("CANCEL", expected_current_status="missing"),
            request=build_request(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == {"code": "E_REFERRAL_STATUS_INVALID"}


@pytest.mark.asyncio
async def test_missing_referral_maps_to_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_auth_bypass(monkeypatch)
    _install_referral(monkeypatch, None)

    with pytest.raises(HTTPException) as exc_info:
        await review.apply_referral_review_decision(
            referral_id=17,
            payload=_payload("CANCEL"),
            request=build_request(),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {"code": "E_REFERRAL_NOT_FOUND"}


@pytest.mark.asyncio
async def test_expected_status_mismatch_maps_to_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_auth_bypass(monkeypatch)
    _install_referral(monkeypatch, _referral(status="STARTED"))

    with pytest.raises(HTTPException) as exc_info:
        await review.apply_referral_review_decision(
            referral_id=17,
            payload=_payload("CANCEL", expected_current_status="REJECTED_FRAUD"),
            request=build_request(),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "E_REFERRAL_STATUS_CONFLICT"}


@pytest.mark.asyncio
async def test_decision_status_conflict_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_auth_bypass(monkeypatch)
    _install_referral(monkeypatch, _referral(status="QUALIFIED"))

    with pytest.raises(HTTPException) as exc_info:
        await review.apply_referral_review_decision(
            referral_id=17,
            payload=_payload("CONFIRM_FRAUD"),
            request=build_request(),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "E_REFERRAL_REVIEW_DECISION_CONFLICT"}


@pytest.mark.parametrize(
    ("current_status", "decision"),
    [
        ("QUALIFIED", "REOPEN"),
        ("REWARDED", "CANCEL"),
        ("STARTED", "UNKNOWN"),
    ],
)
def test_resolve_next_status_rejects_unsupported_transitions(
    current_status: str,
    decision: str,
) -> None:
    assert review._resolve_next_status(current_status=current_status, decision=decision) is None
