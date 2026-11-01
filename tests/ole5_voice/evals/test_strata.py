"""The strata: the items, their variants and the script's lines counted by each label, which
the committed set must hold as `strata.toml` registers them."""

from __future__ import annotations

from collections import Counter

from ole5_voice.evals.items import EVALS, count_strata, load_terms
from ole5_voice.evals.models import TICKET_KIND, Item, Variant
from ole5_voice.evals.takes import Script, load_script

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


# The draft script's lines by kind and language (Saudi, MSA, English, mixed, none): the agent's
# proposal in plan 002's registration ("New recordings (N)"), until the owner approves it (Q4).
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
LANGUAGES = ("saudi", "msa", "english", "mixed", "none")


def test_the_draft_script_holds_the_proposals_lines() -> None:
    script = load_script(EVALS / "script.toml")
    found = Counter((line.kind, line.language) for line in script.lines)
    expected = {
        (kind, language): n
        for kind, counts in PROPOSAL.items()
        for language, n in zip(LANGUAGES, counts, strict=True)
        if n
    }
    assert dict(found) == expected
    assert len(script.lines) == 52 and len({line.id for line in script.lines}) == 52


def test_the_draft_scripts_lines_follow_the_spelling_guide() -> None:
    script = load_script(EVALS / "script.toml")
    terms = set(load_terms(EVALS / "terms.toml"))
    for line in script.lines:
        assert set(line.terms) <= terms, line.id
        assert all(term in line.text for term in line.terms), line.id
        silent = line.language == "none"
        assert silent == (line.text == ""), line.id  # no speech exactly where no language
        if line.kind == "listening_sound":
            assert line.text in script.listening_sounds, line.id
        if line.kind == "echo_only":
            assert line.reply in {"ar_inbox", "en_signature"}, line.id
