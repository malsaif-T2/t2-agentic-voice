"""The matcher: whether an output says a reference, under Ole5's spelling guide.

What counts as right lives here alone (evaluation.md, "The golden set"). The guide is
`evals/spelling.toml`: each ruling in it quotes the owner's words and their date (plan 002,
Q8). Its comparison rulings are the matcher's: both texts are normalized with the library's
`normalize_arabic` and `normalize_digits`, and compared with every space removed, as the
prototype's `norm` compared them (`Ole5-chatbot/scripts/stt_eval.py`, lines 1062-1066 and
1085), so two words written as one still count. Since a digit's name is read only as a whole
word, the texts are also compared with their spaces removed before the digits are read: "some
one" is "someone" there, as it was in the prototype's form. The matcher refuses a guide that
lacks one of the rulings it applies. Its rulings on how references are written are the spellings
`poe golden` checks every reference against.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Annotated, Final, Literal, Self

from pydantic import Field, StringConstraints, model_validator
from t2_agentic_voice.languages import SpellingRule, normalize_arabic, normalize_digits

from ole5_voice.evals.files import read_model
from ole5_voice.evals.models import Kind, Model

RulingId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]*$")]
# The comparison rulings the verdict applies, each by its ID in the guide; a guide without one
# of them is refused, so the matcher never judges by a ruling nobody made.
COMPARISON_RULINGS: Final = ("letter-forms", "digits", "english-case", "punctuation", "spaces")
# The ruling that listening sounds come from the script's fixed list (`poe golden` applies it).
LISTENING_SOUNDS_RULING: Final = "listening-sounds"


class GuideError(ValueError):
    """A spelling guide that cannot be read, or that lacks a ruling the matcher applies."""


class Ruling(Model):
    """One ruling of the guide: the rule as it was put to the owner, the owner's own words,
    and the day."""

    id: RulingId
    part: Literal["comparison", "references"]  # how outputs are compared, or references written
    ruling: str = Field(min_length=1)
    said: str = Field(min_length=1)  # the owner's words, quoted
    on: date


class Spelling(Model):
    """Spellings a reference must not hold under one ruling, and what to write instead; for the
    item kinds named, or for every item when none is."""

    id: RulingId
    ruling: RulingId  # the `references` ruling it applies
    avoid: tuple[str, ...] = Field(min_length=1)
    write: str
    kinds: tuple[Kind, ...] = ()


class SpellingGuide(Model):
    """`evals/spelling.toml`: the rulings, then the spellings to avoid."""

    rulings: tuple[Ruling, ...] = Field(min_length=1)
    spellings: tuple[Spelling, ...] = ()

    @model_validator(mode="after")
    def _ids_unique_and_cited(self) -> Self:
        ids = [r.id for r in self.rulings] + [s.id for s in self.spellings]
        if len(set(ids)) != len(ids):
            raise ValueError("every ruling and spelling has its own id")
        references = {r.id for r in self.rulings if r.part == "references"}
        if any(s.ruling not in references for s in self.spellings):
            raise ValueError("each spelling applies a ruling on how references are written")
        return self

    def ruling(self, ruling_id: str) -> Ruling:
        """The ruling of that ID; GuideError when the guide has none."""
        for ruling in self.rulings:
            if ruling.id == ruling_id:
                return ruling
        raise GuideError(f"the spelling guide has no ruling '{ruling_id}'")

    def rules_for(self, kind: str) -> list[SpellingRule]:
        """The spellings that apply to an item of `kind`, as the library's `SpellingRule`s,
        each quoting its ruling's words and date."""
        rules = []
        for spelling in self.spellings:
            if spelling.kinds and kind not in spelling.kinds:
                continue
            ruling = self.ruling(spelling.ruling)
            rules.append(
                SpellingRule(
                    id=spelling.id,
                    avoid=spelling.avoid,
                    write=spelling.write,
                    said=ruling.said,
                    on=ruling.on,
                )
            )
        return rules


def load_guide(path: Path) -> SpellingGuide:
    """The spelling guide in `path`, checked as it is read; GuideError, naming the file and the
    fields only, when it cannot be read (`files.read_model`)."""
    return read_model(
        path, SpellingGuide, lambda problem: GuideError(f"{path.name}: {problem}"), toml=True
    )


def normalize(text: str) -> str:
    """The form every scorer compares, the app's one copy of it: the library's normalizers in
    the prototype's order, the text's canonical Arabic form, then its digits read as 0 to 9
    (`stt_eval.py`, lines 1062-1066). The verdict, a window's words (`run_parts.Parts`) and a
    reference's words (`scorecard.write_scorecard`) are all counted in it. The library's own,
    `scored_form`, is in no facade (the owner's ruling, plan 004): a test ties the two."""
    return normalize_digits(normalize_arabic(text))


def joined(text: str) -> str:
    """`text` in its canonical Arabic form with every space removed, and only then its digits
    read: the prototype's form (`stt_eval.py`, lines 1062-1066), but for a whole text that is
    one digit's name. A digit name inside a word written in two ("some one", "five 7") or cut
    by a format character stays part of the word, so spaces count for nothing (Q8)."""
    return normalize_digits("".join(normalize_arabic(text).split()))


class GuideMatcher:
    """The `Matcher` of a spelling guide: right when the output equals one reference after
    normalization, both with every space removed (`key`), or in their `joined` form."""

    def __init__(
        self,
        rulings: Sequence[Ruling],
        *,
        normalize: Callable[[str], str] = normalize,
        joined: Callable[[str], str] | None = joined,
    ) -> None:
        self.rulings = tuple(rulings)
        self._normalize = normalize
        self._joined = joined

    def key(self, text: str) -> str:
        """What the verdict compares: `text` normalized, with every space removed."""
        return "".join(self._normalize(text).split())

    def is_right(self, output: str, references: Sequence[str]) -> bool:
        if isinstance(references, str):
            raise TypeError("references is a sequence of texts (the reference and alternatives)")
        heard = self.key(output)
        if any(heard == self.key(reference) for reference in references):
            return True
        if self._joined is None:
            return False
        whole = self._joined(output)
        return any(whole == self._joined(reference) for reference in references)


def load_matcher(spelling: Path, *, normalize: Callable[[str], str] | None = None) -> GuideMatcher:
    """The matcher of the spelling guide in `spelling` (`evals/spelling.toml`); GuideError when
    the guide lacks one of `COMPARISON_RULINGS`. `normalize` stands in for the library's
    normalizers, for a test, which then compares by `key` alone."""
    guide = load_guide(spelling)
    rulings = [guide.ruling(ruling_id) for ruling_id in COMPARISON_RULINGS]
    if any(ruling.part != "comparison" for ruling in rulings):
        raise GuideError(f"{spelling.name}: {', '.join(COMPARISON_RULINGS)} rule on comparison")
    if normalize is None:
        return GuideMatcher(rulings)
    return GuideMatcher(rulings, normalize=normalize, joined=None)
