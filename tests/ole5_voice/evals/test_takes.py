"""The recorder's files: the script both the recorder and the import read, the session record
that carries the speaker's consent, a take's sidecar and its reviews, and where each is written
below `--out`."""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.evals.items import GoldenSetError, read_toml
from ole5_voice.evals.takes import (
    Review,
    Script,
    ScriptLine,
    SessionRecord,
    TakeSidecar,
    parse_review_file,
    review_file,
    session_file,
    take_audio,
    take_sidecar,
)
from pydantic import ValidationError

SHA = "0123456789abcdef" * 4
CONSENT = {"speaker": "the owner", "agreed": True, "on": "2026-11-02", "words": "I agree."}
SCRIPT = """\
listening_sounds = ["اها", "امم", "mm-hmm"]

[[lines]]
id = "n01"
kind = "multi_clause_request"
language = "english"
say = ["open a ticket", "about my mail"]

[[lines]]
id = "n02"
kind = "silence"
language = "none"
seconds = 4
"""


def test_a_script_line_joins_its_clauses() -> None:
    line = ScriptLine.model_validate(
        {"id": "n01", "kind": "multi_clause_request", "language": "english", "say": ["a", "b"]}
    )
    assert line.text == "a b"
    silence = {"id": "n02", "kind": "silence", "language": "none", "seconds": 4}
    assert ScriptLine.model_validate(silence).text == ""


def test_the_script_reads_its_lines_and_listening_sounds(tmp_path: Path) -> None:
    path = tmp_path / "script.toml"
    path.write_text(SCRIPT, encoding="utf-8")
    script = read_toml(path, Script)
    assert script.listening_sounds == ("اها", "امم", "mm-hmm")
    assert [(line.id, line.text) for line in script.lines] == [
        ("n01", "open a ticket about my mail"),
        ("n02", ""),
    ]
    for broken in (SCRIPT.replace("[[lines]]", "[[line]]"), 'listening_sounds = ["x"]\n'):
        path.write_text(broken, encoding="utf-8")  # a misspelt table; no line at all
        with pytest.raises(GoldenSetError, match=r"script\.toml: \d problem\(s\), the first at "):
            read_toml(path, Script)


def test_a_lines_takes_have_a_scripted_reference_only_when_it_has_words() -> None:
    """The recorder and the import give a take of a line its reference source alike."""
    line = {"id": "n01", "kind": "request", "language": "english"}
    assert ScriptLine.model_validate(line | {"say": ["a b"]}).source == "script"
    for silent in ({}, {"say": [""]}):
        assert ScriptLine.model_validate(line | silent).source == "none", silent


def test_a_reviews_file_name_is_read_one_way() -> None:
    """The recorder and the import read a review's file name alike, as `review_file` builds it:
    a take's name and a pass of at most six digits, the most a review records."""
    assert parse_review_file("n01-laptop-1-2.review-3.json") == ("n01-laptop-1-2", 3)
    assert parse_review_file("n01.review-999999.json") == ("n01", 999_999)
    for name in ("n01.review-1000000.json", "n01.review-0.json", "N01.review-1.json", "n01.json"):
        assert parse_review_file(name) is None, name
    fields = {"take": "n01", "at": "2026-11-02T10:00:00Z", "verdict": "confirmed"}
    assert Review.model_validate(fields | {"review_pass": 999_999}).review_pass == 999_999
    with pytest.raises(ValidationError):
        Review.model_validate(fields | {"review_pass": 1_000_000})


def test_a_session_record_holds_its_speakers_consent() -> None:
    record = SessionRecord.model_validate(
        {"session": "laptop-1", "device": "laptop", "consent": CONSENT}
    )
    assert record.consent.agreed
    with pytest.raises(ValidationError):
        SessionRecord.model_validate({"session": "laptop-1", "device": "laptop"})


def test_a_take_and_its_review_parse() -> None:
    take = TakeSidecar.model_validate(
        {
            "take": "n01-laptop-1",
            "line": "n01",
            "session": "laptop-1",
            "device": "laptop",
            "microphone": "Microphone Array",
            "track": {"echo_cancellation": True, "sample_rate": 16000},
            "recorded_at": "2026-11-02T10:00:00Z",
            "file": "n01-laptop-1.wav",
            "sha256": SHA,
            "seconds": 3.2,
            "turn_ends_ms": [3100],
            "status": "kept",
        }
    )
    review = Review.model_validate(
        {"take": take.take, "review_pass": 1, "at": "2026-11-02T11:00:00Z", "verdict": "typed"}
    )
    assert (take.track.noise_suppression, review.text) == (None, "")


def test_each_file_has_its_place_below_out() -> None:
    assert session_file("laptop-1") == "laptop-1/session.json"
    assert take_audio("laptop-1", "n01-1") == "laptop-1/n01-1.wav"
    assert take_sidecar("laptop-1", "n01-1") == "laptop-1/n01-1.json"
    assert review_file("laptop-1", "n01-1", 2) == "laptop-1/n01-1.review-2.json"


@pytest.mark.parametrize(("session", "take"), [("laptop-1", "nul"), ("con", "n01"), ("..", "x")])
def test_a_name_that_is_no_plain_file_is_refused(session: str, take: str) -> None:
    """A take named `nul` would be written to Windows' null device, and lost."""
    with pytest.raises(ValueError, match="relative path below its root"):
        take_audio(session, take)
