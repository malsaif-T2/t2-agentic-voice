"""The matcher and Ole5's spelling guide: the guide's rulings quote the owner's words and date,
the matcher refuses a guide without one it applies, and its verdict compares the normalized
texts with every space removed (the prototype's `norm`), so a word split in two still counts."""

from __future__ import annotations

import json
import re
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals import matcher
from ole5_voice.evals.items import EVALS
from ole5_voice.evals.matcher import (
    COMPARISON_RULINGS,
    GuideError,
    GuideMatcher,
    load_guide,
    load_matcher,
)
from ole5_voice.evals.models import TICKET_KIND
from ole5_voice.evals.runs import Matcher
from t2_agentic_voice.languages import normalize_arabic

from tests.ole5_voice.evals.fakes import fake_normalize

SPELLING = EVALS / "spelling.toml"
CHARACTERIZATION = (
    Path(__file__).parents[2] / "t2_agentic_voice/fixtures/arabic_normalizer_characterization.json"
)
# The verdict string the spelling guide gives a row the prototype read otherwise (Q8).
GUIDE_VERDICT = {"digits spelled out": "57"}


def _fake() -> GuideMatcher:
    return load_matcher(SPELLING, normalize=fake_normalize)


def _guide_text(**changes: Any) -> dict[str, Any]:
    with SPELLING.open("rb") as file:
        guide: dict[str, Any] = tomllib.load(file)
    guide.update(changes)
    return guide


def _write(path: Path, guide: dict[str, Any]) -> Path:
    """A guide as TOML, written from its parsed form with JSON's escapes (TOML accepts them)."""
    lines = []
    for table in ("rulings", "spellings"):
        for entry in guide.get(table, []):
            lines.append(f"[[{table}]]")
            for key, value in entry.items():
                text = value.isoformat() if isinstance(value, date) else json.dumps(value)
                lines.append(f"{key} = {text}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_the_committed_guide_quotes_the_owner_for_every_ruling() -> None:
    guide = load_guide(SPELLING)
    assert {r.id for r in guide.rulings} >= set(COMPARISON_RULINGS)
    for ruling in guide.rulings:
        assert (ruling.said, ruling.on) == ("Use these rules", date(2026, 11, 1)), ruling.id
    assert guide.ruling("spaces").part == "comparison"
    assert guide.ruling("product-terms").part == "references"
    with pytest.raises(GuideError, match="no ruling 'made-up'"):
        guide.ruling("made-up")


def test_the_matcher_holds_the_comparison_rulings_it_applies() -> None:
    found = _fake()
    judge: Matcher = found  # the runner's protocol, checked by mypy
    assert judge.is_right("a", ["a"])
    assert [r.id for r in found.rulings] == list(COMPARISON_RULINGS)
    assert all(r.said and r.on == date(2026, 11, 1) for r in found.rulings)


def test_the_spellings_apply_to_their_kinds_and_quote_their_ruling() -> None:
    guide = load_guide(SPELLING)
    request = {r.id for r in guide.rules_for("request")}
    ticket = {r.id for r in guide.rules_for(TICKET_KIND)}
    assert request == {"product-term-outlook", "product-term-pdf", "product-term-word"}
    assert ticket == request | {"numbers-arabic", "numbers-english"}
    outlook = next(r for r in guide.rules_for("request") if r.id == "product-term-outlook")
    assert (outlook.write, outlook.said, outlook.on) == (
        "Outlook",
        "Use these rules",
        date(2026, 11, 1),
    )


def test_the_verdict_ignores_punctuation_case_and_spaces() -> None:
    judge = _fake()
    assert judge.is_right("Yes, submit.", ["yes submit"])
    assert judge.is_right("how do i  ARCHIVE it?", ["How do I archive it"])
    assert not judge.is_right("how do I archive", ["How do I archive it"])
    assert judge.is_right("", [""])  # nothing said, nothing heard
    assert not judge.is_right("Thank you.", [""])  # text from silence is wrong
    assert not judge.is_right("anything", [])


def test_a_word_split_in_two_is_counted_right() -> None:
    # The characterization case of plan 002's decision log: the verdict removes every space.
    judge = _fake()
    assert judge.is_right("لوسمحت", ["لو سمحت"])
    assert judge.is_right("تمام تمام", ["تمامتمام"])
    assert judge.is_right("mm hmm", ["mm-hmm"])
    assert judge.key("لو  سمحت") == judge.key("لوسمحت") == "لوسمحت"


def test_an_alternative_reference_counts_too() -> None:
    judge = _fake()
    assert judge.is_right("ok", ["okay", "ok"])
    assert not judge.is_right("oak", ["okay", "ok"])


def test_a_bare_string_of_references_is_a_type_error() -> None:
    with pytest.raises(TypeError, match="sequence of texts"):
        _fake().is_right("abc", "abc")


def test_the_matcher_refuses_a_guide_without_a_ruling_it_applies(tmp_path: Path) -> None:
    for missing in COMPARISON_RULINGS:
        guide = _guide_text()
        guide["rulings"] = [r for r in guide["rulings"] if r["id"] != missing]
        with pytest.raises(GuideError, match=f"no ruling '{missing}'"):
            load_matcher(_write(tmp_path / f"{missing}.toml", guide))
    guide = _guide_text()
    for ruling in guide["rulings"]:
        if ruling["id"] == "spaces":
            ruling["part"] = "references"
    with pytest.raises(GuideError, match="rule on comparison"):
        load_matcher(_write(tmp_path / "moved.toml", guide))


def test_a_ruling_without_the_owners_words_or_date_is_refused(tmp_path: Path) -> None:
    for field in ("said", "on", "ruling"):
        guide = _guide_text()
        del guide["rulings"][0][field]
        with pytest.raises(GuideError, match=re.escape("spelling.toml")):
            load_guide(_write(tmp_path / "spelling.toml", guide))


def test_a_guide_whose_spelling_cites_no_ruling_on_references_is_refused(tmp_path: Path) -> None:
    cases: list[tuple[str, int, dict[str, str]]] = [
        ("spellings", 0, {"ruling": "spaces"}),  # a ruling on comparison
        ("spellings", 0, {"ruling": "made-up"}),  # no such ruling
        ("rulings", 1, {"id": "letter-forms"}),  # the first ruling's id, twice
    ]
    for table, index, change in cases:
        guide = _guide_text()
        guide[table][index].update(change)
        with pytest.raises(GuideError, match=re.escape("spelling.toml")):
            load_guide(_write(tmp_path / "spelling.toml", guide))


def test_a_guide_that_is_not_toml_or_not_there_is_refused(tmp_path: Path) -> None:
    broken = tmp_path / "spelling.toml"
    broken.write_text('[[rulings]]\nid = "x\n', encoding="utf-8")
    with pytest.raises(GuideError, match=re.escape("spelling.toml")):
        load_guide(broken)
    with pytest.raises(GuideError, match=re.escape("absent.toml")):
        load_guide(tmp_path / "absent.toml")


def _library_normalizer() -> None:
    try:
        normalize_arabic("")
    except NotImplementedError:
        pytest.skip("the library's normalizer is not built on this branch yet (Track A)")


def test_the_library_normalizer_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fold(text: str) -> str:
        calls.append(text)
        return text.casefold()

    monkeypatch.setattr(matcher, "normalize_arabic", fold)
    monkeypatch.setattr(matcher, "normalize_digits", lambda t: t.replace("٥", "5"))
    judge = load_matcher(SPELLING)
    assert judge.is_right("A ٥", ["a5"])
    assert calls == ["A ٥", "a5"]


def test_the_verdict_on_the_characterization_table_is_the_prototypes_norm() -> None:
    # Run once the library's normalizer is built: each row's verdict string is the
    # prototype's `norm` column, or the guide's string on a row the guide rules otherwise.
    _library_normalizer()
    judge = load_matcher(SPELLING)
    rows = json.loads(CHARACTERIZATION.read_text(encoding="utf-8"))["rows"]
    for row in rows:
        expected = GUIDE_VERDICT[row["gap"]] if "gap" in row else row["norm"]
        assert judge.key(row["input"]) == expected, row["input"]
