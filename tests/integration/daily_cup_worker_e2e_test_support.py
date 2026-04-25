from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models.energy_state import EnergyState
from app.db.models.entitlements import Entitlement
from app.db.models.quiz_questions import QuizQuestion
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.settlement import settle_pending_match_from_duel

UTC = timezone.utc


class FrozenWorkerDateTime(datetime):
    current = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        if tz is None:
            return cls.current.replace(tzinfo=None)
        return cls.current.astimezone(tz)


def build_b2_question(*, question_id: str, now_utc: datetime) -> QuizQuestion:
    return QuizQuestion(
        question_id=question_id,
        mode_code="QUICK_MIX_A1A2",
        source_file="daily_cup_b2_seed.csv",
        level="B2",
        category="DailyCupB2",
        question_text=f"B2 Frage {question_id}?",
        option_1="A",
        option_2="B",
        option_3="C",
        option_4="D",
        correct_option_id=0,
        correct_answer="A",
        explanation="Seed",
        key=question_id,
        status="ACTIVE",
        quick_mix_eligible=True,
        created_at=now_utc,
        updated_at=now_utc,
    )


async def seed_daily_cup_b2_questions(*, now_utc: datetime) -> None:
    async with SessionLocal.begin() as session:
        session.add_all(
            [
                build_b2_question(question_id=f"fc_b2_{index:03d}", now_utc=now_utc)
                for index in range(1, 7)
            ]
        )


async def get_active_premium_scope(*, user_id: int) -> str | None:
    async with SessionLocal.begin() as session:
        entitlement = await session.scalar(
            select(Entitlement).where(
                Entitlement.user_id == user_id,
                Entitlement.entitlement_type == "PREMIUM",
                Entitlement.status == "ACTIVE",
            )
        )
        return None if entitlement is None else str(entitlement.scope)


async def count_duel_tickets(*, user_id: int) -> int:
    async with SessionLocal.begin() as session:
        return await PurchasesRepo.count_credited_product(
            session,
            user_id=user_id,
            product_code="FRIEND_CHALLENGE_5",
        )


async def get_free_energy(*, user_id: int) -> int | None:
    async with SessionLocal.begin() as session:
        state = await session.get(EnergyState, user_id)
        return None if state is None else int(state.free_energy)


async def get_energy_balance(*, user_id: int) -> tuple[int, int] | None:
    async with SessionLocal.begin() as session:
        state = await session.get(EnergyState, user_id)
        if state is None:
            return None
        return int(state.free_energy), int(state.paid_energy)


async def round_question_ids(*, tournament_id, round_no: int) -> tuple[tuple[str, ...], ...]:
    async with SessionLocal.begin() as session:
        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=round_no,
        )
        assert matches
        question_sets: list[tuple[str, ...]] = []
        for match in matches:
            assert match.friend_challenge_id is not None
            challenge = await FriendChallengesRepo.get_by_id(session, match.friend_challenge_id)
            assert challenge is not None
            assert challenge.question_ids
            question_sets.append(tuple(str(question_id) for question_id in challenge.question_ids))
        return tuple(question_sets)


async def settle_round_with_lowest_user_wins(
    *,
    tournament_id,
    round_no: int,
    settled_at: datetime,
) -> None:
    expired_deadline = settled_at - timedelta(minutes=1)
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        tournament.round_deadline = expired_deadline
        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=round_no,
        )
        assert matches
        for match in matches:
            match.deadline = expired_deadline
            assert match.friend_challenge_id is not None
            challenge = await FriendChallengesRepo.get_by_id_for_update(
                session,
                match.friend_challenge_id,
            )
            assert challenge is not None

            if match.user_b is None:
                winner_user_id = int(match.user_a)
                challenge.status = "COMPLETED"
                challenge.winner_user_id = winner_user_id
                challenge.creator_score = 7
                challenge.opponent_score = 0
                challenge.creator_finished_at = settled_at
                challenge.opponent_finished_at = settled_at
                challenge.completed_at = settled_at
                challenge.updated_at = settled_at
                assert await settle_pending_match_from_duel(
                    session, match=match, now_utc=settled_at
                )
                continue

            winner_user_id = min(int(match.user_a), int(match.user_b))
            challenge.status = "COMPLETED"
            challenge.winner_user_id = winner_user_id
            if int(challenge.creator_user_id) == winner_user_id:
                challenge.creator_score = 7
                challenge.opponent_score = 4
            else:
                challenge.creator_score = 4
                challenge.opponent_score = 7
            challenge.creator_finished_at = settled_at
            challenge.opponent_finished_at = settled_at
            challenge.completed_at = settled_at
            challenge.updated_at = settled_at
            assert await settle_pending_match_from_duel(session, match=match, now_utc=settled_at)
