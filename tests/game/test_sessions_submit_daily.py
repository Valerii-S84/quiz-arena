from __future__ import annotations

from tests.game.sessions_submit_daily_support import (
    NOW_UTC,
    SimpleNamespace,
    _async_return,
    _Session,
    datetime,
    pytest,
    sessions_submit_daily,
    uuid4,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("score", "expected_energy"),
    [
        (7, None),
        (6, 3),
        (5, 2),
        (4, None),
    ],
)
async def test_apply_daily_completion_reward_uses_expected_thresholds(
    monkeypatch: pytest.MonkeyPatch,
    score: int,
    expected_energy: int | None,
) -> None:
    ticket_calls: list[dict[str, object]] = []
    energy_calls: list[dict[str, object]] = []
    daily_run_id = uuid4()

    async def _fake_credit_ticket(*_args, **kwargs) -> None:
        ticket_calls.append(kwargs)

    async def _fake_credit_free_energy(*_args, **kwargs) -> None:
        energy_calls.append(kwargs)

    monkeypatch.setattr(sessions_submit_daily, "_credit_daily_duel_ticket", _fake_credit_ticket)
    monkeypatch.setattr(
        sessions_submit_daily.EnergyService,
        "credit_free_energy",
        _fake_credit_free_energy,
    )

    await sessions_submit_daily._apply_daily_completion_reward(
        _Session(),
        user_id=11,
        daily_run_id=daily_run_id,
        score=score,
        now_utc=NOW_UTC,
    )

    if score >= 7:
        assert ticket_calls == [
            {
                "user_id": 11,
                "daily_run_id": daily_run_id,
                "now_utc": NOW_UTC,
            }
        ]
        assert energy_calls == []
        return

    assert ticket_calls == []
    if expected_energy is None:
        assert energy_calls == []
    else:
        assert energy_calls == [
            {
                "user_id": 11,
                "amount": expected_energy,
                "idempotency_key": f"daily:reward:energy:{daily_run_id}",
                "now_utc": NOW_UTC,
                "source": "DAILY_CHALLENGE",
            }
        ]


@pytest.mark.asyncio
async def test_credit_daily_duel_ticket_uses_zero_cost_purchase_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_purchases: list[SimpleNamespace] = []
    zero_cost_calls: list[dict[str, object]] = []
    product = SimpleNamespace(product_code="FRIEND_CHALLENGE_5", stars_amount=5)
    purchase = SimpleNamespace(id=uuid4())
    daily_run_id = uuid4()

    monkeypatch.setattr(
        sessions_submit_daily.PurchasesRepo,
        "get_by_idempotency_key",
        _async_return(None),
    )
    monkeypatch.setattr(
        sessions_submit_daily,
        "get_product",
        lambda product_code: product if product_code == "FRIEND_CHALLENGE_5" else None,
    )

    def _fake_build_purchase(
        built_product,
        *,
        user_id: int,
        idempotency_key: str,
        discount_stars_amount: int,
        applied_promo_code_id,
        now_utc: datetime,
    ):
        assert built_product is product
        assert user_id == 11
        assert idempotency_key == f"daily:reward:ticket:{daily_run_id}"
        assert discount_stars_amount == 5
        assert applied_promo_code_id is None
        assert now_utc == NOW_UTC
        return purchase

    async def _fake_create(*_args, **kwargs):
        created_purchases.append(kwargs["purchase"])
        return kwargs["purchase"]

    async def _fake_apply_zero_cost_purchase(*_args, **kwargs):
        zero_cost_calls.append(kwargs)

    purchase_service = SimpleNamespace(
        _build_purchase=_fake_build_purchase,
        apply_zero_cost_purchase=_fake_apply_zero_cost_purchase,
    )

    monkeypatch.setattr(sessions_submit_daily, "_get_purchase_service", lambda: purchase_service)
    monkeypatch.setattr(sessions_submit_daily.PurchasesRepo, "create", _fake_create)

    await sessions_submit_daily._credit_daily_duel_ticket(
        _Session(),
        user_id=11,
        daily_run_id=daily_run_id,
        now_utc=NOW_UTC,
    )

    assert created_purchases == [purchase]
    assert zero_cost_calls == [
        {
            "purchase_id": purchase.id,
            "user_id": 11,
            "now_utc": NOW_UTC,
        }
    ]
