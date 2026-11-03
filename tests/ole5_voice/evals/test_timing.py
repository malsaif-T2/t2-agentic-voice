"""`poe eval-timing` (plan 003's registration, T), against a fake `echo_timings`, fake speech
ports and a fake phrase cache (timing_support.py), so nothing is sent and no time passes: the
fixed phrases declared and counted before the first variant; the smoke test; each variant's timed
turn and steps; the pacers holding 10 Whisper and 5 Orpheus requests in any minute over a whole
run; a rate-limited call run again; the cap; an interrupt; and the scorecard and its history
line. The refusals before anything is sent are test_timing_refusals.py's."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals import timing
from ole5_voice.evals.items import HISTORY_FILE
from ole5_voice.evals.run_lines import TimingLine
from ole5_voice.evals.timing_run import AGENT
from t2_agentic_voice import VoiceAgent, VoiceSettings
from t2_agentic_voice.evals import EchoTiming
from t2_agentic_voice.ports import AudioClip, TextToSpeech

from tests.ole5_voice.evals.test_pacers import most_in_a_minute
from tests.ole5_voice.evals.timing_support import (
    ARABIC,
    WHISPER,
    FakeEchoTimings,
    FakePhraseCache,
    Setup,
    echo,
    make_setup,
)
from tests.t2_agentic_voice.fakes import FakeTextToSpeech


@pytest.fixture
def setup(tmp_path: Path) -> Setup:
    return make_setup(tmp_path)


def test_a_run_times_each_paused_request_after_its_smoke_test(setup: Setup) -> None:
    setup.echo.script = [echo(), echo(), echo(2, early=True), echo()]
    assert timing.main(setup.argv(), parts=setup.parts()) == 0
    card = setup.card()
    assert card.complete and card.stopped is None and card.phrase_requests == 6
    assert setup.cache.declared == [AGENT]
    assert [r.variant for r in card.variants] == [
        "p0-laptop",
        "p1-laptop",
        "p2-laptop",
        "e1-laptop",
    ]
    first, cut = card.variants[0], card.variants[1]
    assert first.steps is not None and (first.cut, first.timed_turn) == (False, 0)
    assert first.steps.model_dump() == {
        "vad_stop": 0.0,
        "smart_turn": 300.0,
        "whisper": 270.0,
        "echo_ready": 10.0,
        "orpheus_first_byte": 245.0,
        "leading_silence": 450.0,
        "first_audio": 600.0,
        "heard_words": 1200.0,
    }
    assert (cut.cut, cut.timed_turn) == (True, 1)
    assert card.totals.cut_variants == 1 and card.totals.steps["whisper"].turns == 3
    assert set(card.languages) == {"saudi", "english"}
    assert [u.model for u in card.smoke] == [WHISPER, ARABIC]
    whisper = next(u for u in card.spend if u.model == WHISPER)
    assert whisper.requests == 6  # the smoke's and four variants', one cut in two
    assert card.cost_usd == pytest.approx(60 / 3600 * 0.111 + 6 * 55 / 1e6 * 40)
    tags = [asked["clips"][0][1] for asked in setup.echo.asked]
    assert tags == ["ar-SA", "ar-SA", "ar-SA", "ar-SA", "en"]
    asked = setup.echo.asked[0]
    assert (asked["lead_s"], asked["tail_s"], asked["phrases"]) == (1.0, 4.5, setup.cache)
    assert asked["stt"] is setup.stt and asked["tts"] is setup.tts and asked["agent"] is AGENT
    assert setup.stt.closed and setup.tts.closed
    ((line, to_data), (same, beside)) = setup.lines.appended
    assert line is same and isinstance(line, TimingLine)
    assert (to_data, beside) == (setup.world.data / HISTORY_FILE, setup.out / HISTORY_FILE)
    assert (line.variants, line.cut_variants, line.phrase_requests) == (4, 1, 6)
    assert line.requests == {WHISPER: 6, ARABIC: 6} and line.billed_seconds == 60.0
    assert line.medians_ms["whisper"] == 270.0 and line.settings["run.tts_rpm"] == "5"
    assert (setup.out / "results.jsonl").read_text("utf-8").count("\n") == 4


def test_the_pacers_hold_10_whisper_and_5_orpheus_requests_in_any_minute(setup: Setup) -> None:
    """Over a whole run of two-turn calls, counted when each started (at the earliest), with the
    phrase cache's six requests counted before the first: no minute holds more than 10 Whisper
    requests or 5 to the Arabic model."""
    setup.echo.script = [echo(2)]
    assert (
        timing.main(
            setup.argv("--cap-usd", "5", "--stt-rpm", "10", "--tts-rpm", "5"),
            parts=setup.parts(variants=12),
        )
        == 0
    )
    starts = setup.echo.started
    sent = [at for at in starts for _ in range(2)]
    assert most_in_a_minute(sent) <= 5 < 10  # two to each model a call
    assert starts[0] >= 1000.0 + 60.0  # the phrases' six filled the Arabic window first
    assert setup.clock.pauses


def test_a_rate_limited_call_is_run_again_after_a_minute(setup: Setup) -> None:
    setup.echo.script = [echo(), echo(failure="rate_limited"), echo()]
    assert timing.main(setup.argv(), parts=setup.parts(variants=1)) == 0
    card = setup.card()
    assert [r.attempts for r in card.variants] == [2, 1]
    assert card.variants[0].failure is None and 60.0 in setup.clock.pauses
    assert next(u for u in card.spend if u.model == WHISPER).requests == 4


def test_a_variant_that_keeps_failing_is_kept_as_failed(setup: Setup) -> None:
    setup.echo.script = [echo(), echo(failure="rate_limited")]
    assert timing.main(setup.argv(), parts=setup.parts(variants=1)) == 0
    card = setup.card()
    assert [r.attempts for r in card.variants] == [3, 3]
    assert card.totals.failures == 2 and card.totals.steps["whisper"].turns == 0


def test_a_failed_smoke_test_stops_the_run(setup: Setup) -> None:
    setup.echo.script = [echo(failure="timeout")]
    assert timing.main(setup.argv(), parts=setup.parts()) == 1
    card = setup.card()
    assert (card.complete, card.stopped, card.variants) == (False, "smoke_failed", ())
    assert len(setup.echo.asked) == 1 and setup.lines.appended  # its spend is recorded


def test_a_smoke_only_run_runs_the_smoke_test_alone(setup: Setup) -> None:
    assert timing.main(setup.argv("--smoke-only"), parts=setup.parts()) == 0
    card = setup.card()
    assert card.complete and card.variants == () and len(setup.echo.asked) == 1
    assert card.smoke[0].requests == 1


def test_the_run_stops_before_a_variant_that_would_pass_the_cap(setup: Setup) -> None:
    budget = 2 * 10 / 3600 * 0.111 + 2 * 200 / 1e6 * 40  # one variant's, at most
    spent = 10 / 3600 * 0.111 + 55 / 1e6 * 40  # one call's
    cap = f"{budget + 1.5 * spent:.6f}"  # room for the smoke test and one variant
    assert timing.main(setup.argv("--cap-usd", cap), parts=setup.parts()) == 1
    card = setup.card()
    assert (card.stopped, len(card.variants)) == ("cap", 1)
    assert card.cost_usd <= float(cap)


def test_a_phrase_cache_that_fails_stops_the_run_before_any_call(setup: Setup) -> None:
    from t2_agentic_voice import ProviderError

    class Failing(FakePhraseCache):
        async def declare(self, agent: VoiceAgent) -> int:
            raise ProviderError("rate_limited", True)

    setup.cache = Failing(0)
    assert timing.main(setup.argv(), parts=setup.parts()) == 1
    assert setup.card().stopped == "phrases_failed" and setup.echo.asked == []


def test_an_interrupted_run_keeps_what_it_measured(setup: Setup) -> None:
    class Interrupting(FakeEchoTimings):
        async def __call__(
            self, clips: Iterable[tuple[AudioClip, str]], **asked: Any
        ) -> AsyncIterator[EchoTiming]:
            if len(self.started) == 2:
                raise KeyboardInterrupt
            async for found in super().__call__(clips, **asked):
                yield found

    setup.echo = Interrupting(setup.clock, [echo()])
    assert timing.main(setup.argv(), parts=setup.parts()) == 1
    card = setup.card()
    assert (card.stopped, len(card.variants)) == ("interrupted", 1)
    assert setup.stt.closed and setup.tts.closed


def test_a_variant_with_no_turn_at_or_after_its_mark_has_no_timed_turn(setup: Setup) -> None:
    setup.echo.script = [echo(), echo(1, early=True), EchoTiming(turns=(), usage=())]
    assert timing.main(setup.argv(), parts=setup.parts(variants=1)) == 0
    early, silent = setup.card().variants
    assert (early.cut, early.timed_turn, early.steps) == (True, None, None)
    assert (silent.cut, silent.timed_turn, silent.steps) == (False, None, None)


def test_the_phrase_cache_is_the_runtimes_kept_in_the_agents_folder(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[tuple[Any, ...]] = []

    class Cache:
        @classmethod
        def from_settings(cls, given: VoiceSettings, tts: TextToSpeech, *, folder: Path) -> str:
            built.append((given, tts, folder))
            return "the cache"

    monkeypatch.setattr(timing, "PhraseCache", Cache)
    tts = FakeTextToSpeech()
    assert timing._phrase_cache(settings, tts) == "the cache"  # type: ignore[comparison-overlap]
    assert built == [(settings, tts, settings.storage.var_dir / "ole5-timing" / "phrases")]
