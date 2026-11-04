"""The measuring part of `poe overlap` (overlap_run.py, overlap_plan.py): the smoke test that
stops a run before any clip when it failed, the pacer holding the replay to 10 Whisper requests
a minute, a clip that met a rate limit played again after a minute and one still limited
stopping the run, a variant whose deciding request failed counted apart, the cap stopping the
run before a clip it cannot afford, the text-to-speech whose reply outlasts the clip, the
reference answerer's verdicts, each clip's reply, and a `--set`'s value."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pytest
from ole5_voice.evals import overlap
from ole5_voice.evals.overlap_card import OverlapScorecard
from ole5_voice.evals.overlap_plan import DEFAULT_REPLY, overlaps_of, setting
from ole5_voice.evals.overlap_run import (
    MAX_ATTEMPTS,
    RATE_LIMIT_PAUSE_S,
    ReplySpeech,
    reference,
    stt_budget,
)
from ole5_voice.evals.run_lines import OverlapLine
from ole5_voice.evals.run_parts import Choice, Todo, load_plan
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.takes import ScriptLine
from t2_agentic_voice.evals import OverlapReplay

from tests.ole5_voice.evals.overlap_support import (
    WENT_ON,
    FakeReplayer,
    Run,
    clip,
    pipeline,
    requests_in_any_minute,
    stop,
)
from tests.ole5_voice.evals.run_support import FakeClock, World, golden_set, make_world


def _script(world: World) -> None:
    (world.data / "script.toml").write_text(
        '[[lines]]\nid = "x"\nkind = "noise"\nlanguage = "none"\n', encoding="utf-8"
    )


def _run(tmp_path: Path, n: int, *script: OverlapReplay | BaseException) -> Run:
    world = make_world(tmp_path)
    found = [clip(world, f"k{i}", "stop_word") for i in range(n)]
    _script(world)
    clock = FakeClock()
    return Run(world, golden_set(*found), FakeReplayer(list(script), clock), clock=clock)


def _card(run: Run) -> OverlapScorecard:
    return OverlapScorecard.model_validate_json((run.out / SCORECARD_FILE).read_bytes())


@pytest.mark.parametrize(
    "smoke",
    [
        stop(failure="timeout"),
        stop(failure="rate_limited"),  # passing would need the clip played again
        stop(failure="rejected"),
        WENT_ON,  # it sent no request, so it tested nothing
        ValueError("the reply is no phrase a greeting may say"),
    ],
)
def test_a_smoke_test_that_failed_stops_the_run_before_any_clip(
    tmp_path: Path, smoke: OverlapReplay | BaseException
) -> None:
    run = _run(tmp_path, 2, smoke, stop(), stop())
    assert overlap.main(pipeline(run), parts=run.parts()) == 1
    card = _card(run)
    assert (card.complete, card.stopped, card.variants) == (False, "smoke_failed", ())
    assert len(run.replayer.asked) == 1 and run.replayer.closed == 1 and run.stt.closed
    (line, _), _ = run.lines.appended  # every attempt is recorded, its spend counted
    assert isinstance(line, OverlapLine) and not line.complete
    assert line.requests == card.requests


def test_the_pacer_holds_the_replay_to_10_whisper_requests_a_minute(tmp_path: Path) -> None:
    run = _run(tmp_path, 8, *[stop()] * 9)
    assert overlap.main(pipeline(run), parts=run.parts()) == 0
    times = [asked["at"] for asked in run.replayer.asked]
    assert requests_in_any_minute(times, [2] * len(times)) <= 10
    assert max(run.clock.pauses) == pytest.approx(60.0, abs=0.01)  # the window's oldest left


def test_a_clip_is_budgeted_3_requests_for_each_started_4_s_of_it_and_its_tail() -> None:
    assert [stt_budget(s) for s in (0.5, 1.0, 3.5, 3.6, 7.5, 7.6)] == [6, 6, 6, 9, 9, 12]
    assert stt_budget(23.0) == 21  # an echo item's clip: 27.5 s with its tail, 7 spans


def _long_run(tmp_path: Path, *script: OverlapReplay) -> Run:
    """Clips of 1, 24 and 1 s (items k0, k1, k2), the smoke test k0's."""
    world = make_world(tmp_path)
    found = [clip(world, f"k{i}", "stop_word", seconds=s) for i, s in enumerate((1.0, 24.0, 1.0))]
    _script(world)
    clock = FakeClock()
    return Run(world, golden_set(*found), FakeReplayer(list(script), clock), clock=clock)


def test_a_long_clip_starts_on_an_empty_minute(tmp_path: Path) -> None:
    """A 24 s clip is budgeted 24 requests, more than the 10 a minute: it waits until no request
    of the last minute is left, though 6 more would have fitted beside the 4 sent, so the
    overlaps it may open join no other clip's requests in a minute."""
    run = _long_run(tmp_path, stop(), stop(), stop(), stop())
    assert overlap.main(pipeline(run), parts=run.parts()) == 0
    times = [asked["at"] for asked in run.replayer.asked]
    assert run.replayer.asked[2]["clip"].seconds == pytest.approx(24.0)
    assert times[1] == times[0] and all(t <= times[2] - 60 for t in times[:2])
    assert requests_in_any_minute(times, [2] * 4) <= 10


def test_the_cap_budgets_a_long_clip_by_its_length(tmp_path: Path) -> None:
    """The 24 s clip is budgeted 24 requests of 24 s each, 0.0178 USD: a cap of 0.015 refuses
    it, though the smoke test and the first clip, 0.00185 each, fit."""
    run = _long_run(tmp_path, stop(), stop(), stop(), stop())
    argv = [*pipeline(run)[:-2], "--cap-usd", "0.015"]
    assert overlap.main(argv, parts=run.parts()) == 1
    card = _card(run)
    assert (card.complete, card.stopped, len(card.variants)) == (False, "cap", 1)
    assert len(run.replayer.asked) == 2


def test_a_clip_that_met_a_rate_limit_is_played_again_after_a_minute(tmp_path: Path) -> None:
    run = _run(tmp_path, 1, stop(), stop(failure="rate_limited"), stop())
    assert overlap.main(pipeline(run), parts=run.parts()) == 0
    card = _card(run)
    (result,) = card.variants
    assert (result.attempts, card.requests, card.billed_seconds) == (2, 6, 60.0)
    assert RATE_LIMIT_PAUSE_S in run.clock.pauses


def test_a_clip_still_rate_limited_on_its_last_call_stops_the_run(tmp_path: Path) -> None:
    """Not scored as the rule's verdict on what Whisper never answered: the run stops as at
    the cap, its scorecard and history line written."""
    limited = [stop(failure="rate_limited")] * MAX_ATTEMPTS
    run = _run(tmp_path, 3, stop(), stop(), *limited, stop())
    assert overlap.main(pipeline(run), parts=run.parts()) == 1
    card = _card(run)
    assert (card.complete, card.stopped, len(card.variants)) == (False, "rate_limited", 1)
    assert len(run.replayer.asked) == 2 + MAX_ATTEMPTS  # the third clip never played
    assert run.clock.pauses.count(RATE_LIMIT_PAUSE_S) == MAX_ATTEMPTS - 1
    (line, _), _ = run.lines.appended
    assert isinstance(line, OverlapLine) and not line.complete
    assert line.requests == 2 * (2 + MAX_ATTEMPTS)


def test_a_variant_whose_deciding_request_failed_is_counted_apart(tmp_path: Path) -> None:
    run = _run(tmp_path, 2, stop(), stop(failure="timeout"), stop())
    assert overlap.main(pipeline(run), parts=run.parts()) == 0
    card = _card(run)
    assert [r.judged.failed for r in card.variants] == [True, False]
    assert (card.totals.failed, card.totals.should_stop, card.totals.stopped) == (1, 1, 1)
    (line, _), _ = run.lines.appended
    assert isinstance(line, OverlapLine)
    assert (line.variants, line.failed, line.right) == (2, 1, 1)


def test_the_cap_stops_the_run_before_a_clip_it_cannot_afford(tmp_path: Path) -> None:
    """A clip of 1 s is budgeted 6 requests of 10 s (two started spans of it and its tail):
    0.00185 USD at 0.111 an hour. The smoke test and the first clip spent 2 requests each
    (0.001233), so the second's budget would pass a cap of 0.003."""
    run = _run(tmp_path, 3, stop(), stop(), stop(), stop())
    argv = [*pipeline(run)[:-2], "--cap-usd", "0.003"]
    assert overlap.main(argv, parts=run.parts()) == 1
    card = _card(run)
    assert (card.complete, card.stopped, len(card.variants)) == (False, "cap", 1)
    assert card.cost_usd == pytest.approx(40 / 3600 * 0.111)
    (line, _), _ = run.lines.appended
    assert isinstance(line, OverlapLine) and not line.complete
    assert run.replayer.closed == 1 and run.stt.closed


def test_the_reply_outlasts_the_clip_as_a_quiet_tone() -> None:
    speech = ReplySpeech(seconds=0.5)

    async def said() -> list[bytes]:
        await speech.check_language("ar-SA")
        found = [chunk.pcm16 async for chunk in speech.synthesize("any", language="ar-SA")]
        await speech.aclose()
        return found

    chunks = asyncio.run(said())
    assert [len(c) for c in chunks] == [9600, 9600, 4800]  # 0.2, 0.2 and 0.1 s at 24 kHz
    assert any(chunks[0]) and speech.max_chars("en") is None


def _todo(tmp_path: Path, *found_kinds: tuple[str, str, tuple[str, ...]]) -> list[Todo]:
    world = make_world(tmp_path)
    found = [
        clip(world, item_id, kind, tags=tags, end_ms=900 if kind == "stop_word" else None)
        for item_id, kind, tags in found_kinds
    ]
    run = Run(world, golden_set(*found), FakeReplayer([], FakeClock()))
    return list(load_plan(world.data, Choice(split="dev"), run.parts().plan).todo)


def test_the_reference_answerer_gives_each_kind_its_verdict(tmp_path: Path) -> None:
    kinds = [
        ("k1", "stop_word", ()),
        ("c1", "correction", ("over-assistant",)),
        ("r1", "request", ("over-assistant",)),
        ("p1", "repeat_request", ()),
        ("b1", "listening_sound", ()),
    ]
    todo = _todo(tmp_path, *kinds)
    found = overlaps_of(todo, {}, None, {})
    verdicts = [reference(each) for each in found]
    assert [(v.action, v.kind, v.last_audio_ms) for v in verdicts] == [
        ("stop", "stop", 900.0),
        ("stop", "correction", 0.0),
        ("stop", "new_words", 0.0),
        ("repeat", "new_words", 0.0),
        ("go_on", "false", None),
    ]
    judged = [e.result("dev", v).judged for e, v in zip(found, verdicts, strict=True)]
    assert all(j.right for j in judged)
    assert (judged[0].from_mark_ms, judged[1].from_detector_ms) == (0.0, 0.0)


def test_each_clips_reply_is_the_texts_known_to_have_played_over_it(tmp_path: Path) -> None:
    todo = _todo(tmp_path, ("k1", "stop_word", ()), ("b1", "listening_sound", ()))
    called = {"k1-laptop": ("A made-up clause.",), "b1-laptop": ()}
    line = ScriptLine(id="k1", kind="stop_word", language="saudi", say=("made-up",))
    first, second = overlaps_of(todo, {"k1": line}, {}, called)
    assert (first.reply, first.reply_known) == (("A made-up clause.",), True)
    assert (second.reply, second.reply_known) == ((DEFAULT_REPLY["ar-SA"],), False)


def test_a_settings_value_is_read_as_json_where_it_is_json() -> None:
    assert setting("stt.no_speech_max=0.5") == ("stt.no_speech_max", 0.5)
    assert setting("interruptions.mode=two_step") == ("interruptions.mode", "two_step")
    assert setting("stt.no_speech_max=null") == ("stt.no_speech_max", None)
    for broken in ("stt", "stt.=1", ".x=1", "stt.x"):
        with pytest.raises(argparse.ArgumentTypeError):
            setting(broken)
