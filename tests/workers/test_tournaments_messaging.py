from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest

from app.workers.tasks import tournaments_messaging
from app.workers.tasks import tournaments_messaging_delivery_runtime as private_runtime


@pytest.mark.asyncio
async def test_private_delivery_continues_after_recipient_system_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processed_user_ids: list[int] = []
    bot = SimpleNamespace(session=SimpleNamespace(close=_async_noop))

    async def _deliver(*, user_id: int, **_kwargs: Any) -> None:
        processed_user_ids.append(user_id)
        if user_id == 2:
            raise RuntimeError("private persistence failed")

    monkeypatch.setattr(private_runtime, "_deliver_user_message", _deliver)
    request = cast(
        Any,
        SimpleNamespace(
            context=SimpleNamespace(
                parsed_tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                tournament=SimpleNamespace(),
                standings_user_ids=[1, 2, 3],
            ),
            build_bot_fn=lambda: bot,
        ),
    )
    operations = cast(
        Any,
        SimpleNamespace(content_version=lambda **_kwargs: "round:1"),
    )

    with pytest.raises(RuntimeError, match="private persistence failed"):
        await private_runtime.deliver_round_messages_with_dependencies(
            request=request,
            operations=operations,
        )

    assert processed_user_ids == [1, 2, 3]


@pytest.mark.asyncio
async def test_private_payload_failure_happens_before_pending_claim() -> None:
    call_order: list[str] = []

    def _payload(**_kwargs: Any) -> tuple[str, object]:
        call_order.append("payload")
        raise RuntimeError("payload failed")

    async def _prepare(**_kwargs: Any) -> object:
        call_order.append("prepare")
        return SimpleNamespace(should_send=False)

    context = SimpleNamespace(
        telegram_targets={1: 101},
        participant_rows={1: SimpleNamespace(standings_message_id=None)},
    )
    operations = SimpleNamespace(
        build_target=lambda **_kwargs: SimpleNamespace(idempotency_key="delivery"),
        delivery_operation=lambda _message_id: "send",
        build_payload=_payload,
        prepare_delivery=_prepare,
    )
    delivery_context = cast(
        Any,
        SimpleNamespace(
            request=SimpleNamespace(context=context),
            operations=operations,
            happened_at=object(),
        ),
    )

    with pytest.raises(RuntimeError, match="payload failed"):
        await private_runtime._deliver_user_message(
            delivery_context=delivery_context,
            state=cast(Any, SimpleNamespace(skipped=0)),
            user_id=1,
        )

    assert call_order == ["payload"]


def test_private_tournament_worker_share_url_uses_canonical_telegram_contract() -> None:
    share_url = tournaments_messaging._build_standings_share_url(
        invite_code="abcdefabcdef",
        tournament_name="Liga Finale",
    )

    parsed = urlparse(share_url)
    query = parse_qs(parsed.query)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://t.me/share/url"
    assert query["url"] == ["https://t.me/Deine_Deutsch_Quiz_bot?start=tournament_abcdefabcdef"]
    assert query["text"] == ["🏆 Ich spiele im Liga Finale! Komm dazu →"]


async def _async_noop() -> None:
    return None
