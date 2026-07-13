from __future__ import annotations

from uuid import uuid4

from app.db.session import SessionLocal
from app.services.messaging_repair_queries import load_tournament_expected_targets


async def test_repair_target_query_accepts_public_uuid_string() -> None:
    async with SessionLocal() as session:
        targets = await load_tournament_expected_targets(
            session,
            flow="daily_cup_round_messaging",
            tournament_id=str(uuid4()),
        )

    assert targets == []
