from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.services.messaging_repair_models import ExistingDeliveryOutcome, RepairTarget
from app.services.messaging_repair_plan_builder import build_messaging_repair_plan
from app.services.messaging_repair_queries import load_tournament_expected_targets
from app.services.telegram_delivery_types import FAILURE_CODE_TRANSIENT, TelegramDeliveryFailure
from app.workers.tasks import daily_cup_messaging_delivery_runtime as daily_runtime
from app.workers.tasks import daily_cup_messaging_delivery_steps as daily_steps
from app.workers.tasks import messaging_fallback_delivery
from app.workers.tasks import tournaments_messaging_delivery_steps as private_steps
from app.workers.tasks.daily_cup_messaging_delivery_steps import (
    DailyCupDeliveryRun,
    DailyCupUserDelivery,
)
from app.workers.tasks.daily_cup_messaging_delivery_types import DailyCupDeliveryState
from app.workers.tasks.tournaments_messaging_delivery_types import (
    TournamentRoundDeliveryState,
    TournamentRoundMessageAttempt,
)

NOW_UTC = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_daily_edit_persistence_failure_does_not_send_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fallback_calls: list[object] = []

    class _Bot:
        async def edit_message_text(self, **_kwargs: Any) -> None:
            return None

    async def _mark_sent(**_kwargs: Any) -> None:
        raise RuntimeError("sent persistence failed")

    async def _fallback(*_args: Any, **_kwargs: Any) -> None:
        fallback_calls.append(object())

    monkeypatch.setattr(daily_runtime, "send_fallback_message", _fallback)
    delivery = DailyCupUserDelivery(
        user_id=1,
        chat_id=101,
        existing_message_id=501,
        target=SimpleNamespace(idempotency_key="original"),
        text="round",
        keyboard=None,
    )

    with pytest.raises(RuntimeError, match="sent persistence failed"):
        await daily_runtime._edit_existing_message(
            cast(Any, SimpleNamespace(bot=_Bot())),
            cast(
                Any,
                SimpleNamespace(
                    mark_telegram_delivery_sent=_mark_sent,
                    is_message_not_modified_error=lambda _exc: False,
                ),
            ),
            DailyCupDeliveryState(),
            _run(),
            delivery,
        )

    assert fallback_calls == []


@pytest.mark.asyncio
async def test_daily_payload_failure_happens_before_pending_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_order: list[str] = []

    def _payload(**_kwargs: Any) -> tuple[str, object]:
        call_order.append("payload")
        raise RuntimeError("payload failed")

    async def _prepare(**_kwargs: Any) -> object:
        call_order.append("prepare")
        return SimpleNamespace(should_send=False)

    monkeypatch.setattr(daily_runtime, "build_daily_cup_message_payload", _payload)
    monkeypatch.setattr(
        daily_runtime,
        "build_delivery_target",
        lambda **_kwargs: SimpleNamespace(idempotency_key="delivery"),
    )
    with pytest.raises(RuntimeError, match="payload failed"):
        await daily_runtime._deliver_to_user(
            cast(
                Any,
                SimpleNamespace(
                    telegram_targets={1: 101},
                    participant_rows={1: SimpleNamespace(standings_message_id=None)},
                ),
            ),
            cast(Any, SimpleNamespace(prepare_telegram_delivery=_prepare)),
            DailyCupDeliveryState(),
            _run(),
            1,
        )

    assert call_order == ["payload"]


def test_failed_repair_requires_explicit_pending_replay_safety() -> None:
    target = RepairTarget(target_type="user", target_id="1")

    def _plan(pending_replay_safe: bool):
        return build_messaging_repair_plan(
            flow="daily_cup_round_messaging",
            correlation_id="cup-1",
            expected_targets=[target],
            existing_attempts=[
                ExistingDeliveryOutcome(
                    target_type="user",
                    target_id="1",
                    status="FAILED",
                    failure_code=FAILURE_CODE_TRANSIENT,
                    pending_replay_safe=pending_replay_safe,
                )
            ],
        )

    assert _plan(False).safe_replay_candidates == []
    assert _plan(True).safe_replay_candidates == [target]


def test_inactive_daily_failed_attempt_is_not_reintroduced_for_replay() -> None:
    inactive_failed = ExistingDeliveryOutcome(
        target_type="user",
        target_id="2:phase:round:2:status:round_2:edit:502",
        status="FAILED",
        failure_code=FAILURE_CODE_TRANSIENT,
        pending_replay_safe=True,
    )

    daily_plan = build_messaging_repair_plan(
        flow="daily_cup_round_messaging",
        correlation_id="cup-1",
        expected_targets=[],
        existing_attempts=[inactive_failed],
    )
    private_plan = build_messaging_repair_plan(
        flow="private_tournament_round_messaging",
        correlation_id="private-1",
        expected_targets=[],
        existing_attempts=[inactive_failed],
    )

    assert daily_plan.safe_replay_candidates == []
    assert private_plan.safe_replay_candidates == [
        RepairTarget(target_type="user", target_id=inactive_failed.target_id)
    ]


@pytest.mark.asyncio
async def test_daily_repair_targets_use_active_user_filter() -> None:
    session = _CaptureSession()

    await load_tournament_expected_targets(
        cast(Any, session),
        flow="daily_cup_round_messaging",
        tournament_id="cup-1",
    )

    assert "u.status = 'ACTIVE'" in session.statement
    assert ":flow <> 'daily_cup_round_messaging'" in session.statement
    assert session.params == {
        "flow": "daily_cup_round_messaging",
        "tournament_id": "cup-1",
    }


@pytest.mark.asyncio
async def test_fallback_failure_terminal_writes_roll_back_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"fallback": "PENDING", "original": "PENDING"}
    session_local = _RollbackSessionLocal(state)
    sessions: list[object] = []
    failure = TelegramDeliveryFailure(
        failure_code=FAILURE_CODE_TRANSIENT,
        failure_reason="telegram unavailable",
        telegram_error_code=None,
        is_blocked_candidate=False,
    )

    async def _fallback_failed(**kwargs: Any) -> TelegramDeliveryFailure:
        sessions.append(kwargs["session"])
        state["fallback"] = "FAILED"
        return failure

    async def _original_failed(**kwargs: Any) -> None:
        sessions.append(kwargs["session"])
        state["original"] = "FAILED"
        raise RuntimeError("failure between terminal writes")

    monkeypatch.setattr(
        messaging_fallback_delivery,
        "mark_telegram_delivery_failed",
        _fallback_failed,
    )
    monkeypatch.setattr(
        messaging_fallback_delivery,
        "mark_telegram_delivery_failed_with_classification",
        _original_failed,
    )

    with pytest.raises(RuntimeError, match="failure between terminal writes"):
        await messaging_fallback_delivery.mark_fallback_and_original_edit_failed(
            fallback_idempotency_key="fallback",
            original_idempotency_key="original",
            happened_at=NOW_UTC,
            exc=RuntimeError("telegram unavailable"),
            session_local=session_local,
        )

    assert state == {"fallback": "PENDING", "original": "PENDING"}
    assert sessions == [session_local.session, session_local.session]


@pytest.mark.asyncio
async def test_both_fallback_flows_use_atomic_failure_operation() -> None:
    calls: list[tuple[str, str]] = []

    async def _atomic(**kwargs: Any) -> None:
        calls.append((kwargs["fallback_idempotency_key"], kwargs["original_idempotency_key"]))

    daily_state = DailyCupDeliveryState()
    await daily_steps._record_fallback_failure(
        dependencies=cast(
            Any,
            SimpleNamespace(
                fallback_delivery=SimpleNamespace(mark_fallback_and_original_edit_failed=_atomic)
            ),
        ),
        state=daily_state,
        run=_run(),
        delivery=_delivery("daily-original"),
        fallback_target=SimpleNamespace(idempotency_key="daily-fallback"),
        exc=RuntimeError("telegram unavailable"),
    )
    await private_steps._send_fallback_round_message(
        delivery_context=cast(Any, _private_context(_atomic)),
        state=TournamentRoundDeliveryState(),
        attempt=TournamentRoundMessageAttempt(
            user_id=2,
            chat_id=202,
            existing_message_id=502,
            target=SimpleNamespace(idempotency_key="private-original"),
            text="round",
            keyboard=None,
        ),
    )

    assert calls == [
        ("daily-fallback", "daily-original"),
        ("private-fallback", "private-original"),
    ]
    assert daily_state.failed == 1


def _run() -> DailyCupDeliveryRun:
    return DailyCupDeliveryRun(
        rounds_total=3,
        happened_at=NOW_UTC,
        task_name="daily",
        content_version="v1",
    )


def _delivery(idempotency_key: str) -> DailyCupUserDelivery:
    return DailyCupUserDelivery(
        user_id=1,
        chat_id=101,
        existing_message_id=501,
        target=SimpleNamespace(idempotency_key=idempotency_key),
        text="round",
        keyboard=None,
    )


def _private_context(atomic_operation: Any) -> object:
    class _Bot:
        async def send_message(self, **_kwargs: Any) -> object:
            raise RuntimeError("telegram unavailable")

    async def _prepare(**_kwargs: Any) -> object:
        return SimpleNamespace(should_send=True)

    async def _begin(*_args: Any, **_kwargs: Any) -> None:
        return None

    operations = SimpleNamespace(
        build_target=lambda **_kwargs: SimpleNamespace(idempotency_key="private-fallback"),
        fallback_delivery_operation=lambda _message_id: "fallback",
        prepare_fallback_delivery=_prepare,
        begin_fallback_dispatch=_begin,
        mark_fallback_and_original_failed=atomic_operation,
    )
    return SimpleNamespace(
        operations=operations,
        request=SimpleNamespace(context=SimpleNamespace(parsed_tournament_id="private-1")),
        bot=_Bot(),
        happened_at=NOW_UTC,
    )


class _Rows:
    @staticmethod
    def all() -> list[tuple[object, ...]]:
        return []


class _CaptureSession:
    statement = ""
    params: dict[str, object] = {}

    async def execute(self, statement: object, params: dict[str, object]) -> _Rows:
        self.statement = str(statement)
        self.params = params
        return _Rows()


class _RollbackContext:
    def __init__(self, owner: _RollbackSessionLocal) -> None:
        self.owner = owner
        self.snapshot: dict[str, str] = {}

    async def __aenter__(self) -> object:
        self.snapshot = dict(self.owner.state)
        return self.owner.session

    async def __aexit__(self, exc_type: object, _exc: object, _tb: object) -> bool:
        if exc_type is not None:
            self.owner.state.clear()
            self.owner.state.update(self.snapshot)
        return False


class _RollbackSessionLocal:
    def __init__(self, state: dict[str, str]) -> None:
        self.state = state
        self.session = object()

    def begin(self) -> _RollbackContext:
        return _RollbackContext(self)
