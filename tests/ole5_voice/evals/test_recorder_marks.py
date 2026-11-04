"""The marks of a take of one clause (plan 005's step 11): a stop or pause word, or words said
over a reply, marked on the take's waveform as a take of several clauses is, the page read as
text (`recorder.js`) and the server run on a free port of 127.0.0.1 (`recorder_support.py`); a
kept stop word's mark required by both, carried by its sidecar and imported as its
`turn_ends_ms`, which the overlap run times the stop from. The review mode marks nothing."""

from __future__ import annotations

import re

import pytest
from ole5_voice.evals import import_recordings, recorder
from ole5_voice.evals.takes import Script, TakeSidecar

from tests.ole5_voice.evals.recorder_support import (
    CONSENT,
    Tree,
    post,
    recorder_of,
    serving,
    take,
)

# Two made-up lines of one clause, each said over the lab's reply: a pause word and a listening
# sound.
LINES = """
[[lines]]
id = "n05"
kind = "stop_word"
language = "english"
say = ["a made-up pause word"]
reply = "en_ticket"

[[lines]]
id = "n06"
kind = "listening_sound"
language = "english"
say = ["a made-up sound"]
reply = "en_ticket"
"""


def _script() -> str:
    return (recorder.PAGE / "recorder.js").read_text(encoding="utf-8")


def _function(script: str, name: str) -> str:
    """The body of the page's function `name`, up to the next function."""
    found = re.search(
        rf"\n  function {name}\(.*?(?=\n  (?:async )?function |\n  // -)", script, re.S
    )
    assert found is not None, name
    return found.group(0)


def test_the_page_marks_a_stop_word_and_words_over_a_reply_as_it_marks_several_clauses() -> None:
    script = _script()
    rule = _function(script, "marking")
    assert 'l.kind === "stop_word"' in rule and "l.reply" in rule
    assert "the end of the word" in rule  # the hint a stop or pause word's take shows
    record = _function(script, "renderRecord")
    assert "marks.needed && !page.take.marks.length" in record  # Keep waits for the mark
    assert '$("ends").hidden = !(page.take && marks.shown)' in record
    assert "several" not in record  # no line of one clause is left unmarked
    review = _function(script, "renderReview")
    assert not re.search(r"wave|marks|ends", review)  # the review mode marks nothing
    page = (recorder.PAGE / "index.html").read_text(encoding="utf-8")
    assert 'id="ends-hint"' in page and 'id="wave"' in page


@pytest.mark.parametrize(
    ("line", "ends", "status", "code"),
    [
        ("n05", (), "kept", 400),  # a kept stop word needs its word's end
        ("n05", (320,), "kept", 200),
        ("n05", (), "discarded", 200),
        ("n06", (), "kept", 200),  # words over a reply may be marked, not must
        ("n06", (410,), "kept", 200),
    ],
)
def test_a_take_of_one_clause_keeps_its_mark_in_its_sidecar(
    tree: Tree, line: str, ends: tuple[int, ...], status: str, code: int
) -> None:
    tree.script.write_text(tree.script.read_text(encoding="utf-8") + LINES, encoding="utf-8")
    with serving(recorder_of(tree)) as server:
        post(server, "api/consent", CONSENT)
        answer = post(server, "api/take", take(line, turn_ends_ms=list(ends), status=status))
    assert answer.status == code
    if code == 400:
        assert "needs its marks" in answer.json()["error"]
    written = list((tree.out / "laptop-1").glob(f"{line}-*.json"))
    assert [TakeSidecar.model_validate_json(p.read_bytes()).turn_ends_ms for p in written] == (
        [ends] if code == 200 else []
    )


def test_a_stop_words_mark_is_imported_as_its_turn_end(tree: Tree) -> None:
    tree.script.write_text(tree.script.read_text(encoding="utf-8") + LINES, encoding="utf-8")
    with serving(recorder_of(tree)) as server:
        post(server, "api/consent", CONSENT)
        post(server, "api/take", take("n05", turn_ends_ms=[320]))
    script = Script.model_validate(
        {"lines": [{"id": "n05", "kind": "stop_word", "language": "english", "say": ["a"]}]}
    )
    (item,) = import_recordings.build(tree.out, script)[0]
    assert [v.turn_ends_ms for v in item.variants] == [(320,)]
