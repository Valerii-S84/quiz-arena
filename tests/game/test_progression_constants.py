from __future__ import annotations

from app.game.sessions.service.constants import (
    DEFAULT_MODE_PROGRESSION_CONFIG,
    MIX_STEP_WEIGHTS,
    MODE_PROGRESSION_CONFIGS,
    PROGRESSION_ACCURACY_THRESHOLD,
    PROGRESSION_CORRECT_PER_STEP,
    PROGRESSION_WARM_UP_THRESHOLD,
)


def test_progression_constants_match_documented_values() -> None:
    assert PROGRESSION_WARM_UP_THRESHOLD == 30
    assert PROGRESSION_ACCURACY_THRESHOLD == 0.75
    assert PROGRESSION_CORRECT_PER_STEP == 10


def test_modes_share_identical_progression_parameters() -> None:
    artikel_config = MODE_PROGRESSION_CONFIGS["ARTIKEL_SPRINT"]
    quick_mix_config = MODE_PROGRESSION_CONFIGS["QUICK_MIX_A1A2"]

    assert artikel_config == DEFAULT_MODE_PROGRESSION_CONFIG
    assert quick_mix_config == DEFAULT_MODE_PROGRESSION_CONFIG
    assert artikel_config.warm_up_threshold == 30
    assert artikel_config.accuracy_threshold == 0.75
    assert artikel_config.correct_per_step == 10


def test_mix_step_weights_remain_unchanged() -> None:
    assert MIX_STEP_WEIGHTS == {
        1: 0.25,
        2: 0.50,
        3: 0.75,
    }
