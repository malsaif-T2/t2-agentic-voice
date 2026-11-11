"""Run I's arm of run T (plan 007, "Run I"; first_audio_cache.py): `--clause-cache on` builds the
clause cache in the run's folder over the replay's counting voice, and the run clears it once the
smoke call has passed; each attempt of a recording keeps its own counts, and a recording replayed
after a rate limit is left out of the shares; the hits are split between each item's first
variant and the rest; and the scorecard and the history line hold the run's numbers. Nothing is
sent: a fake replay, or the library's replay on a fake voice and chat model."""

from __future__ import annotations

import asyncio
import dataclasses
from functools import partial
from pathlib import Path

import pytest
from ole5_voice.agent import talker_agent
from ole5_voice.evals import first_audio
from ole5_voice.evals.first_audio_cache import ClauseCall, clause_summary
from ole5_voice.evals.first_audio_replay import AudioReplay
from ole5_voice.evals.first_audio_score import AudioResult, ReplayedCall, ReplayedTurn
from ole5_voice.evals.measure_lines import FirstAudioLine
from ole5_voice.evals.models import Item
from t2_agentic_voice import VoiceSettings
from t2_agentic_voice.evals import ScriptedLLM
from t2_agentic_voice.ports import AudioClip
from t2_agentic_voice.testing import audio_call
from t2_agentic_voice.voice.calls import VoiceCalls

from tests.ole5_voice.evals.eot_support import paused
from tests.ole5_voice.evals.first_audio_support import call, t_run
from tests.ole5_voice.evals.run_support import World
from tests.ole5_voice.evals.talker_fakes import FakeKnowledgeBase
from tests.ole5_voice.evals.timing_support import ENGLISH
from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech, tone
from tests.t2_agentic_voice.voice.kit import PauseAnalyzer, ToneVAD

ON = ("--clause-cache", "on")


def _with(clauses: ClauseCall, *turns: ReplayedTurn) -> ReplayedCall:
    """A replayed call (`call`'s) that the clause cache counted as `clauses`."""
    return dataclasses.replace(call(*turns), clauses=clauses)


def _quick(ttfa_ms: float = 1200.0) -> ReplayedTurn:
    return ReplayedTurn(ttfa_ms=ttfa_ms, tts_first_audio_ms=250.0)


def _two_devices(world: World) -> list[Item]:
    """Two dev items in the run's order, the first said on two microphones."""
    return [
        paused(world, "n20_made_up", devices=("laptop", "wired")),
        paused(world, "n02_made_up", kind="request"),
    ]


def test_the_flag_builds_the_cache_in_the_runs_folder_and_is_off_by_default(
    tmp_path: Path,
) -> None:
    run = t_run(tmp_path, call(_quick()))
    assert first_audio.main(run.argv("--smoke-only"), parts=run.parts()) == 0
    assert run.replay.built["clauses"] is None and not run.built[0].tts.cache_clauses
    card = run.card()
    assert not card.run.clause_cache and card.clause_cache is None
    assert card.run.settings["tts.cache_clauses"] == "false"
    (line, _), _ = run.lines.appended
    assert isinstance(line, FirstAudioLine) and line.clause_cache is None

    on = t_run(tmp_path / "on", _with(ClauseCall(misses=2, kept=2), _quick()))
    assert first_audio.main(on.argv(*ON, "--smoke-only"), parts=on.parts()) == 0
    assert on.replay.built["clauses"] == on.out / "clauses"  # the run's own folder, new
    assert on.built[0].tts.cache_clauses  # the arm's setting, recorded with the others
    card = on.card()
    assert card.run.clause_cache and card.run.settings["tts.cache_clauses"] == "true"
    assert card.clause_cache is not None and card.clause_cache.every.asked == 0


def test_the_cache_is_cleared_once_the_smoke_call_passed(tmp_path: Path) -> None:
    run = t_run(tmp_path, _with(ClauseCall(misses=3, kept=3), _quick()))
    assert first_audio.main(run.argv(*ON), parts=run.parts()) == 0
    assert run.replay.cleared == [1]  # after the smoke call, before the first measured one
    card = run.card()
    assert card.clause_cache is not None and card.clause_cache.every.asked == 9  # 3 recordings

    failed = t_run(tmp_path / "failed", call(ReplayedTurn(failure="server_error")))
    assert first_audio.main(failed.argv(*ON), parts=failed.parts()) == 1
    assert failed.replay.cleared == []


@pytest.mark.parametrize("arm", [ON, ("--set", "tts.cache_clauses=true")])
def test_a_held_out_run_is_refused_the_cache_before_anything_is_sent(
    tmp_path: Path, arm: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    run = t_run(tmp_path)
    assert first_audio.main(run.argv(*arm, split="held-out"), parts=run.parts()) == 2
    assert "--clause-cache on" in capsys.readouterr().out
    assert run.replay.asked == [] and run.cache.declared == [] and not run.out.exists()


def test_a_repeated_attempts_counts_are_kept_apart(tmp_path: Path) -> None:
    limited = _with(ClauseCall(hits=1, misses=1), ReplayedTurn(failure="rate_limited"))
    again = _with(ClauseCall(hits=2, misses=0, first_held=True), _quick())
    plain = _with(ClauseCall(hits=1, misses=3, first_held=False), _quick())
    run = t_run(tmp_path, plain, limited, again, plain, plain)
    assert first_audio.main(run.argv(*ON), parts=run.parts()) == 0
    card = run.card()
    first = card.variants[0]
    assert first.attempts == 2 and first.clause_cache == (limited.clauses, again.clauses)
    summary = card.clause_cache
    assert summary is not None
    assert (summary.retried.variants, summary.retried.asked, summary.retried.hits) == (1, 4, 3)
    # Left out of the shares: the two other recordings alone, each its item's first variant.
    assert (summary.first.variants, summary.first.asked, summary.first.hits) == (2, 8, 2)
    assert summary.first.share == 0.25 and summary.every.asked == 8


def test_the_scorecard_and_the_history_line_hold_the_runs_numbers(tmp_path: Path) -> None:
    cold = ClauseCall(
        misses=3,
        kept=4,
        miss_ms=(0.01, 0.02, 0.03),
        first_held=False,
        call_s=30.0,
        entries=4,
        megabytes=0.6,
    )
    warm = ClauseCall(
        hits=2,
        misses=1,
        kept=1,
        not_kept={"held": 1},
        hit_ms=(3.0, 5.0),
        miss_ms=(0.04,),
        first_held=True,
        unsaid=0,
        call_s=30.0,
        entries=5,
        megabytes=0.8,
    )
    run = t_run(
        tmp_path,
        _with(cold, _quick()),
        _with(cold, _quick(1500.0)),
        _with(warm, _quick(900.0)),
        _with(warm, ReplayedTurn(ttfa_ms=1000.0)),
        items=_two_devices,
    )
    assert first_audio.main(run.argv(*ON), parts=run.parts()) == 0
    card = run.card()
    summary = card.clause_cache
    assert summary is not None
    assert [v.clause_cache for v in card.variants] == [(cold,), (warm,), (warm,)]
    assert (summary.kept, summary.not_kept, summary.entries, summary.megabytes) == (
        6,
        {"held": 2},
        5,
        0.8,
    )
    assert (summary.hit_read.count, summary.hit_read.most_ms) == (4, 5.0)
    assert summary.miss_lookup.count == 5 and summary.miss_lookup.most_ms == 0.04
    assert summary.tts_first_audio.median_ms == 250.0 and summary.tts_first_audio.count == 2
    # The turns whose reply's first clause was held, against the others.
    assert (summary.held_first, summary.held_first_median_ms) == (2, 950.0)
    assert summary.other_median_ms == 1500.0
    # Requests per call minute: the clauses requested, then with each hit added back.
    assert summary.call_minutes == 1.5
    assert summary.requests_per_minute == pytest.approx(5 / 1.5)
    assert summary.asked_per_minute == pytest.approx(9 / 1.5)
    assert summary.checks == {
        "none_failed": True,
        "first_variant_hits": True,
        "miss_p90": True,
        "miss_most": True,
        "hit_p90": True,
    }
    (line, _), (copy, _) = run.lines.appended
    assert isinstance(line, FirstAudioLine) and line == copy
    assert line.clause_cache == summary


def _result(item: str, variant: str, clauses: ClauseCall, *, attempts: int = 1) -> AudioResult:
    return AudioResult(
        item=item,
        variant=variant,
        split="dev",
        language="saudi",
        device="laptop",
        end="detector",
        attempts=attempts,
        turns=(_quick(),),
        timed=_quick(),
        clause_cache=(clauses,),
    )


def test_the_hits_are_split_between_each_items_first_variant_and_the_rest() -> None:
    results = [
        _result("a", "a-1", ClauseCall(misses=3)),
        _result("b", "b-1", ClauseCall(hits=1, misses=2)),
        _result("a", "a-2", ClauseCall(hits=2, misses=1)),
        _result("b", "b-2", ClauseCall(hits=3, misses=1)),
        _result("c", "c-1", ClauseCall(hits=5), attempts=2),  # replayed: apart
    ]
    summary = clause_summary(results)
    assert (summary.first.variants, summary.first.asked, summary.first.hits) == (2, 6, 1)
    assert summary.first.share == pytest.approx(1 / 6)
    assert (summary.rest.variants, summary.rest.asked, summary.rest.hits) == (2, 7, 5)
    assert (summary.every.asked, summary.every.hits) == (13, 6)
    assert (summary.retried.variants, summary.retried.hits) == (1, 5)
    assert summary.checks["first_variant_hits"] is True
    # Under 2% of the first variants' clauses held: the keep rule's second condition fails.
    cold = clause_summary([_result("a", "a-1", ClauseCall(misses=60, miss_ms=(0.5, 30.0)))])
    assert cold.checks["first_variant_hits"] is False and cold.checks["miss_most"] is False
    assert cold.checks["hit_p90"] is None  # no hit to time
    assert clause_summary([]).first.share is None


def test_the_replay_speaks_through_the_cache_over_its_counting_voice(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The library's replay of two calls saying the same reply: the first requests its clauses
    and keeps them, the second holds every one, its only request the replay's own greeting; the
    counts are taken call by call, the cache cleared empties the folder, and closing the replay
    drains the cache and leaves the voice open."""
    detectors = partial(VoiceCalls, speech_detector=ToneVAD, turn_analyzer=PauseAnalyzer)
    monkeypatch.setattr(audio_call, "VoiceCalls", detectors)
    said = "Open the letter, then press print."
    chat = ScriptedLLM([ScriptedLLM.reply(said), ScriptedLLM.reply(said)])
    tts = FakeTextToSpeech(seconds_per_char=0.03)
    folder = tmp_path / "out" / "clauses"
    replay = AudioReplay(
        agent=talker_agent(FakeKnowledgeBase()),
        settings=settings,
        stt=FakeSpeechToText(["how do I print a letter"] * 2),
        tts=tts,
        llm=chat,
        clauses=folder,
    )
    assert replay.clauses is not None and replay.call_of.tts is replay.clauses
    assert not folder.exists()  # built with no IO
    hold_s = settings.turns.complete_hold_ms / 1000

    async def run() -> tuple[ReplayedCall, ReplayedCall, int]:
        await replay.start()
        try:
            asked = {"language": "en", "end_ms": 500.0, "lead_s": 0.5, "tail_s": 3.0 + hold_s}
            clip = AudioClip(pcm16=tone(0.5, 16_000))
            first = await replay.call(clip, **asked)  # type: ignore[arg-type]
            second = await replay.call(clip, **asked)  # type: ignore[arg-type]
            await replay.clear()
            assert replay.clauses is not None
            return first, second, replay.clauses.cache.counts().entries
        finally:
            await replay.aclose()

    first, second, left = asyncio.run(asyncio.wait_for(run(), timeout=60))
    cold, warm = first.clauses, second.clauses
    assert cold is not None and warm is not None
    assert cold.hits == 0 and cold.misses >= 1 and cold.first_held is False
    assert warm.hits == cold.misses and warm.misses == 0 and warm.first_held is True
    assert cold.kept >= cold.misses and warm.not_kept == {"held": 1}  # the replay's greeting
    assert len(warm.hit_ms) == warm.hits and cold.call_s is not None and warm.unsaid == 0
    english = [u for u in second.usage if u.model == ENGLISH]
    assert sum(u.requests for u in english) == 1  # the greeting the replay says, alone
    assert sum(u.cache_hits for u in english) >= warm.hits
    assert left == 0 and list(folder.glob("*.wav")) == []
    assert not tts.closed  # the run closes the voice it built


def test_a_replay_with_no_cache_clears_nothing(settings: VoiceSettings) -> None:
    replay = AudioReplay(
        agent=talker_agent(FakeKnowledgeBase()),
        settings=settings,
        stt=FakeSpeechToText(),
        tts=FakeTextToSpeech(),
        llm=ScriptedLLM([]),
    )
    assert replay.clauses is None and replay.call_of.tts is replay.voice
    asyncio.run(replay.clear())
