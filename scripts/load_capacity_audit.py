from __future__ import annotations

import argparse
import asyncio
import json
import resource
import statistics
import time
from collections import Counter
from collections.abc import Iterable
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import redis.asyncio as redis
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.methods import AnswerCallbackQuery, GetMe, SendMessage
from aiogram.types import Message as TelegramMessage
from aiogram.types import User as TelegramUser
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, insert, select, text

from app.api.routes import telegram_webhook
from app.bot.application import build_dispatcher
from app.core.config import get_settings
from app.core.integration_db_safety import assert_safe_integration_db
from app.db.models.energy_state import EnergyState
from app.db.models.mode_progress import ModeProgress
from app.db.models.processed_updates import ProcessedUpdate
from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_questions import QuizQuestion
from app.db.models.quiz_sessions import QuizSession
from app.db.models.streak_state import StreakState
from app.db.models.users import User
from app.db.session import SessionLocal, engine
from app.economy.referrals.service import ReferralService
from app.game.questions.runtime_bank import clear_question_pool_cache
from app.game.sessions.service import GameSessionService, select_question_for_mode
from app.main import app
from app.services.channel_bonus import ChannelBonusService
from app.services.user_onboarding import UserOnboardingService
from app.workers.tasks import telegram_updates

MODE_CODE = "QUICK_MIX_A1A2"
SOURCE = "MENU"
BASE_USER_ID = 10_000_000
BASE_TELEGRAM_ID = 90_000_000_000
BASE_UPDATE_ID = 700_000_000
WEBHOOK_SECRET = "capacity-audit-secret"
_CURRENT_QUERY_STEP: ContextVar[str] = ContextVar(
    "capacity_audit_current_query_step",
    default="unscoped",
)

TRUNCATE_TABLES = (
    "daily_metrics",
    "promo_audit_log",
    "admins",
    "promo_attempts",
    "promo_redemptions",
    "contact_requests",
    "referrals",
    "offers_impressions",
    "quiz_attempts",
    "daily_push_logs",
    "daily_question_sets",
    "daily_runs",
    "quiz_questions",
    "quiz_sessions",
    "friend_challenges",
    "tournament_round_scores",
    "tournament_matches",
    "tournament_participants",
    "tournaments",
    "mode_progress",
    "entitlements",
    "ledger_entries",
    "purchases",
    "processed_updates",
    "outbox_events",
    "analytics_events",
    "analytics_daily",
    "reconciliation_runs",
    "promo_codes",
    "promo_code_batches",
    "streak_state",
    "energy_state",
    "users",
)


@dataclass(slots=True)
class LatencySummary:
    count: int
    p50_ms: float
    p95_ms: float
    max_ms: float


@dataclass(slots=True)
class QuerySummary:
    count: int
    total_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float


@dataclass(slots=True)
class QueryDigest:
    statement: str
    count: int
    total_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float


@dataclass(slots=True)
class ScaleResult:
    users: int
    db_size_mb: float
    users_count_ms: float
    user_lookup_p95_ms: float
    global_best_ms: float
    public_stats_ms: float
    question_pool_warm_ms: float
    dispatcher_build_ms: float
    redis_keys: int
    rss_mb: float


@dataclass(slots=True)
class ActiveResult:
    active_users: int
    flow: str
    latency: LatencySummary
    errors: int
    query_summary: QuerySummary
    db_lock_waits_active: int
    deadlocks_delta: int
    outbound_calls: dict[str, int]
    query_steps: dict[str, QuerySummary]
    query_categories: dict[str, QuerySummary]
    top_queries: list[QueryDigest]
    top_queries_by_count: list[QueryDigest]
    attempts_created: int
    duplicate_answer_groups: int
    processed_updates: dict[str, int]
    rss_mb: float


@dataclass(slots=True)
class AuditReport:
    started_at: str
    database_url_redacted: str
    redis_url_redacted: str
    registered_scales: list[ScaleResult] = field(default_factory=list)
    active_tests: list[ActiveResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class QueryRecorder:
    def __init__(self) -> None:
        self.timings_ms: list[float] = []
        self._by_statement: dict[str, list[float]] = {}
        self._by_step: dict[str, list[float]] = {}
        self._by_category: dict[str, list[float]] = {}

    def __enter__(self) -> QueryRecorder:
        event.listen(engine.sync_engine, "before_cursor_execute", self._before)
        event.listen(engine.sync_engine, "after_cursor_execute", self._after)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        event.remove(engine.sync_engine, "before_cursor_execute", self._before)
        event.remove(engine.sync_engine, "after_cursor_execute", self._after)

    def _before(self, conn, cursor, statement, parameters, context, executemany) -> None:
        del conn, cursor, statement, parameters, executemany
        context._capacity_audit_started_at = time.perf_counter()

    def _after(self, conn, cursor, statement, parameters, context, executemany) -> None:
        del conn, cursor, parameters, executemany
        started_at = getattr(context, "_capacity_audit_started_at", None)
        if started_at is not None:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            self.timings_ms.append(elapsed_ms)
            self._by_statement.setdefault(_compact_statement(statement), []).append(elapsed_ms)
            self._by_step.setdefault(_CURRENT_QUERY_STEP.get(), []).append(elapsed_ms)
            self._by_category.setdefault(_classify_statement(statement), []).append(elapsed_ms)

    def summary(self) -> QuerySummary:
        return QuerySummary(
            count=len(self.timings_ms),
            total_ms=round(sum(self.timings_ms), 3),
            p50_ms=round(_percentile(self.timings_ms, 50), 3),
            p95_ms=round(_percentile(self.timings_ms, 95), 3),
            max_ms=round(max(self.timings_ms) if self.timings_ms else 0.0, 3),
        )

    def top_queries(self, *, limit: int = 10) -> list[QueryDigest]:
        return self._digest_items(
            sorted(
                self._by_statement.items(),
                key=lambda item: sum(item[1]),
                reverse=True,
            )[:limit]
        )

    def top_queries_by_count(self, *, limit: int = 10) -> list[QueryDigest]:
        return self._digest_items(
            sorted(
                self._by_statement.items(),
                key=lambda item: (len(item[1]), sum(item[1])),
                reverse=True,
            )[:limit]
        )

    def step_summaries(self) -> dict[str, QuerySummary]:
        return {step: _query_summary(timings) for step, timings in sorted(self._by_step.items())}

    def category_summaries(self) -> dict[str, QuerySummary]:
        return {
            category: _query_summary(timings)
            for category, timings in sorted(self._by_category.items())
        }

    @staticmethod
    def _digest_items(items: list[tuple[str, list[float]]]) -> list[QueryDigest]:
        return [
            QueryDigest(
                statement=statement,
                count=len(timings),
                total_ms=round(sum(timings), 3),
                p50_ms=round(_percentile(timings, 50), 3),
                p95_ms=round(_percentile(timings, 95), 3),
                max_ms=round(max(timings) if timings else 0.0, 3),
            )
            for statement, timings in items
        ]


def _query_summary(timings_ms: list[float]) -> QuerySummary:
    return QuerySummary(
        count=len(timings_ms),
        total_ms=round(sum(timings_ms), 3),
        p50_ms=round(_percentile(timings_ms, 50), 3),
        p95_ms=round(_percentile(timings_ms, 95), 3),
        max_ms=round(max(timings_ms) if timings_ms else 0.0, 3),
    )


class query_step:
    def __init__(self, name: str) -> None:
        self._name = name
        self._token = None

    def __enter__(self) -> None:
        self._token = _CURRENT_QUERY_STEP.set(self._name)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._token is not None:
            _CURRENT_QUERY_STEP.reset(self._token)


def _classify_statement(statement: str) -> str:
    normalized = " ".join(statement.lower().split())
    if " entitlements" in normalized:
        return "entitlement_checks"
    if " energy_state" in normalized or " ledger_entries" in normalized:
        return "energy_check_update"
    if "max(streak_state.best_streak)" in normalized:
        return "leaderboard_statistics_badges"
    if " tournament_participants" in normalized or " tournaments" in normalized:
        return "leaderboard_statistics_badges"
    if " analytics_" in normalized or " daily_metrics" in normalized:
        return "leaderboard_statistics_badges"
    if " users" in normalized:
        return "user_state"
    if " streak_state" in normalized or " mode_progress" in normalized:
        return "user_state"
    if " quiz_questions" in normalized:
        return "question_pool"
    if " quiz_attempts" in normalized:
        return "answer_callback"
    if " quiz_sessions" in normalized:
        return "quiz_session"
    if " referrals" in normalized or " offers_impressions" in normalized:
        return "post_game_prompts"
    if " processed_updates" in normalized:
        return "telegram_update_handling"
    return "other"


def _compact_statement(statement: str) -> str:
    return " ".join(statement.split())[:240]


class InProcessUpdateQueue:
    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task[str]] = {}

    def delay(self, *, update_payload: dict[str, object], update_id: int) -> None:
        self._tasks[update_id] = asyncio.create_task(
            telegram_updates.process_update_async(update_payload, update_id=update_id)
        )

    async def drain_update(self, update_id: int) -> str:
        task = self._tasks.pop(update_id, None)
        if task is None:
            raise RuntimeError(f"update_id={update_id} was not enqueued")
        return await task

    async def drain_all(self) -> list[str]:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        if not tasks:
            return []
        return await asyncio.gather(*tasks)


class BotApiStub:
    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()
        self.sent_messages: list[dict[str, object]] = []
        self._message_seq = 1_000_000

    def reset(self) -> None:
        self.calls.clear()
        self.sent_messages.clear()

    def _next_message_id(self) -> int:
        self._message_seq += 1
        return self._message_seq

    def _build_message(self, *, chat_id: int, text_value: str | None) -> TelegramMessage:
        payload: dict[str, object] = {
            "message_id": self._next_message_id(),
            "date": int(datetime.now(UTC).timestamp()),
            "chat": _private_chat_payload(chat_id),
        }
        if text_value is not None:
            payload["text"] = text_value
        return TelegramMessage.model_validate(payload)

    async def dispatch(self, method: object) -> object:
        method_name = type(method).__name__
        self.calls[method_name] += 1
        if isinstance(method, GetMe):
            return TelegramUser(
                id=777_000_001,
                is_bot=True,
                first_name="QuizArena",
                username="quiz_arena_capacity_bot",
            )
        if isinstance(method, SendMessage):
            chat_id = int(method.chat_id)
            message = self._build_message(chat_id=chat_id, text_value=method.text)
            self.sent_messages.append(
                {
                    "chat_id": chat_id,
                    "message_id": message.message_id,
                    "text": method.text,
                    "reply_markup": method.reply_markup,
                }
            )
            return message
        if isinstance(method, AnswerCallbackQuery):
            return True
        raise AssertionError(f"Unexpected Telegram API method call: {type(method)!r}")


def _redact_url(url: str) -> str:
    return url.replace("quiz:quiz@", "***:***@")


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[percentile - 1]


def _latency_summary(values: list[float]) -> LatencySummary:
    return LatencySummary(
        count=len(values),
        p50_ms=round(_percentile(values, 50), 3),
        p95_ms=round(_percentile(values, 95), 3),
        max_ms=round(max(values) if values else 0.0, 3),
    )


def _rss_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if value > 10_000_000:
        return round(value / (1024 * 1024), 2)
    return round(value / 1024, 2)


def _chunks(values: list[int], size: int) -> Iterable[list[int]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _telegram_user_payload(telegram_user_id: int) -> dict[str, object]:
    return {
        "id": telegram_user_id,
        "is_bot": False,
        "first_name": "Capacity",
        "username": None,
        "language_code": "de",
    }


def _private_chat_payload(telegram_user_id: int) -> dict[str, object]:
    return {
        "id": telegram_user_id,
        "type": "private",
        "first_name": "Capacity",
        "username": None,
    }


def _message_update(*, update_id: int, telegram_user_id: int, message_id: int) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "date": int(datetime.now(UTC).timestamp()),
            "chat": _private_chat_payload(telegram_user_id),
            "from": _telegram_user_payload(telegram_user_id),
            "text": "/start",
            "entities": [{"offset": 0, "length": 6, "type": "bot_command"}],
        },
    }


def _callback_update(
    *,
    update_id: int,
    telegram_user_id: int,
    callback_query_id: str,
    data: str,
    message_id: int,
) -> dict[str, object]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": callback_query_id,
            "from": _telegram_user_payload(telegram_user_id),
            "chat_instance": f"capacity-chat-{telegram_user_id}",
            "data": data,
            "message": {
                "message_id": message_id,
                "date": int(datetime.now(UTC).timestamp()),
                "chat": _private_chat_payload(telegram_user_id),
                "text": "capacity callback source",
            },
        },
    }


def _extract_answer_callback(messages: list[dict[str, object]], chat_id: int) -> str:
    for item in reversed(messages):
        if item["chat_id"] != chat_id:
            continue
        markup = item.get("reply_markup")
        rows = getattr(markup, "inline_keyboard", None)
        if not rows:
            continue
        for row in rows:
            for button in row:
                callback_data = getattr(button, "callback_data", None)
                if isinstance(callback_data, str) and callback_data.startswith("answer:"):
                    return callback_data
    raise RuntimeError(f"answer callback not found for chat_id={chat_id}")


async def _post_webhook_update(client: AsyncClient, update_payload: dict[str, object]) -> None:
    response = await client.post(
        "/webhook/telegram",
        json=update_payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
    )
    if response.status_code != 200:
        raise RuntimeError(f"webhook returned {response.status_code}: {response.text}")


def install_webhook_mocks(bot_api: BotApiStub) -> tuple[InProcessUpdateQueue, callable]:
    queue = InProcessUpdateQueue()
    original_route_get_settings = telegram_webhook.get_settings
    original_process_task = telegram_webhook.process_telegram_update
    original_build_bot = telegram_updates.build_bot
    original_bot_call = Bot.__call__

    telegram_webhook.get_settings = lambda: SimpleNamespace(
        telegram_webhook_secret=WEBHOOK_SECRET,
        telegram_webhook_enqueue_timeout_ms=250,
    )
    telegram_webhook.process_telegram_update = queue
    telegram_updates.build_bot = lambda: Bot(token="42:TEST", default=DefaultBotProperties())

    async def fake_bot_call(self: Bot, method: object, request_timeout: int | None = None):
        del self, request_timeout
        return await bot_api.dispatch(method)

    Bot.__call__ = fake_bot_call  # type: ignore[method-assign]

    def restore() -> None:
        telegram_webhook.get_settings = original_route_get_settings
        telegram_webhook.process_telegram_update = original_process_task
        telegram_updates.build_bot = original_build_bot
        Bot.__call__ = original_bot_call  # type: ignore[method-assign]

    return queue, restore


async def assert_safe_target() -> None:
    assert_safe_integration_db(str(engine.url))
    settings = get_settings()
    if "test" not in settings.database_url:
        raise RuntimeError("DATABASE_URL must point to an isolated test database")


async def truncate_test_db() -> None:
    quoted_tables = ", ".join(f"'{table_name}'" for table_name in TRUNCATE_TABLES)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename IN (" + quoted_tables + ")"
            )
        )
        existing = [str(value) for value in result.scalars().all()]

    ordered_existing = [table_name for table_name in TRUNCATE_TABLES if table_name in existing]
    if not ordered_existing:
        return
    async with engine.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE TABLE {', '.join(ordered_existing)} RESTART IDENTITY CASCADE")
        )


async def flush_test_redis() -> int:
    client = redis.Redis.from_url(get_settings().redis_url)
    try:
        await client.flushdb()
        return int(await client.dbsize())
    finally:
        await client.aclose()


async def seed_questions(question_count: int) -> None:
    now_utc = datetime.now(UTC)
    levels = ("A1", "A2", "B1", "B2")
    rows = [
        {
            "question_id": f"capacity-q-{idx:06d}",
            "mode_code": MODE_CODE,
            "source_file": "capacity_synthetic.csv",
            "level": levels[idx % len(levels)],
            "category": f"Capacity-{idx % 25:02d}",
            "question_text": f"Kapazitätsfrage {idx}?",
            "option_1": "der",
            "option_2": "die",
            "option_3": "das",
            "option_4": "den",
            "correct_option_id": idx % 4,
            "correct_answer": ("der", "die", "das", "den")[idx % 4],
            "explanation": "Synthetic capacity audit question.",
            "key": f"capacity-key-{idx:06d}",
            "status": "ACTIVE",
            "quick_mix_eligible": True,
            "created_at": now_utc,
            "updated_at": now_utc,
        }
        for idx in range(question_count)
    ]
    async with engine.begin() as conn:
        for chunk in _chunks(list(range(len(rows))), 5000):
            await conn.execute(insert(QuizQuestion), [rows[idx] for idx in chunk])


async def seed_users(target_count: int, *, existing_count: int) -> None:
    if target_count <= existing_count:
        return
    now_utc = datetime.now(UTC)
    local_day = date.today()
    new_indexes = list(range(existing_count, target_count))
    async with engine.begin() as conn:
        for chunk in _chunks(new_indexes, 5000):
            users = [
                {
                    "id": BASE_USER_ID + idx,
                    "telegram_user_id": BASE_TELEGRAM_ID + idx,
                    "referral_code": f"C{idx:010d}"[-11:],
                    "username": None,
                    "first_name": f"Capacity{idx}",
                    "language_code": "de",
                    "timezone": "Europe/Berlin",
                    "status": "ACTIVE",
                    "created_at": now_utc - timedelta(days=idx % 30),
                    "last_seen_at": now_utc - timedelta(minutes=idx % 1440),
                    "referral_prompt_shown_at": None,
                    "channel_bonus_claimed_at": None,
                }
                for idx in chunk
            ]
            energy = [
                {
                    "user_id": BASE_USER_ID + idx,
                    "free_energy": 10,
                    "paid_energy": 0,
                    "free_cap": 10,
                    "regen_interval_sec": 10_800,
                    "last_regen_at": now_utc,
                    "last_daily_topup_local_date": local_day,
                    "version": 0,
                    "updated_at": now_utc,
                }
                for idx in chunk
            ]
            streaks = [
                {
                    "user_id": BASE_USER_ID + idx,
                    "current_streak": idx % 7,
                    "best_streak": idx % 31,
                    "last_activity_local_date": local_day if idx % 3 == 0 else None,
                    "today_status": "PLAYED" if idx % 3 == 0 else "NO_ACTIVITY",
                    "streak_saver_tokens": 0,
                    "streak_saver_last_purchase_at": None,
                    "premium_freezes_used_week": 0,
                    "premium_freeze_week_start_local_date": None,
                    "version": 0,
                    "updated_at": now_utc,
                }
                for idx in chunk
            ]
            mode_progress = [
                {
                    "user_id": BASE_USER_ID + idx,
                    "mode_code": MODE_CODE,
                    "preferred_level": ("A1", "A2", "B1", "B2")[idx % 4],
                    "mix_step": idx % 3,
                    "correct_in_mix": idx % 2,
                    "created_at": now_utc,
                    "updated_at": now_utc,
                }
                for idx in chunk
            ]
            await conn.execute(insert(User), users)
            await conn.execute(insert(EnergyState), energy)
            await conn.execute(insert(StreakState), streaks)
            await conn.execute(insert(ModeProgress), mode_progress)


async def db_size_mb() -> float:
    async with engine.connect() as conn:
        value = await conn.scalar(text("SELECT pg_database_size(current_database())"))
    return round(float(value or 0) / (1024 * 1024), 3)


async def redis_key_count() -> int:
    client = redis.Redis.from_url(get_settings().redis_url)
    try:
        return int(await client.dbsize())
    finally:
        await client.aclose()


async def lock_snapshot() -> dict[str, int]:
    async with engine.connect() as conn:
        lock_waits = await conn.scalar(
            text(
                "SELECT COUNT(*)::int FROM pg_stat_activity "
                "WHERE wait_event_type = 'Lock' AND state = 'active'"
            )
        )
        deadlocks = await conn.scalar(
            text("SELECT COALESCE(SUM(deadlocks), 0)::bigint FROM pg_stat_database")
        )
    return {"lock_waits_active": int(lock_waits or 0), "deadlocks_total": int(deadlocks or 0)}


async def measure_registered_scale(users: int) -> ScaleResult:
    clear_question_pool_cache()

    started = time.perf_counter()
    async with SessionLocal.begin() as session:
        await session.scalar(select(func.count(User.id)))
    users_count_ms = (time.perf_counter() - started) * 1000

    lookup_times: list[float] = []
    sample_ids = [BASE_TELEGRAM_ID + idx for idx in range(0, users, max(1, users // 50))][:50]
    for telegram_user_id in sample_ids:
        started = time.perf_counter()
        async with SessionLocal.begin() as session:
            await UserOnboardingService.get_by_telegram_user_id(session, telegram_user_id)
        lookup_times.append((time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    async with SessionLocal.begin() as session:
        await session.scalar(select(func.coalesce(func.max(StreakState.best_streak), 0)))
    global_best_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    async with SessionLocal.begin() as session:
        await session.scalar(select(func.count(User.id)))
        await session.scalar(select(func.count(QuizSession.id)))
        await session.scalar(select(func.count(QuizAttempt.id)))
    public_stats_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    async with SessionLocal.begin() as session:
        await select_question_for_mode(
            session,
            MODE_CODE,
            local_date_berlin=date.today(),
            recent_question_ids=(),
            selection_seed=f"scale:{users}",
            preferred_level=None,
        )
    question_pool_warm_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    build_dispatcher()
    dispatcher_build_ms = (time.perf_counter() - started) * 1000

    return ScaleResult(
        users=users,
        db_size_mb=await db_size_mb(),
        users_count_ms=round(users_count_ms, 3),
        user_lookup_p95_ms=round(_percentile(lookup_times, 95), 3),
        global_best_ms=round(global_best_ms, 3),
        public_stats_ms=round(public_stats_ms, 3),
        question_pool_warm_ms=round(question_pool_warm_ms, 3),
        dispatcher_build_ms=round(dispatcher_build_ms, 3),
        redis_keys=await redis_key_count(),
        rss_mb=_rss_mb(),
    )


async def service_flow_for_user(index: int) -> None:
    user_id = BASE_USER_ID + index
    telegram_user = SimpleNamespace(
        id=BASE_TELEGRAM_ID + index,
        username=None,
        first_name=f"Capacity{index}",
        language_code="de",
    )
    now_utc = datetime.now(UTC)
    async with SessionLocal.begin() as session:
        with query_step("home_snapshot_start"):
            snapshot = await UserOnboardingService.ensure_home_snapshot(
                session,
                telegram_user=telegram_user,
            )
        with query_step("quiz_open_start_session"):
            started = await GameSessionService.start_session(
                session,
                user_id=snapshot.user_id,
                mode_code=MODE_CODE,
                source=SOURCE,
                idempotency_key=f"audit:start:{index}",
                now_utc=now_utc,
            )

    async with SessionLocal.begin() as session:
        with query_step("answer_user_touch"):
            user = await UserOnboardingService.touch_existing_user(
                session,
                telegram_user=telegram_user,
                now_utc=datetime.now(UTC),
            )
            if user is None:
                raise RuntimeError(f"synthetic user missing: index={index}")
        with query_step("answer_callback_submit"):
            answered = await GameSessionService.submit_answer(
                session,
                user_id=user.id,
                session_id=started.session.session_id,
                selected_option=index % 4,
                idempotency_key=f"audit:answer:{started.session.session_id}:{index % 4}",
                now_utc=datetime.now(UTC),
            )
        with query_step("post_game_prompts"):
            show_bonus = await ChannelBonusService.should_show_post_game_prompt(
                session,
                user_id=user_id,
                idempotent_replay=answered.idempotent_replay,
            )
            if not show_bonus:
                await ReferralService.reserve_post_game_prompt(
                    session,
                    user_id=user_id,
                    now_utc=datetime.now(UTC),
                )

    async with SessionLocal.begin() as session:
        with query_step("next_question_start_session"):
            await GameSessionService.start_session(
                session,
                user_id=user_id,
                mode_code=answered.mode_code,
                source=answered.source,
                idempotency_key=f"audit:start:auto:{index}",
                now_utc=datetime.now(UTC),
                preferred_question_level=answered.next_preferred_level,
                recent_question_ids_override=(answered.question_id,),
            )


async def webhook_flow_for_user(
    *,
    index: int,
    client: AsyncClient,
    queue: InProcessUpdateQueue,
    bot_api: BotApiStub,
) -> None:
    telegram_user_id = BASE_TELEGRAM_ID + index
    first_update_id = BASE_UPDATE_ID + index * 10
    await _post_webhook_update(
        client,
        _message_update(
            update_id=first_update_id,
            telegram_user_id=telegram_user_id,
            message_id=10 + index,
        ),
    )
    await queue.drain_update(first_update_id)
    await _post_webhook_update(
        client,
        _callback_update(
            update_id=first_update_id + 1,
            telegram_user_id=telegram_user_id,
            callback_query_id=f"capacity-play-{index}",
            data="play",
            message_id=20 + index,
        ),
    )
    await queue.drain_update(first_update_id + 1)
    answer_callback = _extract_answer_callback(bot_api.sent_messages, telegram_user_id)
    await _post_webhook_update(
        client,
        _callback_update(
            update_id=first_update_id + 2,
            telegram_user_id=telegram_user_id,
            callback_query_id=f"capacity-answer-{index}",
            data=answer_callback,
            message_id=30 + index,
        ),
    )
    await queue.drain_update(first_update_id + 2)


async def run_active_stage(
    active_users: int,
    *,
    flow: str,
    max_concurrency: int,
    start_index: int = 0,
    bot_api: BotApiStub | None = None,
) -> ActiveResult:
    latencies: list[float] = []
    errors = 0
    before_locks = await lock_snapshot()
    before_attempt_id = await _max_attempt_id()
    before_update_id = await _max_processed_update_id()
    if bot_api is not None:
        bot_api.reset()

    async def run_one(index: int, client: AsyncClient | None, queue: InProcessUpdateQueue | None):
        nonlocal errors
        started_at = time.perf_counter()
        try:
            if flow == "webhook":
                if client is None or queue is None or bot_api is None:
                    raise RuntimeError("webhook flow is not configured")
                await webhook_flow_for_user(
                    index=index,
                    client=client,
                    queue=queue,
                    bot_api=bot_api,
                )
            else:
                await service_flow_for_user(index)
        except Exception:
            errors += 1
        finally:
            latencies.append((time.perf_counter() - started_at) * 1000)

    semaphore = asyncio.Semaphore(max(1, min(max_concurrency, active_users)))

    async def limited(index: int, client: AsyncClient | None, queue: InProcessUpdateQueue | None):
        async with semaphore:
            await run_one(index, client, queue)

    with QueryRecorder() as recorder:
        if flow == "webhook":
            if bot_api is None:
                raise RuntimeError("bot_api is required for webhook flow")
            queue, restore = install_webhook_mocks(bot_api)
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
                    base_url="http://testserver",
                    timeout=30.0,
                ) as client:
                    await asyncio.gather(
                        *(
                            limited(index, client, queue)
                            for index in range(start_index, start_index + active_users)
                        )
                    )
            finally:
                restore()
        else:
            await asyncio.gather(
                *(
                    limited(index, None, None)
                    for index in range(start_index, start_index + active_users)
                )
            )

    after_locks = await lock_snapshot()
    return ActiveResult(
        active_users=active_users,
        flow=flow,
        latency=_latency_summary(latencies),
        errors=errors,
        query_summary=recorder.summary(),
        db_lock_waits_active=after_locks["lock_waits_active"],
        deadlocks_delta=after_locks["deadlocks_total"] - before_locks["deadlocks_total"],
        outbound_calls=dict(
            bot_api.calls if bot_api is not None else _estimated_service_calls(active_users)
        ),
        query_steps=recorder.step_summaries(),
        query_categories=recorder.category_summaries(),
        top_queries=recorder.top_queries(),
        top_queries_by_count=recorder.top_queries_by_count(),
        attempts_created=await _count_attempts_after(before_attempt_id),
        duplicate_answer_groups=await _count_duplicate_answer_groups(),
        processed_updates=await _processed_update_status_counts_after(before_update_id),
        rss_mb=_rss_mb(),
    )


def _estimated_service_calls(active_users: int) -> Counter[str]:
    return Counter(
        {
            "estimated_sendMessage": active_users * 3,
            "estimated_answerCallbackQuery": active_users * 2,
        }
    )


async def _max_attempt_id() -> int:
    async with SessionLocal.begin() as session:
        value = await session.scalar(select(func.coalesce(func.max(QuizAttempt.id), 0)))
    return int(value or 0)


async def _max_processed_update_id() -> int:
    async with SessionLocal.begin() as session:
        value = await session.scalar(select(func.coalesce(func.max(ProcessedUpdate.update_id), 0)))
    return int(value or 0)


async def _count_attempts_after(min_id: int) -> int:
    async with SessionLocal.begin() as session:
        value = await session.scalar(
            select(func.count(QuizAttempt.id)).where(QuizAttempt.id > min_id)
        )
    return int(value or 0)


async def _count_duplicate_answer_groups() -> int:
    grouped = (
        select(QuizAttempt.idempotency_key)
        .group_by(QuizAttempt.idempotency_key)
        .having(func.count(QuizAttempt.id) > 1)
        .subquery()
    )
    async with SessionLocal.begin() as session:
        value = await session.scalar(select(func.count()).select_from(grouped))
    return int(value or 0)


async def _processed_update_status_counts_after(min_update_id: int) -> dict[str, int]:
    async with SessionLocal.begin() as session:
        rows = (
            await session.execute(
                select(ProcessedUpdate.status, func.count(ProcessedUpdate.update_id))
                .where(ProcessedUpdate.update_id > min_update_id)
                .group_by(ProcessedUpdate.status)
            )
        ).all()
    return {status: int(total) for status, total in rows}


async def explain_hot_queries() -> dict[str, list[str]]:
    statements = {
        "global_best_streak": "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) "
        "SELECT COALESCE(MAX(best_streak), 0) FROM streak_state",
        "user_lookup": "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) "
        f"SELECT * FROM users WHERE telegram_user_id = {BASE_TELEGRAM_ID}",
        "recent_attempts": "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) "
        f"SELECT qa.question_id FROM quiz_attempts qa "
        f"JOIN quiz_sessions qs ON qa.session_id = qs.id "
        f"WHERE qa.user_id = {BASE_USER_ID} AND qs.mode_code = '{MODE_CODE}' "
        "ORDER BY qa.answered_at DESC LIMIT 20",
    }
    result: dict[str, list[str]] = {}
    async with engine.connect() as conn:
        for name, statement in statements.items():
            rows = (await conn.execute(text(statement))).all()
            result[name] = [str(row[0]) for row in rows]
    return result


def gate_failed(result: ActiveResult, *, max_p95_ms: float) -> bool:
    return (
        result.errors > 0
        or result.duplicate_answer_groups > 0
        or result.deadlocks_delta > 0
        or result.latency.p95_ms > max_p95_ms
    )


def functional_gate_failed(result: ActiveResult) -> bool:
    return result.errors > 0 or result.duplicate_answer_groups > 0 or result.deadlocks_delta > 0


async def run_audit(args: argparse.Namespace) -> AuditReport:
    await assert_safe_target()
    await truncate_test_db()
    await flush_test_redis()
    await seed_questions(args.questions)

    report = AuditReport(
        started_at=datetime.now(UTC).isoformat(),
        database_url_redacted=_redact_url(str(engine.url)),
        redis_url_redacted=_redact_url(get_settings().redis_url),
    )

    existing_users = 0
    for users in args.registered_scales:
        started_at = time.perf_counter()
        await seed_users(users, existing_count=existing_users)
        existing_users = users
        seed_ms = (time.perf_counter() - started_at) * 1000
        scale_result = await measure_registered_scale(users)
        report.registered_scales.append(scale_result)
        report.notes.append(f"seeded_registered_users={users} seed_ms={seed_ms:.3f}")

    bot_api = BotApiStub()
    active_index_offset = 0
    if args.webhook_smoke_users > 0:
        smoke = await run_active_stage(
            args.webhook_smoke_users,
            flow="webhook",
            max_concurrency=min(args.webhook_smoke_users, args.max_concurrency),
            start_index=active_index_offset,
            bot_api=bot_api,
        )
        active_index_offset += args.webhook_smoke_users
        report.active_tests.append(smoke)
        if functional_gate_failed(smoke):
            report.notes.append("Gate stopped after webhook smoke failure.")
            return report

    for active_users in args.active_users:
        result = await run_active_stage(
            active_users,
            flow=args.active_flow,
            max_concurrency=args.max_concurrency,
            start_index=active_index_offset,
            bot_api=bot_api if args.active_flow == "webhook" else None,
        )
        active_index_offset += active_users
        report.active_tests.append(result)
        if gate_failed(result, max_p95_ms=args.max_p95_ms):
            report.notes.append(f"Gate stopped at active_users={active_users}.")
            break

    report.notes.append("explain_hot_queries=" + json.dumps(await explain_hot_queries()))
    return report


def _parse_int_list(raw_value: str) -> list[int]:
    return [int(item.strip()) for item in raw_value.split(",") if item.strip()]


def _json_default(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local synthetic capacity audit.")
    parser.add_argument("--registered-scales", default="1000,10000,100000")
    parser.add_argument("--active-users", default="50,100,250,500,1000")
    parser.add_argument("--active-flow", choices=("service", "webhook"), default="service")
    parser.add_argument("--webhook-smoke-users", type=int, default=10)
    parser.add_argument("--max-concurrency", type=int, default=100)
    parser.add_argument("--max-p95-ms", type=float, default=2000.0)
    parser.add_argument("--questions", type=int, default=5000)
    parser.add_argument("--output", default="reports/load_capacity_audit_latest.json")
    args = parser.parse_args()
    args.registered_scales = _parse_int_list(args.registered_scales)
    args.active_users = _parse_int_list(args.active_users)

    report = asyncio.run(run_audit(args))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, default=_json_default, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, default=_json_default, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
