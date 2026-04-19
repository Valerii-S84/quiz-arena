from __future__ import annotations

import math
import random

from app.game.tournaments.pairing_swiss import build_swiss_pairs as build_swiss_pairs_impl
from app.game.tournaments.types import SwissPair, SwissParticipant


def _to_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _next_power_of_two(value: int) -> int:
    resolved_value = max(1, int(value))
    return 1 << (resolved_value - 1).bit_length()


def build_swiss_pairs(
    *,
    participants: list[SwissParticipant],
    previous_pairs: set[frozenset[int]],
    bye_history: set[int] | None = None,
) -> list[SwissPair]:
    return build_swiss_pairs_impl(
        participants=participants,
        previous_pairs=previous_pairs,
        bye_history=bye_history,
    )


def _evenly_spaced_indices(*, total: int, count: int) -> list[int]:
    resolved_total = max(0, int(total))
    resolved_count = max(0, int(count))
    if resolved_count == 0:
        return []
    if resolved_count > resolved_total:
        raise ValueError("count must be <= total")
    return [(index * resolved_total) // resolved_count for index in range(resolved_count)]


def distribute_byes(
    participants: list[int],
    bracket_size: int,
    bye_count: int,
) -> list[dict[str, int | bool | None]]:
    resolved_size = max(2, int(bracket_size))
    resolved_byes = max(0, int(bye_count))
    expected_players = resolved_size - resolved_byes
    if expected_players != len(participants):
        raise ValueError("participants length does not match bracket_size/bye_count")

    pair_total = resolved_size // 2
    bye_pair_indices = _evenly_spaced_indices(total=pair_total, count=resolved_byes)
    bye_positions: set[int] = set()
    for pair_index in bye_pair_indices:
        left_slot = pair_index * 2
        bye_positions.add(left_slot if pair_index % 2 == 0 else left_slot + 1)

    slots: list[dict[str, int | bool | None]] = [
        {
            "slot_id": slot_id,
            "player_id": None,
            "is_bye": slot_id in bye_positions,
            "round_reached": 1,
        }
        for slot_id in range(resolved_size)
    ]
    player_positions = [slot_id for slot_id in range(resolved_size) if slot_id not in bye_positions]
    for slot_id, user_id in zip(player_positions, participants, strict=True):
        slots[slot_id]["player_id"] = int(user_id)

    return slots


def create_elimination_bracket(participants: list[int], tournament_id: object) -> dict[str, object]:
    if len(participants) < 2:
        raise ValueError("single elimination requires at least 2 participants")
    shuffled_participants = [int(user_id) for user_id in participants]
    random.shuffle(shuffled_participants)
    bracket_size = _next_power_of_two(len(shuffled_participants))
    bye_count = bracket_size - len(shuffled_participants)
    slots = distribute_byes(
        shuffled_participants,
        bracket_size=bracket_size,
        bye_count=bye_count,
    )
    return {
        "tournament_id": str(tournament_id),
        "size": bracket_size,
        "rounds_total": int(math.log2(bracket_size)),
        "rounds_done": 0,
        "bye_count": bye_count,
        "slots": slots,
        "winners": {},
    }


def get_winner_bracket_slot(slot: int, bracket: dict[str, object]) -> int:
    bracket_size = max(2, _to_int(bracket.get("size", 2), default=2))
    resolved_slot = int(slot)
    if resolved_slot < 0 or resolved_slot >= bracket_size:
        raise ValueError("slot is out of bracket bounds")
    return resolved_slot // 2


def get_next_opponent(winner_slot: int, bracket: dict[str, object]) -> int | None:
    slots_raw = bracket.get("slots")
    if not isinstance(slots_raw, list):
        return None
    opponent_slot = int(winner_slot) ^ 1
    if opponent_slot < 0 or opponent_slot >= len(slots_raw):
        return None
    opponent_payload = slots_raw[opponent_slot]
    if not isinstance(opponent_payload, dict):
        return None
    player_id = opponent_payload.get("player_id")
    if player_id is None:
        return None
    resolved_player_id = _to_int(player_id, default=-1)
    return None if resolved_player_id < 0 else resolved_player_id
