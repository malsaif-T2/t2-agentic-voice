"""The library's settings the flight app turns on for plan 010's first changes to how soon a call
answers (flight_voice/turned_on.py, through settings.py's `for_the_app`), each unless the
environment sets it: the warm-up (1.13), Smart Turn on two threads (the study's rank 4), 0.1 s of
silence after a progress line's speech (1.15) and the early start from the detector's stop, over
a reply in progress too (2.2), for either agent, and for the scripted agent alone, which reads its
actions back, a 1.8 s fallback end of a turn with 3 s kept while a read-back awaits its answer
(1.11, Q9); the lean agent, with no read-back, keeps 3 s for every turn. The library's defaults
leave each off."""

from __future__ import annotations

import pytest
from flight_voice.settings import AGENTS, AgentKind, for_the_app, load
from flight_voice.turned_on import (
    MAX_SILENCE_MS,
    PROGRESS_BEAT_MS,
    READ_BACK_SILENCE_MS,
    READ_BACK_TURNS,
    SMART_TURN_THREADS,
    TURNED_ON,
)
from t2_agentic_voice import VoiceSettings


def test_the_library_leaves_each_off_by_default() -> None:
    voice = VoiceSettings(env="test")
    assert (voice.warmup.at_start, voice.warmup.at_join, voice.warmup.after_cancel) == (
        False,
        False,
        False,
    )
    assert (voice.turns.max_silence_ms, voice.turns.read_back_silence_ms) == (3000, None)
    assert voice.turns.smart_turn_threads == 1
    assert voice.session.progress_beat_ms is None
    assert not voice.turns.early_at_stop and not voice.session.early_over_reply


@pytest.mark.parametrize("agent", AGENTS)
def test_the_app_turns_each_on_for_either_agent(agent: AgentKind) -> None:
    app = for_the_app(VoiceSettings(env="test"), agent=agent)
    assert app.warmup.at_start and app.warmup.at_join and app.warmup.after_cancel
    assert app.turns.smart_turn_threads == SMART_TURN_THREADS == 2
    assert app.session.progress_beat_ms == PROGRESS_BEAT_MS == 100
    assert app.turns.complete_hold_ms == 600  # the hold the longer wait needs, as it was
    assert app.turns.early_at_stop and app.session.early_over_reply


def test_the_shorter_end_of_a_turn_is_the_scripted_agents_alone() -> None:
    """Q9's 1.8 s holds only with its exception, 3 s while a read-back awaits its answer: the
    scripted agent reads its actions back; the lean one's "Shall I book it?" has no read-back,
    so it keeps the library's 3 s on every turn."""
    scripted = for_the_app(VoiceSettings(env="test"), agent="scripted").turns
    assert (scripted.max_silence_ms, scripted.read_back_silence_ms) == (1800, 3000)
    assert (MAX_SILENCE_MS, READ_BACK_SILENCE_MS) == (1800, 3000)
    lean = for_the_app(VoiceSettings(env="test"), agent="lean").turns
    assert (lean.max_silence_ms, lean.read_back_silence_ms) == (3000, None)
    assert set(READ_BACK_TURNS).isdisjoint(TURNED_ON["turns"])


def test_each_set_in_the_environment_is_kept(environment: pytest.MonkeyPatch) -> None:
    voice = load().voice
    assert voice.warmup.at_join and voice.turns.max_silence_ms == 1800
    environment.setenv("T2V_WARMUP__AT_JOIN", "false")
    environment.setenv("T2V_TURNS__MAX_SILENCE_MS", "2500")
    environment.setenv("T2V_SESSION__PROGRESS_BEAT_MS", "400")
    environment.setenv("T2V_TURNS__EARLY_AT_STOP", "false")
    voice = load().voice
    assert (voice.warmup.at_start, voice.warmup.at_join, voice.warmup.after_cancel) == (
        True,
        False,
        True,
    )
    assert (voice.turns.max_silence_ms, voice.turns.read_back_silence_ms) == (2500, 3000)
    assert voice.session.progress_beat_ms == 400
    assert not voice.turns.early_at_stop and voice.session.early_over_reply


def test_a_group_the_environment_sets_whole_is_left_as_it_is() -> None:
    given = VoiceSettings.model_validate({"env": "test", "warmup": TURNED_ON["warmup"]})
    assert for_the_app(given).warmup == given.warmup
