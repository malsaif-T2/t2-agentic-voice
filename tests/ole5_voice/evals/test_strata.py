"""The strata: the items, their variants and the script's lines counted by each label, which
the committed set must hold as `strata.toml` registers them; and the script's lines as the
owner approved them: their counts, their spelling and their ticket numbers' shape."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime

from ole5_voice.evals.items import EVALS, Strata, count_strata, load_items, load_terms, read_toml
from ole5_voice.evals.matcher import load_guide
from ole5_voice.evals.models import TICKET_KIND, Item, Variant
from ole5_voice.evals.takes import Script
from t2_agentic_voice.languages import spelling_issues

from tests.ole5_voice.evals import samples


def test_the_strata_count_items_variants_and_script_lines() -> None:
    item = Item.model_validate(
        samples.item().model_dump()
        | {
            "variants": (
                samples.variant("v1"),
                Variant.model_validate(samples.variant("v2").model_dump() | {"tags": ("duck",)}),
            )
        }
    )
    script = Script.model_validate(
        {"lines": [{"id": "n1", "kind": "silence", "language": "none", "seconds": 4}]}
    )
    strata = count_strata([item], script)
    assert strata.items.model_dump() == {
        "total": 1,
        "source": {"script": 1},
        "language": {"english": 1},
        "kind": {"stop_word": 1},
        "device": {},
        "tag": {},
    }
    assert (strata.variants.total, strata.variants.device, strata.variants.tag) == (
        2,
        {"laptop": 2},
        {"duck": 1},
    )
    assert (strata.script.total, strata.script.kind) == (1, {"silence": 1})


# The script's lines by kind and language (Saudi, MSA, English, mixed, none): the agent's
# proposal in plan 002's registration ("New recordings (N)"), which the owner approved on
# 2026-11-01 (Q4).
PROPOSAL = {
    "request": (6, 4, 4, 4, 0),
    "paused_request": (4, 2, 2, 2, 0),
    "stop_word": (3, 1, 2, 0, 0),
    "repeat_request": (2, 1, 1, 0, 0),
    "listening_sound": (3, 0, 2, 0, 0),
    TICKET_KIND: (2, 1, 1, 0, 0),
    "silence": (0, 0, 0, 0, 1),
    "noise": (0, 0, 0, 0, 2),
    "echo_only": (0, 0, 0, 0, 2),
}
# Plan 005's lines, the agent's proposal there (Q2 and Q6, settled on 2026-11-03): said over a
# reply, but for the paused requests, which are said alone.
PLAN_005_PROPOSAL = {
    "stop_word": (6, 1, 3, 0, 0),
    "repeat_request": (2, 0, 1, 0, 0),
    "listening_sound": (3, 0, 2, 0, 0),
    "correction": (1, 0, 1, 0, 0),
    "echo_only": (0, 0, 0, 0, 1),
    "paused_request": (8, 4, 4, 4, 0),
}
LANGUAGES = ("saudi", "msa", "english", "mixed", "none")
# The lab's replies a line may be said over (its replies.json, read only: D-010).
REPLIES = {"ar_archive", "ar_inbox", "ar_password", "ar_ticket", "en_signature", "en_ticket"}


def _counted(proposal: Mapping[str, tuple[int, ...]]) -> Counter[tuple[str, str]]:
    return Counter(
        {
            (kind, language): n
            for kind, counts in proposal.items()
            for language, n in zip(LANGUAGES, counts, strict=True)
            if n
        }
    )


def test_the_script_holds_the_approved_proposals_lines() -> None:
    script = read_toml(EVALS / "script.toml", Script)
    plan_002, plan_005 = script.lines[:52], script.lines[52:]
    assert Counter((line.kind, line.language) for line in plan_002) == _counted(PROPOSAL)
    assert Counter((line.kind, line.language) for line in plan_005) == _counted(PLAN_005_PROPOSAL)
    assert len(script.lines) == 93 and len({line.id for line in script.lines}) == 93
    over = [line for line in plan_005 if line.kind != "paused_request"]
    assert all(line.reply in REPLIES for line in over)
    assert not any(line.reply for line in plan_005 if line.kind == "paused_request")
    assert [line.text for line in plan_005].count("وقف") == 3


def test_the_scripts_lines_follow_the_spelling_guide() -> None:
    script = read_toml(EVALS / "script.toml", Script)
    terms = set(load_terms(EVALS / "terms.toml"))
    guide = load_guide(EVALS / "spelling.toml")
    for line in script.lines:
        assert set(line.terms) <= terms, line.id
        assert all(term in line.text for term in line.terms), line.id
        assert spelling_issues(line.text, guide.rules_for(line.kind)) == [], line.id
        silent = line.language == "none"
        assert silent == (line.text == ""), line.id  # no speech exactly where no language
        if line.kind == "listening_sound":
            assert line.text in script.listening_sounds, line.id
        if line.kind == "echo_only":
            assert line.reply in REPLIES, line.id


# An Ole5 ticket number, in the shape the owner gave on 2026-11-01 (plan 002, Q5): 16 digits,
# the date as YYYYMMDD, then 82, then a 6-digit counter.
TICKET_NUMBER = re.compile(r"(?P<date>[0-9]{8})82[0-9]{6}")


def test_the_scripts_ticket_numbers_are_made_up_in_the_owners_shape() -> None:
    script = read_toml(EVALS / "script.toml", Script)
    numbers = {
        line.id: re.findall(r"[0-9]+", line.text)
        for line in script.lines
        if line.kind == TICKET_KIND
    }
    assert all(len(found) == 1 for found in numbers.values()), numbers  # one number, in digits
    full = {name: number for name, [number] in numbers.items() if len(number) != 4}
    assert len(full) == 2 and len(set(full.values())) == 2, numbers  # and two of a last four
    cues = {line.id: line.cue for line in script.lines}
    for name, number in full.items():
        shaped = TICKET_NUMBER.fullmatch(number)
        assert shaped is not None, name
        # Dated after the day the owner gave the shape, so never one of the owner's examples,
        # on a day of two digits, so only the counter starts with zeros a reading may drop.
        day = datetime.strptime(shaped["date"], "%Y%m%d").date()
        assert date(2026, 11, 1) < day <= date(2026, 12, 31) and day.day >= 10, name
        # The reference keeps the counter's zeros, so the cue asks for each, on this counter.
        assert "every zero" in cues[name] and number[-6:] in cues[name], name
    assert not [line.id for line in script.lines if "DRAFT" in line.cue]


def test_the_committed_set_holds_its_registered_strata() -> None:
    registered = read_toml(EVALS / "strata.toml", Strata)
    counted = count_strata(load_items(EVALS / "golden"), read_toml(EVALS / "script.toml", Script))
    assert counted == registered
    # The set as the registration describes it: the talk-over's 120 takes with segments, less
    # the two the owner left out after the review (`import_talkover.LEFT_OUT`), all on the
    # laptop's microphone array, 3 played on a headset; and the script's 52 items with every
    # take the owner kept, 97 on the laptop, 63 on the wired headset, 59 on the Bluetooth one.
    assert (registered.items.source, registered.variants.total) == (
        {"script": 52, "talkover": 43},
        118 + 219,
    )
    assert registered.variants.device == {"bluetooth": 59, "laptop": 118 + 97, "wired": 63}
    assert registered.variants.tag["playback-headset"] == 3
