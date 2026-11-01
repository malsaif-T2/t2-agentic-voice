"""The golden set's shared models parse strictly: an item round-trips, and a path, a name, a
hash or a count that cannot be right is refused as it is read."""

from __future__ import annotations

from typing import get_args

import pytest
from ole5_voice.evals.models import (
    AudioRef,
    HistoryLine,
    Item,
    Manifest,
    Outcome,
    Review,
    ScriptLine,
    TakeSidecar,
    Variant,
)
from pydantic import ValidationError
from t2_agentic_voice.core.errors import PROVIDER_ERROR_KINDS

SHA = "0123456789abcdef" * 4
SEGMENT = {"root": "talkover", "path": "s01_archive__duck__speakers__181825__seg1.wav"}
VARIANT: dict[str, object] = {
    "id": "s01_archive__duck__speakers__181825",
    "segments": [SEGMENT | {"sha256": SHA}],
    "device": "laptop",
    "session": "talkover-2026-10-27",
    "reference": "كيف أؤرشف مراسلة في النظام؟",
    "reference_source": "script",
    "confirmations": [{"at": "2026-11-02T10:00:00Z", "review_pass": 1}],
    "tags": ["over-assistant", "duck"],
}
ITEM: dict[str, object] = {
    "id": "s01_archive",
    "source": "talkover",
    "kind": "request",
    "language": "saudi",
    "text": "كيف أؤرشف مراسلة في النظام؟",
    "variants": [VARIANT],
}


def test_an_item_reads_from_data_and_round_trips() -> None:
    item = Item.model_validate(ITEM)
    assert item.variants[0].segments[0].root == "talkover"
    assert Item.model_validate_json(item.model_dump_json()) == item


@pytest.mark.parametrize(
    "path", ["", "/etc/passwd", "../.env", "a/../../b", "a\\b", "C:/x", "./a", "a//b"]
)
def test_an_audio_path_stays_below_its_root(path: str) -> None:
    with pytest.raises(ValidationError, match="relative path below its root"):
        AudioRef.model_validate({"root": "owner", "path": path, "sha256": SHA})


def test_a_path_below_its_root_is_kept_as_written() -> None:
    ref = AudioRef.model_validate({"root": "owner", "path": "wired/take-01.wav", "sha256": SHA})
    assert ref.path == "wired/take-01.wav"


@pytest.mark.parametrize(
    "change",
    [
        {"id": "Has Spaces"},
        {"segments": []},  # a variant has its audio
        {"segments": [SEGMENT | {"sha256": "abc"}]},
        {"device": "phone"},
        {"reference_source": "guessed"},
        {"turn_ends_ms": [1800, 500]},  # in order
        {"turn_ends_ms": [500, 500]},
        {"turn_ends_ms": [-1]},
        {"confirmations": [{"at": "2026-11-02T10:00:00Z", "review_pass": 0}]},
        {"spoken": "x"},  # a misspelt or unknown field
    ],
)
def test_a_variant_that_cannot_be_right_is_refused(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Variant.model_validate(VARIANT | change)
    assert Variant.model_validate(VARIANT | {"turn_ends_ms": [500, 1800]}).turn_ends_ms == (
        500,
        1800,
    )


@pytest.mark.parametrize(
    "change", [{"kind": "Stop Word"}, {"language": "arabic"}, {"variants": []}]
)
def test_an_item_that_cannot_be_right_is_refused(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Item.model_validate(ITEM | change)


def test_a_manifest_holds_its_consent_and_files() -> None:
    manifest = Manifest.model_validate(
        {
            "root": "owner",
            "consent": {
                "speaker": "the owner",
                "agreed": True,
                "on": "2026-11-02",
                "words": "I agree to these recordings' use in this golden set.",
            },
            "files": [
                {
                    "path": "laptop/take-01.wav",
                    "sha256": SHA,
                    "seconds": 2.5,
                    "sample_rate": 16000,
                    "device": "laptop",
                    "session": "laptop-1",
                }
            ],
        }
    )
    assert manifest.consent is not None and manifest.consent.agreed
    with pytest.raises(ValidationError):
        Manifest.model_validate(manifest.model_dump() | {"consent": {"agreed": False}})


def test_a_script_line_joins_its_clauses() -> None:
    line = ScriptLine.model_validate(
        {"id": "n01", "kind": "multi_clause_request", "language": "english", "say": ["a", "b"]}
    )
    assert line.text == "a b"
    silence = {"id": "n02", "kind": "silence", "language": "none", "seconds": 4}
    assert ScriptLine.model_validate(silence).text == ""


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


def test_an_outcome_is_ok_stuck_or_a_provider_error_kind() -> None:
    assert set(get_args(Outcome)) == {"ok", "stuck", *PROVIDER_ERROR_KINDS}


def test_a_history_line_names_its_commit() -> None:
    line: dict[str, object] = {
        "time": "2026-11-03T09:00:00Z",
        "commit": "0f44056+",
        "run": "r1",
        "answerer": "groq",
        "model": "whisper-large-v3",
        "settings": {"stt.model": "whisper-large-v3", "groq.api_key": "set"},
        "split": "dev",
        "items": 60,
        "variants": 196,
        "accuracy": 0.41,
        "violations": 0,
        "billed_seconds": 1960.0,
        "cost_usd": 0.06,
        "latency_median_ms": 295.0,
        "breakdowns": {"language": {"saudi": 0.3}},
        "scorecard": "scorecard.json",
        "data_digest": SHA,
        "note": "the baseline, large-v3",
        "complete": True,
    }
    assert HistoryLine.model_validate(line).commit == "0f44056+"
    with pytest.raises(ValidationError):
        HistoryLine.model_validate(line | {"commit": "main"})
