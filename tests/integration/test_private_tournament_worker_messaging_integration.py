from __future__ import annotations

from tests.integration.private_tournament_worker_integration_support import (
    UTC,
    UUID,
    SessionLocal,
    TournamentParticipantsRepo,
    _create_user,
    _DummyWorkerBot,
    _ensure_tournament_schema,
    _seed_friend_challenge_questions,
    as_any_dict,
    create_private_tournament,
    datetime,
    join_private_tournament_by_code,
    pytest,
    start_private_tournament,
    tournaments_messaging,
)


@pytest.mark.asyncio
async def test_round_messaging_sends_once_then_updates_by_edit(monkeypatch) -> None:
    now_utc = datetime.now(UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    creator_user_id = await _create_user("private_tournament_round_msg_creator")
    opponent_user_id = await _create_user("private_tournament_round_msg_opponent")

    async with SessionLocal.begin() as session:
        tournament = await create_private_tournament(
            session,
            created_by=creator_user_id,
            format_code="QUICK_5",
            now_utc=now_utc,
        )
        await join_private_tournament_by_code(
            session,
            user_id=opponent_user_id,
            invite_code=tournament.invite_code,
            now_utc=now_utc,
        )
        await start_private_tournament(
            session,
            creator_user_id=creator_user_id,
            tournament_id=tournament.tournament_id,
            now_utc=now_utc,
        )
        tournament_id = str(tournament.tournament_id)

    bot = _DummyWorkerBot()
    monkeypatch.setattr(tournaments_messaging, "build_bot", lambda: bot)

    first = as_any_dict(
        await tournaments_messaging.run_private_tournament_round_messaging_async(
            tournament_id=tournament_id
        )
    )
    assert int(first["sent"]) == 2
    assert int(first["edited"]) == 0
    assert len(bot.send_messages) == 2
    assert any("Runde 1/3 gestartet" in str(item.get("text")) for item in bot.send_messages)
    callbacks = [
        button.callback_data
        for row in bot.send_messages[0]["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    urls = [
        button.url
        for row in bot.send_messages[0]["reply_markup"].inline_keyboard
        for button in row
        if button.url
    ]
    assert any(callback.startswith("friend:next:") for callback in callbacks)
    assert any(url and "https://t.me/share/url" in url for url in urls)

    second = as_any_dict(
        await tournaments_messaging.run_private_tournament_round_messaging_async(
            tournament_id=tournament_id
        )
    )
    assert int(second["sent"]) == 0
    assert int(second["edited"]) == 2
    assert len(bot.edit_messages) == 2

    async with SessionLocal.begin() as session:
        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=UUID(tournament_id),
        )
        assert all(item.standings_message_id is not None for item in participants)
