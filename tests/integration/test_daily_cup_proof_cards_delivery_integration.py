from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.bot.texts.de import TEXTS_DE
from app.db.models.energy_state import EnergyState
from app.db.models.entitlements import Entitlement
from app.db.models.ledger_entries import LedgerEntry
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.session import SessionLocal
from app.workers.tasks import daily_cup_proof_cards
from tests.integration.daily_cup_proof_cards_test_support import (
    create_completed_daily_cup,
    create_completed_daily_cup_with_bye_seeded_scores,
    create_daily_cup_users,
    ensure_tournament_schema,
    fixed_daily_cup_now,
    install_recording_worker_bot,
    set_user_active_premium,
    set_user_free_energy,
)

UTC = timezone.utc


class _FrozenDateTime(datetime):
    current = datetime(2026, 4, 24, 10, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        if tz is None:
            return cls.current.replace(tzinfo=None)
        return cls.current.astimezone(tz)


async def _get_active_premium(*, user_id: int) -> Entitlement | None:
    async with SessionLocal.begin() as session:
        return await session.scalar(
            select(Entitlement).where(
                Entitlement.user_id == user_id,
                Entitlement.entitlement_type == "PREMIUM",
                Entitlement.status == "ACTIVE",
            )
        )


async def _get_free_energy(*, user_id: int) -> int | None:
    async with SessionLocal.begin() as session:
        state = await session.get(EnergyState, user_id)
        return None if state is None else int(state.free_energy)


async def _get_energy_balance(*, user_id: int) -> tuple[int, int] | None:
    async with SessionLocal.begin() as session:
        state = await session.get(EnergyState, user_id)
        if state is None:
            return None
        return int(state.free_energy), int(state.paid_energy)


async def _count_ledger_entries(*, idempotency_key: str) -> int:
    async with SessionLocal.begin() as session:
        return int(
            await session.scalar(
                select(func.count(LedgerEntry.id)).where(
                    LedgerEntry.idempotency_key == idempotency_key
                )
            )
            or 0
        )


@pytest.mark.asyncio
async def test_daily_cup_proof_cards_send_only_once_per_participant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = fixed_daily_cup_now()
    await ensure_tournament_schema()

    user_ids = await create_daily_cup_users(prefix="daily_cup_proof", count=4)
    tournament_id = await create_completed_daily_cup(now_utc=now_utc, user_ids=user_ids)
    bot, render_calls = install_recording_worker_bot(monkeypatch, record_renders=True)

    first = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        initial_delay_seconds=0,
    )
    assert int(first["sent"]) == 4
    assert int(first["cached_reused"]) == 0
    assert int(first["failed"]) == 0
    assert all(not isinstance(item["photo"], str) for item in bot.send_photos)
    assert [str(item.get("caption")) for item in bot.send_photos[:4]] == [
        "🏆 Daily Arena Cup\nPlatz #1\nPunkte: 4\n📱 https://t.me/Deine_Deutsch_Quiz_bot",
        "🏆 Daily Arena Cup\nPlatz #2\nPunkte: 3\n📱 https://t.me/Deine_Deutsch_Quiz_bot",
        "🏆 Daily Arena Cup\nPlatz #3\nPunkte: 2\n📱 https://t.me/Deine_Deutsch_Quiz_bot",
        "🏆 Daily Arena Cup\nPlatz #4\nPunkte: 1\n📱 https://t.me/Deine_Deutsch_Quiz_bot",
    ]
    first_batch_buttons = [
        button.switch_inline_query
        for item in bot.send_photos[:4]
        for row in item["reply_markup"].inline_keyboard
        for button in row
        if button.switch_inline_query
    ]
    assert len(first_batch_buttons) == 4
    assert all(query and query.startswith("proof:daily:") for query in first_batch_buttons)
    assert len(render_calls) == 4
    assert all(call["rounds_played"] == 3 for call in render_calls)

    first_batch = len(bot.send_photos)
    parsed_tournament_id = UUID(tournament_id)
    async with SessionLocal.begin() as session:
        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=parsed_tournament_id,
        )
    assert all(item.proof_card_sent is True for item in participants)

    second = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        initial_delay_seconds=0,
    )
    assert int(second["sent"]) == 0
    assert int(second["cached_reused"]) == 0
    assert int(second["failed"]) == 0
    second_batch = bot.send_photos[first_batch:]
    assert second_batch == []


@pytest.mark.asyncio
async def test_daily_cup_proof_cards_skip_repeat_enqueue_for_same_participant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = fixed_daily_cup_now()
    await ensure_tournament_schema()

    user_ids = await create_daily_cup_users(prefix="daily_cup_proof_single", count=4)
    tournament_id = await create_completed_daily_cup(now_utc=now_utc, user_ids=user_ids)

    bot, _render_calls = install_recording_worker_bot(monkeypatch)

    first = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        user_id=user_ids[0],
        initial_delay_seconds=0,
    )
    assert first == {
        "processed": 1,
        "participants_total": 4,
        "sent": 1,
        "cached_reused": 0,
        "failed": 0,
    }

    second = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        user_id=user_ids[0],
        initial_delay_seconds=0,
    )
    assert second == {
        "processed": 1,
        "participants_total": 4,
        "sent": 0,
        "cached_reused": 0,
        "failed": 0,
    }
    assert len(bot.send_photos) == 1


@pytest.mark.asyncio
async def test_daily_cup_proof_cards_parallel_duplicate_run_does_not_send_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = fixed_daily_cup_now()
    await ensure_tournament_schema()

    user_ids = await create_daily_cup_users(prefix="daily_cup_proof_parallel", count=13)
    tournament_id = await create_completed_daily_cup(now_utc=now_utc, user_ids=user_ids)
    await set_user_free_energy(user_id=user_ids[2], free_energy=18, now_utc=now_utc)

    _FrozenDateTime.current = now_utc
    monkeypatch.setattr(daily_cup_proof_cards, "datetime", _FrozenDateTime)
    bot, _render_calls = install_recording_worker_bot(monkeypatch)

    original_send_photo = bot.send_photo

    async def _slow_send_photo(**kwargs):
        await asyncio.sleep(0.02)
        return await original_send_photo(**kwargs)

    monkeypatch.setattr(bot, "send_photo", _slow_send_photo)

    first, second = await asyncio.gather(
        daily_cup_proof_cards.run_daily_cup_proof_cards_async(
            tournament_id=tournament_id,
            initial_delay_seconds=0,
        ),
        daily_cup_proof_cards.run_daily_cup_proof_cards_async(
            tournament_id=tournament_id,
            initial_delay_seconds=0,
        ),
    )

    assert first["sent"] + second["sent"] == 13
    assert len(bot.send_photos) == 13
    assert [message["text"] for message in bot.send_messages] == [
        TEXTS_DE["msg.daily_cup.reward.rank_1"],
        TEXTS_DE["msg.daily_cup.reward.rank_2"],
        TEXTS_DE["msg.daily_cup.reward.rank_3"],
    ]


@pytest.mark.asyncio
async def test_daily_cup_proof_cards_keep_proof_cards_but_skip_economy_rewards_below_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = fixed_daily_cup_now()
    await ensure_tournament_schema()

    user_ids = await create_daily_cup_users(prefix="daily_cup_rewards_12", count=12)
    tournament_id = await create_completed_daily_cup(now_utc=now_utc, user_ids=user_ids)
    await set_user_free_energy(user_id=user_ids[2], free_energy=10, now_utc=now_utc)

    bot, _render_calls = install_recording_worker_bot(monkeypatch)

    result = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        initial_delay_seconds=0,
    )

    assert result == {
        "processed": 1,
        "participants_total": 12,
        "sent": 12,
        "cached_reused": 0,
        "failed": 0,
    }
    assert len(bot.send_photos) == 12
    assert bot.send_messages == []
    assert await _get_active_premium(user_id=user_ids[0]) is None
    async with SessionLocal.begin() as session:
        ticket_count = await PurchasesRepo.count_credited_product(
            session,
            user_id=user_ids[1],
            product_code="FRIEND_CHALLENGE_5",
        )
    assert ticket_count == 0
    assert await _get_free_energy(user_id=user_ids[2]) == 10


@pytest.mark.asyncio
async def test_daily_cup_proof_cards_grant_top_three_rewards_with_bye_seeded_results_and_are_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = fixed_daily_cup_now()
    await ensure_tournament_schema()

    user_ids = await create_daily_cup_users(prefix="daily_cup_rewards_13", count=13)
    tournament_id = await create_completed_daily_cup_with_bye_seeded_scores(
        now_utc=now_utc,
        user_ids=user_ids,
    )
    parsed_tournament_id = UUID(tournament_id)
    reward_key_prefix = parsed_tournament_id.hex
    await set_user_free_energy(user_id=user_ids[2], free_energy=18, now_utc=now_utc)
    await set_user_free_energy(user_id=user_ids[3], free_energy=7, now_utc=now_utc)

    _FrozenDateTime.current = now_utc
    monkeypatch.setattr(daily_cup_proof_cards, "datetime", _FrozenDateTime)
    bot, _render_calls = install_recording_worker_bot(monkeypatch)

    first = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        initial_delay_seconds=0,
    )
    second = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        initial_delay_seconds=0,
    )

    assert first == {
        "processed": 1,
        "participants_total": 13,
        "sent": 13,
        "cached_reused": 0,
        "failed": 0,
    }
    assert second == {
        "processed": 1,
        "participants_total": 13,
        "sent": 0,
        "cached_reused": 0,
        "failed": 0,
    }
    assert [message["text"] for message in bot.send_messages] == [
        TEXTS_DE["msg.daily_cup.reward.rank_1"],
        TEXTS_DE["msg.daily_cup.reward.rank_2"],
        TEXTS_DE["msg.daily_cup.reward.rank_3"],
    ]

    premium_entitlement = await _get_active_premium(user_id=user_ids[0])
    assert premium_entitlement is not None
    assert premium_entitlement.scope == "PREMIUM_3_DAYS"
    async with SessionLocal.begin() as session:
        matches = await TournamentMatchesRepo.list_by_tournament_for_update(
            session,
            tournament_id=parsed_tournament_id,
        )
    assert any(match.user_b is None for match in matches)
    assert (
        await _count_ledger_entries(
            idempotency_key=f"dcpl:{reward_key_prefix}:{user_ids[0]}",
        )
        == 1
    )

    async with SessionLocal.begin() as session:
        ticket_count = await PurchasesRepo.count_credited_product(
            session,
            user_id=user_ids[1],
            product_code="FRIEND_CHALLENGE_5",
        )
        no_reward_ticket_count = await PurchasesRepo.count_credited_product(
            session,
            user_id=user_ids[3],
            product_code="FRIEND_CHALLENGE_5",
        )

    assert ticket_count == 2
    assert no_reward_ticket_count == 0
    assert await _get_active_premium(user_id=user_ids[3]) is None
    third_place_energy = await _get_energy_balance(user_id=user_ids[2])
    assert third_place_energy == (18, 5)
    assert sum(third_place_energy) == 23
    assert await _get_free_energy(user_id=user_ids[3]) == 7
    assert (
        await _count_ledger_entries(
            idempotency_key=f"dcen:{reward_key_prefix}:{user_ids[2]}",
        )
        == 1
    )


@pytest.mark.asyncio
async def test_daily_cup_user_specific_proof_card_rerun_does_not_grant_winner_rewards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = fixed_daily_cup_now()
    await ensure_tournament_schema()

    user_ids = await create_daily_cup_users(prefix="daily_cup_rewards_partial", count=13)
    tournament_id = await create_completed_daily_cup(now_utc=now_utc, user_ids=user_ids)

    _FrozenDateTime.current = now_utc
    monkeypatch.setattr(daily_cup_proof_cards, "datetime", _FrozenDateTime)
    bot, _render_calls = install_recording_worker_bot(monkeypatch)

    result = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        user_id=user_ids[5],
        initial_delay_seconds=0,
    )

    assert result == {
        "processed": 1,
        "participants_total": 13,
        "sent": 1,
        "cached_reused": 0,
        "failed": 0,
    }
    assert len(bot.send_photos) == 1
    assert bot.send_messages == []
    assert await _get_active_premium(user_id=user_ids[0]) is None
    async with SessionLocal.begin() as session:
        ticket_count = await PurchasesRepo.count_credited_product(
            session,
            user_id=user_ids[1],
            product_code="FRIEND_CHALLENGE_5",
        )
    assert ticket_count == 0
    assert await _get_free_energy(user_id=user_ids[2]) is None


@pytest.mark.asyncio
async def test_daily_cup_first_place_reward_extends_existing_active_premium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = fixed_daily_cup_now()
    await ensure_tournament_schema()

    user_ids = await create_daily_cup_users(prefix="daily_cup_rewards_extend", count=13)
    tournament_id = await create_completed_daily_cup(now_utc=now_utc, user_ids=user_ids)
    parsed_tournament_id = UUID(tournament_id)
    reward_key_prefix = parsed_tournament_id.hex
    await set_user_active_premium(
        user_id=user_ids[0],
        scope="PREMIUM_WEEK",
        now_utc=now_utc - timedelta(days=1),
        ends_at=now_utc + timedelta(days=5),
    )
    await set_user_free_energy(user_id=user_ids[2], free_energy=18, now_utc=now_utc)

    _FrozenDateTime.current = now_utc
    monkeypatch.setattr(daily_cup_proof_cards, "datetime", _FrozenDateTime)
    bot, _render_calls = install_recording_worker_bot(monkeypatch)

    result = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        initial_delay_seconds=0,
    )

    assert result == {
        "processed": 1,
        "participants_total": 13,
        "sent": 13,
        "cached_reused": 0,
        "failed": 0,
    }
    premium_entitlement = await _get_active_premium(user_id=user_ids[0])
    assert premium_entitlement is not None
    assert premium_entitlement.scope == "PREMIUM_WEEK"
    assert premium_entitlement.ends_at == now_utc + timedelta(days=8)
    assert [message["text"] for message in bot.send_messages] == [
        TEXTS_DE["msg.daily_cup.reward.rank_1"],
        TEXTS_DE["msg.daily_cup.reward.rank_2"],
        TEXTS_DE["msg.daily_cup.reward.rank_3"],
    ]
    assert (
        await _count_ledger_entries(
            idempotency_key=f"dcpl:{reward_key_prefix}:{user_ids[0]}",
        )
        == 1
    )
