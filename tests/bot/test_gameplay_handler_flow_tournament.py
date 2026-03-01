from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay, gameplay_tournaments, gameplay_tournaments_more
from app.bot.handlers.gameplay_flows import tournament_lobby_flow
from app.bot.texts.de import TEXTS_DE
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


@pytest.mark.asyncio
async def test_handle_tournament_create_from_format_sends_share_lobby(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=17)

    async def _fake_create_tournament(*args, **kwargs):
        return SimpleNamespace(
            format="QUICK_5",
            invite_code="abcdefabcdef",
            tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        )

    async def _fake_invite_link(callback, *, invite_code: str):
        del callback
        assert invite_code == "abcdefabcdef"
        return "https://t.me/testbot?start=tournament_abcdefabcdef"

    emitted: list[str] = []

    async def _fake_emit(*args, **kwargs):
        emitted.append(str(kwargs.get("event_type")))

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay_tournaments,
        "TournamentServiceFacade",
        SimpleNamespace(create_private_tournament=_fake_create_tournament),
    )
    monkeypatch.setattr(
        gameplay_tournaments.gameplay_helpers,
        "_build_tournament_invite_link",
        _fake_invite_link,
    )
    monkeypatch.setattr(gameplay, "emit_analytics_event", _fake_emit)

    callback = DummyCallback(
        data="friend:tournament:format:5",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay_tournaments.handle_tournament_create_from_format(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.tournament.created"]
    urls = [button.url for row in response.kwargs["reply_markup"].inline_keyboard for button in row]
    assert any(url and "https://t.me/share/url" in url for url in urls)
    assert emitted == ["private_tournament_created"]


@pytest.mark.asyncio
async def test_handle_tournament_share_result_sends_share_keyboard_and_emits_event(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=17)

    async def _fake_lobby(*args, **kwargs):
        return SimpleNamespace(
            tournament=SimpleNamespace(status="COMPLETED"),
            participants=(
                SimpleNamespace(user_id=17, score=Decimal("2")),
                SimpleNamespace(user_id=18, score=Decimal("1")),
            ),
            viewer_joined=True,
        )

    async def _fake_share_url(callback, *, share_text: str):
        del callback
        assert "#1" in share_text
        return "https://t.me/share/url?url=x&text=y"

    emitted: list[str] = []

    async def _fake_emit(*args, **kwargs):
        emitted.append(str(kwargs.get("event_type")))

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay_tournaments_more,
        "TournamentServiceFacade",
        SimpleNamespace(get_private_tournament_lobby_by_id=_fake_lobby),
    )
    monkeypatch.setattr(
        gameplay_tournaments_more,
        "_build_tournament_share_result_url",
        _fake_share_url,
    )
    monkeypatch.setattr(gameplay, "emit_analytics_event", _fake_emit)

    callback = DummyCallback(
        data="friend:tournament:share:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay_tournaments.handle_tournament_share(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.tournament.share.ready"]
    urls = [button.url for row in response.kwargs["reply_markup"].inline_keyboard for button in row]
    assert any(url and "https://t.me/share/url" in url for url in urls)
    assert emitted == ["private_tournament_result_shared"]


@pytest.mark.asyncio
async def test_handle_tournament_start_enqueues_round_messaging(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=17)

    async def _fake_start(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(round_no=1, matches_total=1)

    async def _fake_lobby(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(
            tournament=SimpleNamespace(
                tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                invite_code="abcdefabcdef",
                name="Freunde",
                format="QUICK_5",
                max_participants=8,
                current_round=1,
                status="ROUND_1",
            ),
            participants=(
                SimpleNamespace(user_id=17, score=Decimal("1")),
                SimpleNamespace(user_id=18, score=Decimal("0")),
            ),
            viewer_joined=True,
            viewer_is_creator=True,
            can_start=False,
            viewer_current_match_challenge_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            viewer_current_opponent_user_id=18,
        )

    async def _fake_list_by_ids(*args, **kwargs):
        del args, kwargs
        return [
            SimpleNamespace(id=17, username="alice", first_name="Alice"),
            SimpleNamespace(id=18, username="bob", first_name="Bob"),
        ]

    emitted: list[str] = []
    enqueued: list[str] = []

    async def _fake_emit(*args, **kwargs):
        emitted.append(str(kwargs.get("event_type")))

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay_tournaments,
        "TournamentServiceFacade",
        SimpleNamespace(
            start_private_tournament=_fake_start,
            get_private_tournament_lobby_by_id=_fake_lobby,
        ),
    )
    monkeypatch.setattr(
        gameplay_tournaments,
        "UsersRepo",
        SimpleNamespace(list_by_ids=_fake_list_by_ids),
    )
    monkeypatch.setattr(gameplay, "emit_analytics_event", _fake_emit)
    monkeypatch.setattr(
        tournament_lobby_flow.gameplay_tournament_notifications,
        "enqueue_tournament_round_messaging",
        lambda *, tournament_id: enqueued.append(tournament_id),
    )

    callback = DummyCallback(
        data="friend:tournament:start:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay_tournaments.handle_tournament_start(callback)

    assert callback.message.answers[0].text == TEXTS_DE["msg.tournament.started"]
    assert emitted == ["private_tournament_started"]
    assert enqueued == ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]


@pytest.mark.asyncio
async def test_handle_tournament_join_notifies_creator_about_new_participant(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=77)

    async def _fake_join(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(joined_now=True)

    async def _fake_lobby(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(
            tournament=SimpleNamespace(
                tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                invite_code="abcdefabcdef",
                created_by=17,
                name="Freunde",
                format="QUICK_5",
                max_participants=8,
                current_round=0,
                status="REGISTRATION",
            ),
            participants=(
                SimpleNamespace(user_id=17, score=Decimal("0")),
                SimpleNamespace(user_id=77, score=Decimal("0")),
            ),
            viewer_joined=True,
            viewer_is_creator=False,
            can_start=False,
            viewer_current_match_challenge_id=None,
            viewer_current_opponent_user_id=None,
        )

    async def _fake_list_by_ids(*args, **kwargs):
        del args, kwargs
        return [
            SimpleNamespace(id=17, username="alice", first_name="Alice"),
            SimpleNamespace(id=77, username="bob", first_name="Bob"),
        ]

    async def _fake_get_by_id(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(id=17, telegram_user_id=555)

    async def _fake_emit(*args, **kwargs):
        del args, kwargs
        return None

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay_tournaments,
        "TournamentServiceFacade",
        SimpleNamespace(
            join_private_tournament_by_code=_fake_join,
            get_private_tournament_lobby_by_invite_code=_fake_lobby,
        ),
    )
    monkeypatch.setattr(
        gameplay_tournaments,
        "UsersRepo",
        SimpleNamespace(list_by_ids=_fake_list_by_ids, get_by_id=_fake_get_by_id),
    )
    monkeypatch.setattr(gameplay, "emit_analytics_event", _fake_emit)

    callback = DummyCallback(
        data="friend:tournament:join:abcdefabcdef",
        from_user=SimpleNamespace(id=77, first_name="Tom"),
        message=DummyMessage(),
    )
    await gameplay_tournaments.handle_tournament_join(callback)

    assert callback.message.answers[0].text == TEXTS_DE["msg.tournament.joined"]
    assert len(callback.bot.sent_messages) == 1
    creator_notice = callback.bot.sent_messages[0]
    assert "hat dein Turnier betreten" in str(creator_notice.get("text"))
    markup = creator_notice.get("reply_markup")
    assert markup is not None
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "friend:tournament:start:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
