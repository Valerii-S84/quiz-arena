from __future__ import annotations

from zoneinfo import ZoneInfo

from aiogram.types import CallbackQuery, Message

from app.bot.handlers.gameplay_flows.tournament_views import format_points
from app.bot.keyboards.daily_cup import build_daily_cup_lobby_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.tournaments.constants import (
    TOURNAMENT_SELF_BOT_LABEL,
    daily_cup_max_rounds_for_participants,
)
from app.workers.tasks.daily_cup_messaging_text import (
    build_standings_lines as build_daily_cup_standings_lines,
)
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
    participants_total = len(participant_labels)
    rounds_total = daily_cup_max_rounds_for_participants(participants_total=participants_total)
    standings_user_ids = [item.user_id for item in lobby.participants]
    points_map = {item.user_id: format_points(item.score) for item in lobby.participants}
    body_lines = [
        "🏆 Daily Arena Cup",
        "",
        "Format: 7 Fragen • 3-4 Runden",
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
            tie_break_map = {
                item.user_id: format_points(item.tie_break) for item in lobby.participants
            }
            standings_lines = build_daily_cup_standings_lines(
                standings_user_ids=standings_user_ids,
                labels=labels,
                points_by_user=points_map,
                viewer_user_id=user_id,
                tie_breaks_by_user=tie_break_map,
            )
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
                    else TOURNAMENT_SELF_BOT_LABEL
                )
                body_lines.extend(
                    [
                        TEXTS_DE["msg.daily_cup.round_active_with_opponent"].format(
                            opponent_label=opponent_label
                        ),
                        "",
                    ]
                )
            elif round_no >= rounds_total:
                body_lines.extend(
                    [TEXTS_DE["msg.daily_cup.waiting_completion"].format(round_no=round_no), ""]
                )
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
                    f"Runde {round_no}/{rounds_total}",
                    f"Deadline: {format_deadline(lobby.tournament.round_deadline)} (Berlin)",
                    "",
                ]
            )
            body_lines.extend(
                build_daily_cup_standings_lines(
                    standings_user_ids=standings_user_ids,
                    labels=labels,
                    points_by_user=points_map,
                    viewer_user_id=user_id,
                    tie_breaks_by_user=None,
                )
            )

    play_challenge_id = (
        str(lobby.viewer_current_match_challenge_id)
        if lobby.viewer_current_match_challenge_id is not None
        else None
    )
    keyboard = build_daily_cup_lobby_keyboard(
        tournament_id=str(lobby.tournament.tournament_id),
        can_join=lobby.tournament.status == "REGISTRATION" and not lobby.viewer_joined,
        play_challenge_id=play_challenge_id,
        show_share_result=lobby.tournament.status == "COMPLETED" and lobby.viewer_joined,
        show_proof_card=lobby.tournament.status == "COMPLETED" and lobby.viewer_joined,
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
