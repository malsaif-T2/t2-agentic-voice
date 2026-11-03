"""The import of recorded calls' overlaps (import_calls.py, call_timeline.py) on generated call
folders, never `var/`: a call's turns over a reply, in its tail and after a stop, each with the
texts that played over it; the alignment checked first, a shifted call refused whole; the owner's
labels, an overlap with none left out; the clips cut and written outside the golden set, their
manifest, items and replies written in it; the reviews as confirmations; and the refusals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals import import_calls
from ole5_voice.evals.audio import read_wav, write_wav
from ole5_voice.evals.call_timeline import overlaps, timeline
from ole5_voice.evals.import_calls import CallLabels, build, item_id, load_replies, write
from ole5_voice.evals.items import GoldenSetError, load_items, read_json
from ole5_voice.evals.models import Manifest

CALL = "CallA_1"
GREETING, FRAME, HEARD, LAST = "A made-up greeting.", "Echo frame.", "made-up words", "Last one."
# The call's timeline, in seconds from its start: the greeting (reply 0) plays from 0.2 to 2.0
# and turn 0 begins over it; reply 1's second clause plays over turn 1, until the caller's stop;
# turn 2 begins just after that stop (no tail); reply 2 plays to 6.5, and turn 3 begins in its
# tail; turn 4 begins over nothing.
TIMELINE: list[dict[str, Any]] = [
    {"t": 0.0, "event": "start", "call_id": CALL, "wall": "made-up", "consent": "v1"},
    {"t": 0.1, "event": "clause_asked", "reply_id": 0, "clause": 0, "text": GREETING},
    {"t": 0.2, "event": "clause_queued", "reply_id": 0, "clause": 0},
    {"t": 1.0, "event": "turn_opened", "turn_id": 0, "speech_s": 0.8},
    {"t": 1.6, "event": "turn_closed", "turn_id": 0, "speech_ended_s": 1.4},
    {"t": 2.0, "event": "clause_played", "reply_id": 0, "clause": 0},
    {"t": 3.0, "event": "clause_asked", "reply_id": 1, "clause": 0, "text": FRAME},
    {"t": 3.0, "event": "clause_asked", "reply_id": 1, "clause": 1, "text": HEARD},
    {"t": 3.1, "event": "clause_queued", "reply_id": 1, "clause": 0},
    {"t": 3.5, "event": "clause_played", "reply_id": 1, "clause": 0},
    {"t": 3.6, "event": "clause_queued", "reply_id": 1, "clause": 1},
    {"t": 3.9, "event": "turn_opened", "turn_id": 1, "speech_s": 3.7},
    {"t": 4.6, "event": "turn_closed", "turn_id": 1, "speech_ended_s": 4.4},
    {"t": 5.0, "event": "stop"},
    {"t": 5.0, "event": "stopped", "replies": [1]},
    {"t": 5.2, "event": "turn_opened", "turn_id": 2, "speech_s": 5.1},
    {"t": 5.9, "event": "clause_asked", "reply_id": 2, "clause": 0, "text": LAST},
    {"t": 6.0, "event": "clause_queued", "reply_id": 2, "clause": 0},
    {"t": 6.5, "event": "clause_played", "reply_id": 2, "clause": 0},
    {"t": 6.9, "event": "turn_opened", "turn_id": 3, "speech_s": 6.7},
    {"t": 8.0, "event": "turn_opened", "turn_id": 4, "speech_s": 7.8},
    {"t": 10.0, "event": "ended", "reason": "caller_left"},
]


def _call(recordings: Path, name: str, lines: list[dict[str, Any]], seconds: float = 9.95) -> Path:
    folder = recordings / name
    folder.mkdir(parents=True)
    pcm = b"".join((n % 20_000).to_bytes(2, "little") for n in range(round(seconds * 16_000)))
    (folder / "caller.wav").write_bytes(write_wav(pcm))
    text = "".join(json.dumps(line) + "\n" for line in lines)
    (folder / "timeline.jsonl").write_text(text, encoding="utf-8")
    return folder


def _labels(*overlaps: dict[str, Any]) -> CallLabels:
    return CallLabels.model_validate({"overlaps": list(overlaps)})


STOP = {"call": CALL, "turn": 0, "kind": "stop_word", "language": "saudi", "reference": "x  y"}
QUIET = {"call": CALL, "turn": 3, "kind": "echo_only", "language": "none", "device": "wired"}


def test_each_turn_over_a_reply_or_in_its_tail_carries_the_texts_played_over_it(
    tmp_path: Path,
) -> None:
    folder = _call(tmp_path, CALL, TIMELINE)
    found = overlaps(timeline(folder))
    assert [(o.turn, o.speech_s, o.stopped_s, o.reply) for o in found] == [
        (0, 0.8, 1.4, (GREETING,)),
        (1, 3.7, 4.4, (HEARD,)),  # the frame had played before its speech began
        (3, 6.7, 10.0, (LAST,)),  # in reply 2's tail, never closed: to the call's end
    ]


def test_the_labelled_overlaps_become_items_clips_and_replies(tmp_path: Path) -> None:
    recordings, evals, audio = tmp_path / "recordings", tmp_path / "evals", tmp_path / "audio"
    _call(recordings, CALL, TIMELINE)
    _call(recordings, "shifted", TIMELINE, seconds=10.2)  # its track runs past the call
    _call(recordings, "unended", TIMELINE[:-1])
    _call(recordings, "unread", [{"t": "soon"}])
    (_call(recordings, "untimed", TIMELINE) / "timeline.jsonl").unlink()
    (_call(recordings, "unwaved", TIMELINE) / "caller.wav").write_bytes(b"made-up")
    audio.mkdir()
    labels = _labels(STOP | {"word_end_ms": 500}, QUIET, STOP | {"call": "shifted"})
    found = build(recordings, labels, terms=())
    assert found.refused == ["shifted", "unended", "unread", "untimed", "unwaved"]
    assert found.unlabelled == [(CALL, 1)]
    write(evals, audio, found)
    stop, quiet = load_items(evals / "golden")
    assert (stop.id, stop.source, stop.kind, stop.text) == (
        "call-calla_1-turn-0",
        "talkover",
        "stop_word",
        "",
    )
    (variant,) = stop.variants
    assert (variant.reference, variant.reference_source, variant.confirmations) == (
        "x y",
        "typed",
        (),
    )
    assert (variant.turn_ends_ms, variant.tags, variant.session) == (
        (500,),
        ("call", "over-assistant"),
        "calls",
    )
    assert (quiet.variants[0].reference_source, quiet.variants[0].device) == ("none", "wired")
    clip = read_wav(audio / "call-calla_1-turn-0.wav")
    assert clip.seconds == pytest.approx(1.2)  # 0.3 s around its speech, 0.8 to 1.4
    assert clip.pcm16[:2] == round(0.5 * 16_000).to_bytes(2, "little")
    manifest = read_json(evals / "manifests" / "calls.json", Manifest)
    first = manifest.files[0]
    assert (first.path, first.sha256) == ("call-calla_1-turn-0.wav", clip.sha256)
    assert first.seconds == pytest.approx(1.2)
    assert load_replies(evals) == {
        "call-calla_1-turn-0": (GREETING,),
        "call-calla_1-turn-3": (LAST,),
    }
    write(evals, audio, found)  # again, the same: nothing refused


def test_the_owners_reviews_confirm_a_variant(tmp_path: Path) -> None:
    recordings, reviews = tmp_path / "recordings", tmp_path / "reviews"
    _call(recordings, CALL, TIMELINE)
    name = item_id(CALL, 0)
    review = {"take": name, "review_pass": 1, "at": "2026-11-04T10:00:00+03:00"}
    (reviews / "calls").mkdir(parents=True)
    path = reviews / "calls" / f"{name}.review-1.json"
    path.write_text(json.dumps(review | {"verdict": "confirmed"}), encoding="utf-8")
    found = build(recordings, _labels(STOP), terms=("y",), reviews=reviews)
    (item,) = found.items
    assert len(item.variants[0].confirmations) == 1 and item.terms == ("y",)


@pytest.mark.parametrize(
    ("labels", "problem"),
    [
        ([STOP, STOP], "twice"),
        ([STOP | {"turn": 4}], "no overlap"),
        ([STOP | {"language": "none"}], "no language is exactly one with no speech"),
    ],
)
def test_labels_the_import_refuses(
    tmp_path: Path, labels: list[dict[str, Any]], problem: str
) -> None:
    _call(tmp_path / "recordings", CALL, TIMELINE)
    with pytest.raises(GoldenSetError, match=problem):
        build(tmp_path / "recordings", _labels(*labels), terms=())


def test_a_clip_past_its_track_and_a_call_it_cannot_name_are_refused(tmp_path: Path) -> None:
    short = [*TIMELINE[:5], {"t": 0.4, "event": "ended", "reason": "caller_left"}]
    _call(tmp_path / "recordings", CALL, short, seconds=0.3)
    with pytest.raises(GoldenSetError, match="past its call's caller track"):
        build(tmp_path / "recordings", _labels(STOP), terms=())
    with pytest.raises(GoldenSetError, match="names no item"):
        item_id("a#b", 0)


def test_the_import_never_writes_over_another_file(tmp_path: Path) -> None:
    recordings, evals, audio = tmp_path / "recordings", tmp_path / "evals", tmp_path / "audio"
    _call(recordings, CALL, TIMELINE)
    audio.mkdir()
    found = build(recordings, _labels(STOP), terms=())
    (audio / "call-calla_1-turn-0.wav").write_bytes(b"another")
    with pytest.raises(GoldenSetError, match="another file of this name"):
        write(evals, audio, found)
    (audio / "call-calla_1-turn-0.wav").unlink()
    write(evals, audio, found)
    item = (evals / "golden" / "call-calla_1-turn-0.toml").read_text(encoding="utf-8")
    other = item.replace('"call", ', "")  # the same ID, from another import
    (evals / "golden" / "call-calla_1-turn-0.toml").write_text(other, encoding="utf-8")
    with pytest.raises(GoldenSetError, match="another import"):
        write(evals, audio, found)


def test_the_command(tmp_path: Path) -> None:
    recordings, evals, audio = tmp_path / "recordings", tmp_path / "evals", tmp_path / "audio"
    _call(recordings, CALL, TIMELINE)
    audio.mkdir()
    (evals / "golden").mkdir(parents=True)
    (evals / "terms.toml").write_text('terms = ["Outlook"]\n', encoding="utf-8")
    labels = tmp_path / "labels.toml"
    labels.write_text(
        '[[overlaps]]\ncall = "CallA_1"\nturn = 0\nkind = "stop_word"\nlanguage = "saudi"\n'
        'reference = "made-up"\n',
        encoding="utf-8",
    )
    argv = ["--recordings", str(recordings), "--labels", str(labels), "--audio", str(audio)]
    assert import_calls.main([*argv, "--evals", str(evals)]) == 0
    assert [i.id for i in load_items(evals / "golden")] == ["call-calla_1-turn-0"]
    _call(recordings, "shifted", TIMELINE, seconds=10.2)
    assert import_calls.main([*argv, "--evals", str(evals)]) == 1  # a call refused
    labels.write_text("[[overlaps]]\nturn = 0\n", encoding="utf-8")
    assert import_calls.main([*argv, "--evals", str(evals)]) == 1  # labels it cannot read
    assert import_calls.main([*argv[:4], "--audio", str(tmp_path / "absent")]) == 2
    assert load_replies(tmp_path / "absent") == {}
