from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.workers.tasks import daily_cup_winner_reward_grants as grants


class _NestedSession:
    def begin_nested(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb


def test_grant_daily_cup_rank_reward_covers_rank_rewards(monkeypatch) -> None:
    tournament_id = uuid4()
    calls: list[tuple[str, object]] = []

    async def _missing(_session, _key):
        return None

    async def _grant_premium(_session, **kwargs):
        calls.append(("premium", kwargs["user_id"]))

    async def _purchase_missing(_session, _key):
        return None

    async def _create(_session, **kwargs):
        calls.append(("create", kwargs["purchase"].id))

    async def _apply(_session, **kwargs):
        calls.append(("apply", kwargs["purchase_id"]))

    async def _energy(_session, **kwargs):
        calls.append(("energy", kwargs["amount"]))
        return SimpleNamespace(amount=5)

    monkeypatch.setattr(grants.LedgerRepo, "get_by_idempotency_key", _missing)
    monkeypatch.setattr(grants, "grant_premium_days", _grant_premium)
    monkeypatch.setattr(grants, "get_product", lambda _code: SimpleNamespace(stars_amount=12))
    monkeypatch.setattr(grants.PurchasesRepo, "get_by_idempotency_key", _purchase_missing)
    monkeypatch.setattr(
        grants.PurchaseService,
        "_build_purchase",
        lambda *_args, **_kwargs: SimpleNamespace(id=uuid4()),
    )
    monkeypatch.setattr(grants.PurchasesRepo, "create", _create)
    monkeypatch.setattr(grants.PurchaseService, "apply_zero_cost_purchase", _apply)
    monkeypatch.setattr(grants.EnergyService, "credit_paid_energy", _energy)

    for rank in (1, 2, 3):
        assert asyncio.run(
            grants.grant_daily_cup_rank_reward(
                session=_NestedSession(),
                tournament_id=tournament_id,
                user_id=rank,
                rank=rank,
                now_utc=datetime.now(timezone.utc),
                logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
            )
        )

    assert ("premium", 1) in calls
    assert len([call for call in calls if call[0] == "apply"]) == 2
    assert ("energy", grants.DAILY_CUP_FREE_ENERGY_REWARD) in calls


def test_grant_daily_cup_rank_reward_logs_product_errors(monkeypatch) -> None:
    warnings: list[dict[str, object]] = []
    monkeypatch.setattr(grants, "get_product", lambda _code: None)

    result = asyncio.run(
        grants.grant_daily_cup_rank_reward(
            session=_NestedSession(),
            tournament_id=uuid4(),
            user_id=2,
            rank=2,
            now_utc=datetime.now(timezone.utc),
            logger=SimpleNamespace(
                warning=lambda event, **kwargs: warnings.append({"event": event, **kwargs})
            ),
        )
    )

    assert result is False
    assert warnings[0]["event"] == "daily_cup_winner_reward_grant_failed"
    assert warnings[0]["error_type"] == "ValueError"
