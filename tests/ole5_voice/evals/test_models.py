"""The golden set's shared models parse strictly: an item round-trips, and a path, a name, a
hash or a count that cannot be right is refused as it is read."""

from __future__ import annotations

import re

import pytest
from ole5_voice.evals.models import (
    OTHER,
    TICKET_KIND,
    AudioRef,
    Item,
    Kind,
    Manifest,
    SplitFile,
    Variant,
)
from pydantic import TypeAdapter, ValidationError

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
    "want": "send",
    "variants": [VARIANT],
}


def test_an_item_reads_from_data_and_round_trips() -> None:
    item = Item.model_validate(ITEM)
    assert (item.variants[0].segments[0].root, item.want) == ("talkover", "send")
    assert Item.model_validate_json(item.model_dump_json()) == item
    assert Item.model_validate(ITEM | {"want": None}).want is None


@pytest.mark.parametrize(
    "path",
    [
        *["", "/etc/passwd", "../.env", "a/../../b", "a\\b", "C:/x", "./a", "a//b", "a/./b"],
        *["//host/share", "a:b", ".", "...", ".. /x"],  # a UNC path, a stream, the root itself
        # Windows device names, with any extension: reading gives nothing, writing loses it.
        *["nul", "NUL.", "nul ", "a/nul", "nul.wav", "a/con.wav", "CON.txt", "com1", "lpt¹"],
        *["a.wav.", "a.wav ", "a/b.", "a/b "],  # Windows drops the end: another file's alias
        *["a\x00b", "a\tb", "a*b", 'a"b', "a<b", "a|b"],
    ],
)
def test_an_audio_path_stays_below_its_root(path: str) -> None:
    with pytest.raises(ValidationError, match="relative path below its root"):
        AudioRef.model_validate({"root": "owner", "path": path, "sha256": SHA})


@pytest.mark.parametrize("path", ["wired/take-01.wav", "nulled.wav", "con-call/aux_1.wav", "a.b/c"])
def test_a_path_below_its_root_is_kept_as_written(path: str) -> None:
    ref = AudioRef.model_validate({"root": "owner", "path": path, "sha256": SHA})
    assert ref.path == path


def test_a_refused_value_is_never_echoed() -> None:
    """A model's error names the field, never what it refused: a transcript, a key."""
    made_up = "gsk_made-up-key-for-tests-0123456789"
    with pytest.raises(ValidationError) as raised:
        AudioRef.model_validate({"root": "owner", "path": f"/{made_up}", "sha256": made_up})
    assert made_up not in str(raised.value) and made_up not in repr(raised.value)


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
    "change",
    [{"kind": "Stop Word"}, {"language": "arabic"}, {"variants": []}, {"want": "Send It"}],
)
def test_an_item_that_cannot_be_right_is_refused(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Item.model_validate(ITEM | change)


def test_the_ticket_kind_is_a_kind() -> None:
    """The golden set and the scorecard agree on it: the ticket items carry it, and the
    scorecard scores ID recall over them."""
    assert TypeAdapter(Kind).validate_python(TICKET_KIND) == "ticket_number"


def test_no_kind_takes_the_held_out_pooled_groups_name() -> None:
    """A held-out run pools its smaller groups into one, `OTHER`, which no kind may be named,
    so the two never merge."""
    assert OTHER == "other"
    with pytest.raises(ValidationError, match="pooled group of a held-out run"):
        TypeAdapter(Kind).validate_python(OTHER)
    with pytest.raises(ValidationError, match="pooled group"):
        Item.model_validate(ITEM | {"kind": OTHER})


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
    refused = manifest.model_dump()
    refused["consent"]["agreed"] = False  # only the flag: the rest of the record stays whole
    with pytest.raises(ValidationError) as raised:
        Manifest.model_validate(refused)
    assert [(e["type"], e["loc"]) for e in raised.value.errors()] == [
        ("literal_error", ("consent", "agreed"))
    ]


def test_the_split_file_maps_each_item_to_its_split() -> None:
    split = SplitFile.model_validate_json(
        '{"salt": "m1", "items": {"s01": "dev", "k05": "held-out"}}'
    )
    assert split.items == {"s01": "dev", "k05": "held-out"}
    for bad in ('{"salt": "m1", "items": {}}', '{"salt": "", "items": {"s01": "dev"}}'):
        with pytest.raises(ValidationError):
            SplitFile.model_validate_json(bad)
    with pytest.raises(ValidationError, match=re.escape("items.s01")):
        SplitFile.model_validate({"salt": "m1", "items": {"s01": "test"}})
