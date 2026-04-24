from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.db.models.quiz_sessions import QuizSession
from app.game.sessions.service import sessions_submit_daily
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc
NOW_UTC = datetime(2026, 4, 24, 8, 0, tzinfo=UTC)
BERLIN_DATE = date(2026, 4, 24)


class _Session(AsyncSessionStub):
    pass


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


@pytest.mark.asyncio
async def test_credit_daily_duel_ticket_is_idempotent_for_same_daily_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_purchases: list[SimpleNamespace] = []
    credited_purchase_ids: list[UUID] = []
    product = SimpleNamespace(product_code="FRIEND_CHALLENGE_5", stars_amount=5)
    purchase_store: dict[str, SimpleNamespace] = {}
    daily_run_id = uuid4()

    async def _fake_get_by_idempotency_key(_session, idempotency_key: str):
        return purchase_store.get(idempotency_key)

    def _fake_build_purchase(
        built_product,
        *,
        user_id: int,
        idempotency_key: str,
        discount_stars_amount: int,
        applied_promo_code_id,
        now_utc: datetime,
    ):
        del user_id, discount_stars_amount, applied_promo_code_id, now_utc
        purchase = SimpleNamespace(
            id=uuid4(),
            product_code=built_product.product_code,
            idempotency_key=idempotency_key,
            status="CREATED",
        )
        return purchase

    async def _fake_create(_session, *, purchase, created_at: datetime):
        del _session, created_at
        purchase_store[purchase.idempotency_key] = purchase
        created_purchases.append(purchase)
        return purchase

    async def _fake_apply_zero_cost_purchase(_session, *, purchase_id: UUID, user_id: int, now_utc):
        del _session, user_id, now_utc
        credited_purchase_ids.append(purchase_id)
        for purchase in purchase_store.values():
            if purchase.id == purchase_id and purchase.status != "CREDITED":
                purchase.status = "CREDITED"
                return SimpleNamespace(idempotent_replay=False)
        return SimpleNamespace(idempotent_replay=True)

    monkeypatch.setattr(sessions_submit_daily, "get_product", lambda _product_code: product)
    monkeypatch.setattr(
        sessions_submit_daily.PurchasesRepo,
        "get_by_idempotency_key",
        _fake_get_by_idempotency_key,
    )
    monkeypatch.setattr(sessions_submit_daily.PurchasesRepo, "create", _fake_create)
    monkeypatch.setattr(
        sessions_submit_daily,
        "_get_purchase_service",
        lambda: SimpleNamespace(
            _build_purchase=_fake_build_purchase,
            apply_zero_cost_purchase=_fake_apply_zero_cost_purchase,
        ),
    )

    await sessions_submit_daily._credit_daily_duel_ticket(
        _Session(),
        user_id=11,
        daily_run_id=daily_run_id,
        now_utc=NOW_UTC,
    )
    await sessions_submit_daily._credit_daily_duel_ticket(
        _Session(),
        user_id=11,
        daily_run_id=daily_run_id,
        now_utc=NOW_UTC,
    )

    assert len(created_purchases) == 1
    assert len({purchase.id for purchase in created_purchases}) == 1
    assert len(credited_purchase_ids) == 2
    assert len(set(credited_purchase_ids)) == 1


def test_get_purchase_service_imports_purchase_service_lazily() -> None:
    from app.economy.purchases.service import PurchaseService

    assert sessions_submit_daily._get_purchase_service() is PurchaseService


@pytest.mark.asyncio
async def test_credit_daily_duel_ticket_propagates_purchase_service_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_import_error():
        raise ImportError("purchase service unavailable")

    monkeypatch.setattr(sessions_submit_daily, "_get_purchase_service", _raise_import_error)

    with pytest.raises(ImportError, match="purchase service unavailable"):
        await sessions_submit_daily._credit_daily_duel_ticket(
            _Session(),
            user_id=11,
            daily_run_id=uuid4(),
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_correct", "initial_score", "expected_score"),
    [
        (True, 6, 7),
        (True, 5, 6),
        (True, 4, 5),
        (False, 4, 4),
    ],
)
async def test_apply_daily_answer_completes_with_expected_reward_score_and_preserves_streak_flow(
    monkeypatch: pytest.MonkeyPatch,
    is_correct: bool,
    initial_score: int,
    expected_score: int,
) -> None:
    reward_calls: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    quiz_session = cast(QuizSession, SimpleNamespace(daily_run_id=uuid4()))
    run = SimpleNamespace(
        id=quiz_session.daily_run_id,
        berlin_date=BERLIN_DATE,
        current_question=6,
        score=initial_score,
        status="IN_PROGRESS",
        completed_at=None,
    )

    async def _fake_apply_reward(*_args, **kwargs) -> None:
        reward_calls.append(kwargs)

    async def _fake_record_activity(*_args, **_kwargs):
        return SimpleNamespace(current_streak=6, best_streak=8)

    async def _fake_emit_analytics_event(*_args, **kwargs) -> None:
        events.append(kwargs)

    monkeypatch.setattr(
        sessions_submit_daily.DailyRunsRepo,
        "get_by_id_for_update",
        _async_return(run),
    )
    monkeypatch.setattr(
        sessions_submit_daily,
        "_apply_daily_completion_reward",
        _fake_apply_reward,
    )
    monkeypatch.setattr(
        sessions_submit_daily.StreakService,
        "record_activity",
        _fake_record_activity,
    )
    monkeypatch.setattr(
        sessions_submit_daily,
        "emit_analytics_event",
        _fake_emit_analytics_event,
    )

    state = await sessions_submit_daily.apply_daily_answer(
        _Session(),
        user_id=11,
        quiz_session=quiz_session,
        is_correct=is_correct,
        now_utc=NOW_UTC,
    )

    assert reward_calls == [
        {
            "user_id": 11,
            "daily_run_id": run.id,
            "score": expected_score,
            "now_utc": NOW_UTC,
        }
    ]
    assert state.completed is True
    assert state.current_question == 7
    assert state.score == expected_score
    assert state.current_streak == 6
    assert state.best_streak == 8
    assert run.status == "COMPLETED"
    assert run.completed_at == NOW_UTC
    payload = cast(dict[str, object], events[0]["payload"])
    assert payload["score"] == expected_score


@pytest.mark.asyncio
async def test_apply_daily_answer_does_not_repeat_reward_for_already_completed_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quiz_session = cast(QuizSession, SimpleNamespace(daily_run_id=uuid4()))
    run = SimpleNamespace(
        id=quiz_session.daily_run_id,
        berlin_date=BERLIN_DATE,
        current_question=7,
        score=6,
        status="COMPLETED",
        completed_at=NOW_UTC,
    )

    async def _unexpected_apply_reward(*_args, **_kwargs) -> None:
        pytest.fail("reward should not be re-applied for completed daily runs")

    async def _unexpected_record_activity(*_args, **_kwargs):
        pytest.fail("streak activity should not be re-recorded for completed daily runs")

    async def _fake_sync_rollover(*_args, **_kwargs):
        return SimpleNamespace(current_streak=3, best_streak=5)

    monkeypatch.setattr(
        sessions_submit_daily.DailyRunsRepo,
        "get_by_id_for_update",
        _async_return(run),
    )
    monkeypatch.setattr(
        sessions_submit_daily,
        "_apply_daily_completion_reward",
        _unexpected_apply_reward,
    )
    monkeypatch.setattr(
        sessions_submit_daily.StreakService,
        "record_activity",
        _unexpected_record_activity,
    )
    monkeypatch.setattr(
        sessions_submit_daily.StreakService,
        "sync_rollover",
        _fake_sync_rollover,
    )

    state = await sessions_submit_daily.apply_daily_answer(
        _Session(),
        user_id=11,
        quiz_session=quiz_session,
        is_correct=True,
        now_utc=NOW_UTC,
    )

    assert state.daily_run_id == run.id
    assert state.current_question == 7
    assert state.score == 6
    assert state.completed is True
    assert state.current_streak == 3
    assert state.best_streak == 5
    assert run.status == "COMPLETED"


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
