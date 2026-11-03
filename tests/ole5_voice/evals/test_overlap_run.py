"""The measuring part of `poe overlap` (overlap_run.py, overlap_plan.py): the pacer holding the
replay to 10 Whisper requests a minute, a clip that met a rate limit played again after a
minute, the cap stopping the run before a clip it cannot afford, the text-to-speech whose reply
outlasts the clip, the reference answerer's verdicts, each clip's reply, and a `--set`'s value."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pytest
from ole5_voice.evals import overlap
from ole5_voice.evals.overlap_card import OverlapScorecard
from ole5_voice.evals.overlap_plan import DEFAULT_REPLY, overlaps_of, setting
from ole5_voice.evals.overlap_run import RATE_LIMIT_PAUSE_S, ReplySpeech, reference
from ole5_voice.evals.run_lines import OverlapLine
from ole5_voice.evals.run_parts import Choice, Todo, load_plan
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.takes import ScriptLine
from t2_agentic_voice.evals import OverlapReplay

from tests.ole5_voice.evals.overlap_support import (
    FakeReplayer,
    Run,
    clip,
    pipeline,
    requests_in_any_minute,
    stop,
)
from tests.ole5_voice.evals.run_support import FakeClock, golden_set, make_world


def _run(tmp_path: Path, n: int, *script: OverlapReplay) -> Run:
    world = make_world(tmp_path)
    found = [clip(world, f"k{i}", "stop_word") for i in range(n)]
    (world.data / "script.toml").write_text(
        '[[lines]]\nid = "x"\nkind = "noise"\nlanguage = "none"\n', encoding="utf-8"
    )
    clock = FakeClock()
    return Run(world, golden_set(*found), FakeReplayer(list(script), clock), clock=clock)


def test_the_pacer_holds_the_replay_to_10_whisper_requests_a_minute(tmp_path: Path) -> None:
    run = _run(tmp_path, 8, *[stop()] * 8)
    assert overlap.main(pipeline(run), parts=run.parts()) == 0
    times = [asked["at"] for asked in run.replayer.asked]
    assert requests_in_any_minute(times, [2] * len(times)) <= 10
    assert max(run.clock.pauses) == pytest.approx(60.0, abs=0.01)  # the window's oldest left


def test_a_clip_that_met_a_rate_limit_is_played_again_after_a_minute(tmp_path: Path) -> None:
    run = _run(tmp_path, 1, stop(failure="rate_limited"), stop())
    assert overlap.main(pipeline(run), parts=run.parts()) == 0
    card = OverlapScorecard.model_validate_json((run.out / SCORECARD_FILE).read_bytes())
    (result,) = card.variants
    assert (result.attempts, card.requests, card.billed_seconds) == (2, 4, 40.0)
    assert RATE_LIMIT_PAUSE_S in run.clock.pauses


def test_the_cap_stops_the_run_before_a_clip_it_cannot_afford(tmp_path: Path) -> None:
    """A clip is budgeted 3 requests of 10 s: 0.000925 USD at 0.111 an hour. The first spent
    2 requests (0.000617), so the second's budget would pass a cap of 0.0012."""
    run = _run(tmp_path, 3, stop(), stop(), stop())
    argv = [*pipeline(run)[:-2], "--cap-usd", "0.0012"]
    assert overlap.main(argv, parts=run.parts()) == 1
    card = OverlapScorecard.model_validate_json((run.out / SCORECARD_FILE).read_bytes())
    assert (card.complete, card.stopped, len(card.variants)) == (False, "cap", 1)
    assert card.cost_usd == pytest.approx(20 / 3600 * 0.111)
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
