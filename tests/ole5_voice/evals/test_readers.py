"""Every reader of the golden set's and the runs' files refuses a broken file without echoing what
it holds (`files.py`): a value planted in each, where a refusal that quoted its input would show
it, is never in the error's text, and no exception chain leads to it, since a pydantic error
holds the input it refused even where its text hides it (plan 004, app0 and app1)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from ole5_voice.evals import files, history, import_talkover, items, matcher, recorder_load
from ole5_voice.evals import scorecard as scorecards
from ole5_voice.evals.audio import Wav
from ole5_voice.evals.models import Item, Manifest
from ole5_voice.evals.recorder_state import RecorderError
from ole5_voice.evals.run_parts import clip_answers
from t2_agentic_voice import InvalidRequestError

PLANTED = "SECRET-1"  # short, so even a shortened echo of its record would show it whole
SCRIPT = '[[lines]]\nid = "n01"\nkind = "request"\nlanguage = "english"\nsay = ["a b"]\n'


def _write(path: Path, text: str | bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def _no_audio(path: Path) -> Wav:
    raise AssertionError("no audio is read")


def _item(tmp: Path) -> object:
    return items.read_toml(_write(tmp / "i1.toml", f'id = "{PLANTED}"\n'), Item)


def _not_toml(tmp: Path) -> object:
    return items.read_toml(_write(tmp / "i1.toml", f'id = "{PLANTED}\n'), Item)


def _not_utf8(tmp: Path) -> object:
    return items.read_json(_write(tmp / "m.json", PLANTED.encode() + b"\xff\xfe"), Manifest)


def _toml_not_utf8(tmp: Path) -> object:
    text = f'id = "{PLANTED}'.encode() + b'\xff"\n'
    return items.read_toml(_write(tmp / "i1.toml", text), Item)


def _manifest(tmp: Path) -> object:
    return items.read_json(_write(tmp / "m.json", json.dumps({"root": PLANTED})), Manifest)


def _guide(tmp: Path) -> object:
    return matcher.load_guide(_write(tmp / "spelling.toml", f'[[rulings]]\nid = "{PLANTED}"\n'))


def _lab(tmp: Path) -> object:
    _write(tmp / "lab" / "refs.json", json.dumps({"a.wav": {"text": PLANTED}}))
    return import_talkover.build(tmp / "lab", terms=[], describe=_no_audio)


def _script(tmp: Path) -> object:
    script = _write(tmp / "script.toml", f'[[lines]]\nid = "{PLANTED}"\n')
    return recorder_load.load_recorder(out=tmp / "out", script=script)


def _session(tmp: Path) -> object:
    _write(tmp / "out" / "s1" / "session.json", json.dumps({"session": PLANTED}))
    return recorder_load.load_recorder(out=tmp / "out", script=_write(tmp / "s.toml", SCRIPT))


def _replies(tmp: Path) -> object:
    _write(tmp / "replies" / "replies.json", json.dumps([{"id": PLANTED, "file": 1}]))
    script = _write(tmp / "s.toml", SCRIPT)
    return recorder_load.load_recorder(out=tmp / "out", script=script, replies=tmp / "replies")


def _scorecard(tmp: Path) -> object:
    return scorecards.load_scorecard(_write(tmp / "card.json", json.dumps({"run": PLANTED})))


def _history(tmp: Path) -> object:
    return history.read_history(_write(tmp / "h.jsonl", json.dumps({"run": PLANTED}) + "\n"))


def _history_bytes(tmp: Path) -> object:
    return history.read_history(_write(tmp / "h.jsonl", PLANTED.encode() + b"\xff\n"))


def _clips_from(tmp: Path) -> object:
    card = _write(tmp / "card.json", json.dumps({"run": {"name": PLANTED}}))
    return clip_answers(card, (), commit="ab" * 20, model="whisper-large-v3")


READERS: dict[str, tuple[Callable[[Path], object], type[Exception]]] = {
    "an item": (_item, items.GoldenSetError),
    "a file that is not TOML": (_not_toml, items.GoldenSetError),
    "a file that is not UTF-8": (_not_utf8, items.GoldenSetError),
    "a TOML file that is not UTF-8": (_toml_not_utf8, items.GoldenSetError),
    "a manifest": (_manifest, items.GoldenSetError),
    "the spelling guide": (_guide, matcher.GuideError),
    "the lab's refs.json": (_lab, items.GoldenSetError),
    "the recorder's script": (_script, RecorderError),
    "a session record": (_session, RecorderError),
    "replies.json": (_replies, RecorderError),
    "a scorecard": (_scorecard, scorecards.EvalDataError),
    "a history line": (_history, scorecards.EvalDataError),
    "a history that is not UTF-8": (_history_bytes, scorecards.EvalDataError),
    "--clips-from": (_clips_from, InvalidRequestError),
}


@pytest.mark.parametrize("reader", sorted(READERS))
def test_a_broken_file_is_refused_without_echoing_it(tmp_path: Path, reader: str) -> None:
    read, error = READERS[reader]
    with pytest.raises(error) as refused:
        read(tmp_path)
    assert PLANTED not in str(refused.value) and PLANTED not in repr(refused.value)
    assert refused.value.__cause__ is None and refused.value.__context__ is None


def test_a_problem_is_told_by_its_fields() -> None:
    def refuse(problem: str) -> ValueError:
        return ValueError(problem)

    with pytest.raises(ValueError, match=r"^1 problem\(s\), the first at the top level: Invalid"):
        files.parse_json(tuple[int, int], f'["{PLANTED}', refuse)
    with pytest.raises(ValueError, match=r"^1 problem\(s\), the first at 1: Input should be"):
        files.parse_json(tuple[int, int], f'[1, "{PLANTED}"]', refuse)
