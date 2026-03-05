from __future__ import annotations

from zoneinfo import ZoneInfo

from aiogram.types import CallbackQuery, Message

from app.bot.handlers.gameplay_flows.tournament_views import format_points
from app.bot.keyboards.daily_cup import build_daily_cup_lobby_keyboard, build_daily_cup_share_url
from app.bot.texts.de import TEXTS_DE
from app.core.telegram_links import public_bot_link
from app.workers.tasks.tournaments_messaging_text import (
    format_deadline,
    is_message_not_modified_error,
)

_BERLIN_TZ = ZoneInfo("Europe/Berlin")


def _build_roster_lines(
    *, participant_labels: list[tuple[int, str]], viewer_user_id: int
) -> list[str]:
    lines = [f"Teilnehmer: {len(participant_labels)}", ""]
    for user_id, label in participant_labels:
        suffix = " (Du)" if user_id == viewer_user_id else ""
        lines.append(f"• {label} ✅{suffix}")
    if viewer_user_id not in {user_id for user_id, _ in participant_labels}:
        lines.append("• Du?")
    return lines


def _build_standings_lines(
    *,
    participant_labels: list[tuple[int, str]],
    participant_points: dict[int, str],
    viewer_user_id: int,
    participant_tie_breaks: dict[int, str] | None = None,
) -> list[str]:
    lines: list[str] = []
    for index, (user_id, label) in enumerate(participant_labels, start=1):
        medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else " "
        you = " (Du)" if user_id == viewer_user_id else ""
        points = participant_points.get(user_id, "0")
        tie_break_suffix = ""
        if participant_tie_breaks is not None:
            tie_break_suffix = f" · TB {participant_tie_breaks.get(user_id, '0')}"
        lines.append(f"{index}. {medal} {label}{you} - {points} Pkt{tie_break_suffix}")
    return lines


async def render_daily_cup_lobby(
    callback: CallbackQuery,
    *,
    lobby,
    user_id: int,
    labels: dict[int, str],
    replace_current_message: bool = False,
) -> None:
    if callback.message is None:
        return
    participant_labels = [
        (item.user_id, labels.get(item.user_id, "Spieler")) for item in lobby.participants
    ]
    body_lines = [
        "🏆 Daily Arena Cup",
        "",
        "Format: 5 Fragen • 3 Runden",
    ]
    if lobby.tournament.status == "REGISTRATION":
        if lobby.viewer_joined:
            body_lines.extend([TEXTS_DE["msg.daily_cup.registered_waiting"], ""])
        else:
            body_lines.extend([TEXTS_DE["msg.daily_cup.invite_open_rules"], ""])
        body_lines.extend(
            _build_roster_lines(participant_labels=participant_labels, viewer_user_id=user_id)
        )
    else:
        round_no = max(1, int(lobby.tournament.current_round))
        if lobby.tournament.status == "COMPLETED":
            points_map = {item.user_id: format_points(item.score) for item in lobby.participants}
            tie_break_map = {
                item.user_id: format_points(item.tie_break) for item in lobby.participants
            }
            standings_lines = _build_standings_lines(
                participant_labels=participant_labels,
                participant_points=points_map,
                viewer_user_id=user_id,
                participant_tie_breaks=tie_break_map,
            )
            standings_user_ids = [item.user_id for item in lobby.participants]
            place = standings_user_ids.index(user_id) + 1
            top_3 = standings_lines[:3]
            while len(top_3) < 3:
                top_3.append("—")
            body_lines.extend(
                [
                    TEXTS_DE["msg.daily_cup.final_results"].format(
                        top_1=top_3[0],
                        top_2=top_3[1],
                        top_3=top_3[2],
                        place=place,
                        score=points_map.get(user_id, "0"),
                    ),
                    "",
                    "📊 Endtabelle",
                    *standings_lines,
                ]
            )
        else:
            if lobby.viewer_current_match_challenge_id is not None:
                opponent_label = (
                    labels.get(lobby.viewer_current_opponent_user_id, "Gegner")
                    if lobby.viewer_current_opponent_user_id is not None
                    else "Gegner"
                )
                body_lines.extend(
                    [
                        TEXTS_DE["msg.daily_cup.round_active_with_opponent"].format(
                            opponent_label=opponent_label
                        ),
                        "",
                    ]
                )
            elif round_no >= 3:
                body_lines.extend([TEXTS_DE["msg.daily_cup.waiting_completion"], ""])
            else:
                body_lines.extend(
                    [
                        TEXTS_DE["msg.daily_cup.waiting_next_round"].format(
                            round_no=round_no,
                            next_round_time=(
                                lobby.tournament.round_deadline.astimezone(_BERLIN_TZ).strftime(
                                    "%H:%M"
                                )
                                if lobby.tournament.round_deadline is not None
                                else "-"
                            ),
                        ),
                        "",
                    ]
                )
            body_lines.extend(
                [
                    f"Runde {round_no}/3",
                    f"Deadline: {format_deadline(lobby.tournament.round_deadline)} (Berlin)",
                    "",
                ]
            )
            points_map = {item.user_id: format_points(item.score) for item in lobby.participants}
            body_lines.extend(
                _build_standings_lines(
                    participant_labels=participant_labels,
                    participant_points=points_map,
                    viewer_user_id=user_id,
                    participant_tie_breaks=None,
                )
            )

    play_challenge_id = (
        str(lobby.viewer_current_match_challenge_id)
        if lobby.viewer_current_match_challenge_id is not None
        else None
    )
    share_url: str | None = None
    if lobby.tournament.status == "COMPLETED" and lobby.viewer_joined:
        standings_user_ids = [item.user_id for item in lobby.participants]
        place = standings_user_ids.index(user_id) + 1
        points_map = {item.user_id: format_points(item.score) for item in lobby.participants}
        share_url = build_daily_cup_share_url(
            base_link=public_bot_link(),
            share_text=TEXTS_DE["msg.daily_cup.share_template"].format(
                place=place,
                total=len(standings_user_ids),
                points=points_map.get(user_id, "0"),
            ),
        )
    keyboard = build_daily_cup_lobby_keyboard(
        tournament_id=str(lobby.tournament.tournament_id),
        can_join=lobby.tournament.status == "REGISTRATION" and not lobby.viewer_joined,
        play_challenge_id=play_challenge_id,
        show_share_result=lobby.tournament.status == "COMPLETED" and lobby.viewer_joined,
        show_proof_card=lobby.tournament.status == "COMPLETED" and lobby.viewer_joined,
        share_url=share_url,
    )
    rendered_text = "\n".join(body_lines)
    if replace_current_message and isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(rendered_text, reply_markup=keyboard)
            return
        except Exception as exc:
            if is_message_not_modified_error(exc):
                return
    await callback.message.answer(rendered_text, reply_markup=keyboard)
