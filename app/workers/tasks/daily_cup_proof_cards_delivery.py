from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from aiogram.types import BufferedInputFile

from app.bot.keyboards.daily_cup import build_daily_cup_share_keyboard, build_daily_cup_share_url
from app.bot.texts.de import TEXTS_DE
from app.core.telegram_links import public_bot_link
from app.db.repo.ledger_repo import LedgerRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.economy.energy.service import EnergyService
from app.economy.premium_grants import grant_premium_days
from app.economy.purchases.catalog import get_product
from app.economy.purchases.service import PurchaseService
from app.game.sessions.service.constants import FRIEND_CHALLENGE_TICKET_PRODUCT_CODE
from app.workers.tasks.daily_cup_proof_cards_text import build_caption
from app.workers.tasks.tournaments_proof_card_render import render_tournament_proof_card_png

DAILY_CUP_REWARD_MIN_PARTICIPANTS = 13
DAILY_CUP_PREMIUM_REWARD_DAYS = 3
DAILY_CUP_TICKET_REWARD_TOTAL = 2
DAILY_CUP_FREE_ENERGY_REWARD = 5


@dataclass(frozen=True, slots=True)
class DailyCupProofCardDeliveryResult:
    sent: int
    cached_reused: int
    failed: int


@dataclass(frozen=True, slots=True)
class DailyCupProofCardAttemptResult:
    sent: bool
    cached_reused: bool
    failed: bool


@dataclass(frozen=True, slots=True)
class DailyCupWinnerRewardNotification:
    user_id: int
    text: str


def _build_reward_key(
    *,
    prefix: str,
    tournament_id: UUID,
    user_id: int,
    suffix: int | None = None,
) -> str:
    parts = [prefix, tournament_id.hex, str(user_id)]
    if suffix is not None:
        parts.append(str(suffix))
    return ":".join(parts)


async def _grant_daily_cup_premium_reward(
    *,
    session: Any,
    tournament_id: UUID,
    user_id: int,
    now_utc: datetime,
) -> bool:
    ledger_idempotency_key = _build_reward_key(
        prefix="dcpl",
        tournament_id=tournament_id,
        user_id=user_id,
    )
    if await LedgerRepo.get_by_idempotency_key(session, ledger_idempotency_key) is not None:
        return False

    await grant_premium_days(
        session,
        user_id=user_id,
        grant_days=DAILY_CUP_PREMIUM_REWARD_DAYS,
        scope="PREMIUM_3_DAYS",
        now_utc=now_utc,
        source="TOURNAMENT",
        entry_type="TOURNAMENT_REWARD",
        entitlement_idempotency_key=_build_reward_key(
            prefix="dcpe",
            tournament_id=tournament_id,
            user_id=user_id,
        ),
        ledger_idempotency_key=ledger_idempotency_key,
        metadata={
            "rank": 1,
            "reward_type": "PREMIUM_3_DAYS",
            "tournament_id": str(tournament_id),
        },
    )
    return True


def _daily_cup_reward_message(*, rank: int) -> str:
    return TEXTS_DE[f"msg.daily_cup.reward.rank_{rank}"]


async def _credit_zero_cost_product(
    *,
    session: Any,
    user_id: int,
    product_code: str,
    idempotency_key: str,
    now_utc: datetime,
) -> Any:
    product = get_product(product_code)
    if product is None:
        raise ValueError(f"product is not configured: {product_code}")

    purchase = await PurchasesRepo.get_by_idempotency_key(session, idempotency_key)
    if purchase is None:
        purchase = PurchaseService._build_purchase(
            product,
            user_id=user_id,
            idempotency_key=idempotency_key,
            discount_stars_amount=product.stars_amount,
            applied_promo_code_id=None,
            now_utc=now_utc,
        )
        await PurchasesRepo.create(
            session,
            purchase=purchase,
            created_at=now_utc,
        )

    return await PurchaseService.apply_zero_cost_purchase(
        session,
        purchase_id=purchase.id,
        user_id=user_id,
        now_utc=now_utc,
    )


async def _grant_daily_cup_ticket_reward(
    *,
    session: Any,
    tournament_id: UUID,
    user_id: int,
    now_utc: datetime,
) -> bool:
    granted_any = False
    for ticket_no in range(1, DAILY_CUP_TICKET_REWARD_TOTAL + 1):
        result = await _credit_zero_cost_product(
            session=session,
            user_id=user_id,
            product_code=FRIEND_CHALLENGE_TICKET_PRODUCT_CODE,
            idempotency_key=_build_reward_key(
                prefix="dctk",
                tournament_id=tournament_id,
                user_id=user_id,
                suffix=ticket_no,
            ),
            now_utc=now_utc,
        )
        granted_any = granted_any or not bool(result.idempotent_replay)
    return granted_any


async def _grant_daily_cup_energy_reward(
    *,
    session: Any,
    tournament_id: UUID,
    user_id: int,
    now_utc: datetime,
) -> bool:
    # Winner rewards must grant the public +5 even when free energy is already capped.
    result = await EnergyService.credit_paid_energy(
        session,
        user_id=user_id,
        amount=DAILY_CUP_FREE_ENERGY_REWARD,
        idempotency_key=_build_reward_key(
            prefix="dcen",
            tournament_id=tournament_id,
            user_id=user_id,
        ),
        now_utc=now_utc,
        source="TOURNAMENT",
    )
    return result.amount > 0 and not result.idempotent_replay


async def grant_daily_cup_winner_rewards(
    *,
    session: Any,
    context: Any,
    now_utc: datetime,
    logger: Any,
) -> list[DailyCupWinnerRewardNotification]:
    if context.participants_total < DAILY_CUP_REWARD_MIN_PARTICIPANTS:
        return []

    participant_user_ids = {int(row.user_id) for row in context.participants}
    notifications: list[DailyCupWinnerRewardNotification] = []

    for rank, current_user_id in enumerate(context.standings_user_ids[:3], start=1):
        if current_user_id not in participant_user_ids:
            continue

        reward_granted = await _grant_reward_for_rank(
            session=session,
            tournament_id=context.parsed_tournament_id,
            user_id=current_user_id,
            rank=rank,
            now_utc=now_utc,
            logger=logger,
        )
        if reward_granted:
            notifications.append(
                DailyCupWinnerRewardNotification(
                    user_id=current_user_id,
                    text=_daily_cup_reward_message(rank=rank),
                )
            )

    return notifications


async def _grant_reward_for_rank(
    *,
    session: Any,
    tournament_id: UUID,
    user_id: int,
    rank: int,
    now_utc: datetime,
    logger: Any,
) -> bool:
    try:
        async with session.begin_nested():
            if rank == 1:
                return await _grant_daily_cup_premium_reward(
                    session=session,
                    tournament_id=tournament_id,
                    user_id=user_id,
                    now_utc=now_utc,
                )
            if rank == 2:
                return await _grant_daily_cup_ticket_reward(
                    session=session,
                    tournament_id=tournament_id,
                    user_id=user_id,
                    now_utc=now_utc,
                )
            return await _grant_daily_cup_energy_reward(
                session=session,
                tournament_id=tournament_id,
                user_id=user_id,
                now_utc=now_utc,
            )
    except Exception as exc:
        logger.warning(
            "daily_cup_winner_reward_grant_failed",
            tournament_id=str(tournament_id),
            user_id=user_id,
            rank=rank,
            error_type=type(exc).__name__,
        )
        return False


async def send_daily_cup_winner_reward_messages(
    *,
    bot: Any,
    context: Any,
    notifications: list[DailyCupWinnerRewardNotification],
    logger: Any,
) -> None:
    for notification in notifications:
        chat_id = context.telegram_targets.get(notification.user_id)
        if chat_id is None:
            continue

        try:
            await bot.send_message(chat_id=chat_id, text=notification.text)
        except Exception as exc:
            logger.warning(
                "daily_cup_winner_reward_message_failed",
                tournament_id=str(context.parsed_tournament_id),
                user_id=notification.user_id,
                error_type=type(exc).__name__,
            )


async def send_daily_cup_proof_card(
    *,
    bot,
    tournament_id: str,
    user_id: int,
    chat_id: int,
    place: int,
    points: str,
    participants_total: int,
    cached_file_id: str | None,
    player_label: str,
    now_utc: datetime,
    rounds_played: int,
    render_card_png: Callable[..., bytes] = render_tournament_proof_card_png,
) -> tuple[bool, bool, str | None]:
    caption = build_caption(place=place, points=points)
    share_url = build_daily_cup_share_url(
        base_link=public_bot_link(),
        share_text=TEXTS_DE["msg.daily_cup.share_template"].format(
            place=place,
            total=participants_total,
            points=points,
        ),
    )
    keyboard = build_daily_cup_share_keyboard(tournament_id=tournament_id, share_url=share_url)
    if cached_file_id:
        await bot.send_photo(
            chat_id=chat_id,
            photo=cached_file_id,
            caption=caption,
            reply_markup=keyboard,
        )
        return True, True, None

    card_png = render_card_png(
        player_label=player_label,
        place=place,
        points=points,
        format_label="7 Fragen",
        completed_at=now_utc,
        tournament_name="Daily Arena Cup",
        rounds_played=rounds_played,
        is_daily_arena=True,
    )
    message = await bot.send_photo(
        chat_id=chat_id,
        photo=BufferedInputFile(card_png, filename=f"daily_cup_{tournament_id}_{user_id}.png"),
        caption=caption,
        reply_markup=keyboard,
    )
    file_id = message.photo[-1].file_id if message.photo else None
    return True, False, file_id


async def _deliver_proof_card_for_user(
    *,
    context: Any,
    bot: Any,
    tournament_id: str,
    user_id: int,
    chat_id: int,
    now_utc: datetime,
    session_factory: Any,
    participants_repo: Any,
    send_proof_card_fn: Callable[..., Any],
    render_card_png: Callable[..., bytes],
    logger: Any,
) -> DailyCupProofCardAttemptResult:
    try:
        async with session_factory.begin() as session:
            participant_row = await participants_repo.get_for_tournament_user_for_update(
                session,
                tournament_id=context.parsed_tournament_id,
                user_id=user_id,
                skip_locked=True,
            )
            if participant_row is None or participant_row.proof_card_sent:
                return DailyCupProofCardAttemptResult(
                    sent=False,
                    cached_reused=False,
                    failed=False,
                )

            place = context.standings_user_ids.index(user_id) + 1
            points = context.points_by_user.get(user_id, "0")
            delivered, reused_cached, file_id = await send_proof_card_fn(
                bot=bot,
                tournament_id=tournament_id,
                user_id=user_id,
                chat_id=chat_id,
                place=place,
                points=points,
                participants_total=context.participants_total,
                cached_file_id=participant_row.proof_card_file_id,
                player_label=context.user_labels.get(user_id, "Spieler"),
                now_utc=now_utc,
                rounds_played=context.rounds_played,
                render_card_png=render_card_png,
            )
            if not delivered:
                return DailyCupProofCardAttemptResult(
                    sent=False,
                    cached_reused=False,
                    failed=False,
                )

            await participants_repo.set_proof_card_sent(
                session,
                tournament_id=context.parsed_tournament_id,
                user_id=user_id,
            )
            if file_id is not None:
                await participants_repo.set_proof_card_file_id_if_missing(
                    session,
                    tournament_id=context.parsed_tournament_id,
                    user_id=user_id,
                    file_id=file_id,
                )
    except Exception as exc:
        logger.warning(
            "daily_cup_proof_card_send_failed",
            tournament_id=tournament_id,
            user_id=user_id,
            error_type=type(exc).__name__,
        )
        return DailyCupProofCardAttemptResult(sent=False, cached_reused=False, failed=True)

    return DailyCupProofCardAttemptResult(
        sent=True,
        cached_reused=bool(reused_cached),
        failed=False,
    )


async def deliver_daily_cup_proof_cards(
    *,
    context: Any,
    bot: Any,
    tournament_id: str,
    now_utc: datetime,
    session_factory: Any,
    participants_repo: Any,
    send_proof_card_fn: Callable[..., Any],
    render_card_png: Callable[..., bytes] = render_tournament_proof_card_png,
    logger: Any,
) -> DailyCupProofCardDeliveryResult:
    sent = 0
    cached_reused = 0
    failed = 0

    for row in context.participants:
        current_user_id = int(row.user_id)
        chat_id = context.telegram_targets.get(current_user_id)
        if chat_id is None:
            failed += 1
            continue
        attempt = await _deliver_proof_card_for_user(
            context=context,
            bot=bot,
            tournament_id=tournament_id,
            user_id=current_user_id,
            chat_id=chat_id,
            now_utc=now_utc,
            session_factory=session_factory,
            participants_repo=participants_repo,
            send_proof_card_fn=send_proof_card_fn,
            render_card_png=render_card_png,
            logger=logger,
        )
        sent += int(attempt.sent)
        cached_reused += int(attempt.cached_reused)
        failed += int(attempt.failed)

    return DailyCupProofCardDeliveryResult(
        sent=sent,
        cached_reused=cached_reused,
        failed=failed,
    )


__all__ = [
    "DAILY_CUP_REWARD_MIN_PARTICIPANTS",
    "DailyCupProofCardDeliveryResult",
    "DailyCupWinnerRewardNotification",
    "deliver_daily_cup_proof_cards",
    "grant_daily_cup_winner_rewards",
    "send_daily_cup_proof_card",
    "send_daily_cup_winner_reward_messages",
]
