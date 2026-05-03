from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.users_repo import UsersRepo
from app.game.duels.constants import (
    DUEL_FREE_LIMITS_PER_DAY,
    DUEL_LIMIT_ACTION_ARENA_ACCEPT,
    DUEL_LIMIT_ACTION_ARENA_CREATE,
    DUEL_LIMIT_ACTION_FRIEND_CREATE,
    DUEL_LIMIT_ACTION_REVANCHE,
    DUEL_PAYWALL_PRODUCT_CODES,
    DUEL_TICKET_PRODUCT_CODE,
)
from app.game.modes.rules import requires_duel_limit_gate

if TYPE_CHECKING:
    from app.economy.purchases.catalog import ProductSpec

DUEL_ACCESS_FREE = "FREE"
DUEL_ACCESS_PAID_TICKET = "PAID_TICKET"
DUEL_ACCESS_PREMIUM = "PREMIUM"
DUEL_ACCESS_TYPES = frozenset({DUEL_ACCESS_FREE, DUEL_ACCESS_PAID_TICKET, DUEL_ACCESS_PREMIUM})
_BERLIN_TZ = ZoneInfo("Europe/Berlin")


@dataclass(frozen=True, slots=True)
class DuelLimitDecision:
    allowed: bool
    access_type: str | None
    free_limit: int
    free_used_today: int
    paid_ticket_uses: int
    credited_tickets: int
    premium_active: bool
    paywall_product_codes: tuple[str, str] = DUEL_PAYWALL_PRODUCT_CODES


class DuelLimitService:
    @staticmethod
    def free_limit_for_action(action: str) -> int:
        return DUEL_FREE_LIMITS_PER_DAY[action]

    @staticmethod
    def paywall_product_codes() -> tuple[str, str]:
        return DUEL_PAYWALL_PRODUCT_CODES

    @staticmethod
    def paywall_products() -> tuple[ProductSpec, ...]:
        from app.economy.purchases.catalog import get_product, is_product_available_for_sale

        products: list[ProductSpec] = []
        for product_code in DUEL_PAYWALL_PRODUCT_CODES:
            product = get_product(product_code)
            if product is None or not is_product_available_for_sale(product_code):
                raise RuntimeError(f"duel paywall product is not saleable: {product_code}")
            products.append(product)
        return tuple(products)

    @staticmethod
    def assert_start_gate(source: str, *, duel_limit_checked: bool) -> None:
        if requires_duel_limit_gate(source) and not duel_limit_checked:
            from app.game.sessions.errors import DuelLimitRequiredError

            raise DuelLimitRequiredError

    @staticmethod
    def assert_resolved_access_type(source: str, *, access_type: str) -> None:
        DuelLimitService.assert_start_gate(
            source,
            duel_limit_checked=access_type in DUEL_ACCESS_TYPES,
        )

    @staticmethod
    def resolve_access_type(
        *,
        action: str,
        premium_active: bool,
        free_used_today: int,
        paid_ticket_uses: int,
        credited_tickets: int,
    ) -> DuelLimitDecision:
        free_limit = DuelLimitService.free_limit_for_action(action)
        if premium_active:
            return DuelLimitDecision(
                allowed=True,
                access_type=DUEL_ACCESS_PREMIUM,
                free_limit=free_limit,
                free_used_today=free_used_today,
                paid_ticket_uses=paid_ticket_uses,
                credited_tickets=credited_tickets,
                premium_active=True,
            )
        if free_used_today < free_limit:
            return DuelLimitDecision(
                allowed=True,
                access_type=DUEL_ACCESS_FREE,
                free_limit=free_limit,
                free_used_today=free_used_today,
                paid_ticket_uses=paid_ticket_uses,
                credited_tickets=credited_tickets,
                premium_active=False,
            )
        if paid_ticket_uses < credited_tickets:
            return DuelLimitDecision(
                allowed=True,
                access_type=DUEL_ACCESS_PAID_TICKET,
                free_limit=free_limit,
                free_used_today=free_used_today,
                paid_ticket_uses=paid_ticket_uses,
                credited_tickets=credited_tickets,
                premium_active=False,
            )
        return DuelLimitDecision(
            allowed=False,
            access_type=None,
            free_limit=free_limit,
            free_used_today=free_used_today,
            paid_ticket_uses=paid_ticket_uses,
            credited_tickets=credited_tickets,
            premium_active=False,
        )

    @staticmethod
    async def resolve_friend_create_access_type(
        session: AsyncSession,
        *,
        creator_user_id: int,
        now_utc: datetime,
    ) -> str:
        from app.game.sessions.errors import (
            FriendChallengeAccessError,
            FriendChallengePaymentRequiredError,
        )

        creator = await UsersRepo.get_by_id_for_update(session, creator_user_id)
        if creator is None:
            raise FriendChallengeAccessError

        premium_active = await EntitlementsRepo.has_active_premium(
            session,
            creator_user_id,
            now_utc,
        )
        if premium_active:
            return DUEL_ACCESS_PREMIUM

        day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        free_used_today = (
            await (
                FriendChallengesRepo.count_by_creator_access_type_excluding_arena_revanche(
                    session,
                    creator_user_id=creator_user_id,
                    access_type=DUEL_ACCESS_FREE,
                    since=day_start,
                )
            )
        )
        if free_used_today < DuelLimitService.free_limit_for_action(
            DUEL_LIMIT_ACTION_FRIEND_CREATE
        ):
            return DUEL_ACCESS_FREE

        paid_ticket_uses = await DuelLimitService._count_paid_ticket_uses(
            session,
            user_id=creator_user_id,
        )
        credited_tickets = await PurchasesRepo.count_credited_product(
            session,
            user_id=creator_user_id,
            product_code=DUEL_TICKET_PRODUCT_CODE,
        )
        decision = DuelLimitService.resolve_access_type(
            action=DUEL_LIMIT_ACTION_FRIEND_CREATE,
            premium_active=False,
            free_used_today=free_used_today,
            paid_ticket_uses=paid_ticket_uses,
            credited_tickets=credited_tickets,
        )
        if not decision.allowed or decision.access_type is None:
            raise FriendChallengePaymentRequiredError
        return decision.access_type

    @staticmethod
    async def resolve_arena_create_access_type(
        session: AsyncSession,
        *,
        user_id: int,
        now_utc: datetime,
    ) -> str:
        from app.db.repo.arena_duels_repo import ArenaDuelsRepo
        from app.game.arena_duels.errors import ArenaDuelAccessError, ArenaDuelPaymentRequiredError

        await DuelLimitService._ensure_user_exists(
            session,
            user_id=user_id,
            access_error=ArenaDuelAccessError,
        )
        premium_active = await EntitlementsRepo.has_active_premium(session, user_id, now_utc)
        if premium_active:
            return DUEL_ACCESS_PREMIUM

        day_start = _berlin_day_start_utc(now_utc)
        free_used_today = await ArenaDuelsRepo.count_creator_duels_by_access_type(
            session,
            creator_user_id=user_id,
            access_type=DUEL_ACCESS_FREE,
            since=day_start,
        )
        return await DuelLimitService._resolve_non_premium_access_type(
            session,
            user_id=user_id,
            action=DUEL_LIMIT_ACTION_ARENA_CREATE,
            free_used_today=free_used_today,
            payment_required_error=ArenaDuelPaymentRequiredError,
        )

    @staticmethod
    async def resolve_arena_accept_access_type(
        session: AsyncSession,
        *,
        user_id: int,
        now_utc: datetime,
    ) -> str:
        from app.db.repo.arena_duels_repo import ArenaDuelsRepo
        from app.game.arena_duels.errors import ArenaDuelAccessError, ArenaDuelPaymentRequiredError

        await DuelLimitService._ensure_user_exists(
            session,
            user_id=user_id,
            access_error=ArenaDuelAccessError,
        )
        premium_active = await EntitlementsRepo.has_active_premium(session, user_id, now_utc)
        if premium_active:
            return DUEL_ACCESS_PREMIUM

        day_start = _berlin_day_start_utc(now_utc)
        free_used_today = await ArenaDuelsRepo.count_challenger_attempts_by_access_type(
            session,
            user_id=user_id,
            access_type=DUEL_ACCESS_FREE,
            since=day_start,
        )
        return await DuelLimitService._resolve_non_premium_access_type(
            session,
            user_id=user_id,
            action=DUEL_LIMIT_ACTION_ARENA_ACCEPT,
            free_used_today=free_used_today,
            payment_required_error=ArenaDuelPaymentRequiredError,
        )

    @staticmethod
    async def resolve_revanche_access_type(
        session: AsyncSession,
        *,
        user_id: int,
        now_utc: datetime,
    ) -> str:
        from app.db.repo.analytics_repo import AnalyticsRepo
        from app.game.arena_duels.constants import ARENA_REVANCHE_SENT_EVENT
        from app.game.arena_duels.errors import ArenaDuelAccessError, ArenaDuelPaymentRequiredError

        await DuelLimitService._ensure_user_exists(
            session,
            user_id=user_id,
            access_error=ArenaDuelAccessError,
        )
        premium_active = await EntitlementsRepo.has_active_premium(session, user_id, now_utc)
        if premium_active:
            return DUEL_ACCESS_PREMIUM

        free_used_today = await AnalyticsRepo.count_user_events_since_by_payload_value(
            session,
            event_type=ARENA_REVANCHE_SENT_EVENT,
            user_id=user_id,
            since_utc=_berlin_day_start_utc(now_utc),
            payload_key="access_type",
            payload_value=DUEL_ACCESS_FREE,
        )
        return await DuelLimitService._resolve_non_premium_access_type(
            session,
            user_id=user_id,
            action=DUEL_LIMIT_ACTION_REVANCHE,
            free_used_today=free_used_today,
            payment_required_error=ArenaDuelPaymentRequiredError,
        )

    @staticmethod
    async def _resolve_non_premium_access_type(
        session: AsyncSession,
        *,
        user_id: int,
        action: str,
        free_used_today: int,
        payment_required_error: type[Exception],
    ) -> str:
        paid_ticket_uses = await DuelLimitService._count_paid_ticket_uses(
            session,
            user_id=user_id,
        )
        credited_tickets = await PurchasesRepo.count_credited_product(
            session,
            user_id=user_id,
            product_code=DUEL_TICKET_PRODUCT_CODE,
        )
        decision = DuelLimitService.resolve_access_type(
            action=action,
            premium_active=False,
            free_used_today=free_used_today,
            paid_ticket_uses=paid_ticket_uses,
            credited_tickets=credited_tickets,
        )
        if not decision.allowed or decision.access_type is None:
            raise payment_required_error
        return decision.access_type

    @staticmethod
    async def _count_paid_ticket_uses(session: AsyncSession, *, user_id: int) -> int:
        from app.db.repo.analytics_repo import AnalyticsRepo
        from app.db.repo.arena_duels_repo import ArenaDuelsRepo
        from app.game.arena_duels.constants import ARENA_REVANCHE_SENT_EVENT

        friend_uses = (
            await (
                FriendChallengesRepo.count_by_creator_access_type_excluding_arena_revanche(
                    session,
                    creator_user_id=user_id,
                    access_type=DUEL_ACCESS_PAID_TICKET,
                )
            )
        )
        arena_uses = await ArenaDuelsRepo.count_paid_ticket_usage(session, user_id=user_id)
        revanche_uses = await AnalyticsRepo.count_user_events_by_payload_value(
            session,
            event_type=ARENA_REVANCHE_SENT_EVENT,
            user_id=user_id,
            payload_key="access_type",
            payload_value=DUEL_ACCESS_PAID_TICKET,
        )
        return friend_uses + arena_uses + revanche_uses

    @staticmethod
    async def _ensure_user_exists(
        session: AsyncSession,
        *,
        user_id: int,
        access_error: type[Exception],
    ) -> None:
        user = await UsersRepo.get_by_id_for_update(session, user_id)
        if user is None:
            raise access_error


def _berlin_day_start_utc(now_utc: datetime) -> datetime:
    aware_now = now_utc if now_utc.tzinfo is not None else now_utc.replace(tzinfo=timezone.utc)
    berlin_start = aware_now.astimezone(_BERLIN_TZ).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    return berlin_start.astimezone(timezone.utc)
