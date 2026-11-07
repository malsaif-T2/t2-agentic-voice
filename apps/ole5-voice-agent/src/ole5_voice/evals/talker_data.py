"""The shapes runs K and S share (plan 006's registration): the language tags a reply is held to,
the judge's verdicts, what one turn of a `TextCall` did as a run keeps it (`HeardTurn`, read from
the `evals` facade's turn data, never from the talker's own events), and what a run spent on each
model (`ModelSpend`). Strict, as every model of the golden set's commands: a result read back is
checked as it is read, and an error never echoes the value it refused.

**The reply's language** is read from its own words, never from its clauses' tags: the library
tags a clause by the caller's words (an MSA turn in an `ar-SA` call stays `ar-SA`), and a tag
cannot tell Saudi from MSA. Each of the talker's clauses is in the script most of its words are
written in (`script_of`), and a reply is in a language's script when every clause that has one
is, and no word is in another script (`HeardTurn.written_in`); an Arabic reply's register is the
judge's word (`Register`). `in_language` holds a reply to both, as `HELD_TO` says.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Annotated, Final, Literal, get_args

from pydantic import Field, JsonValue
from t2_agentic_voice import T2VoiceError

from ole5_voice.evals.knowledge_set import SpokenLanguage
from ole5_voice.evals.models import Model
from ole5_voice.evals.runs import Plain

# The library's language tags (`Language.tag`), which a reply is spoken in.
Tag = Literal["ar-SA", "ar", "en"]
TAG_CHOICES: Final = get_args(Tag)
# The language a reply is held to, by the language of the caller's words: Saudi Arabic and Arabic
# with English product terms in the Saudi register, MSA in MSA, English in English ("What
# voice-first means here", item 8).
TAGS: Final[Mapping[SpokenLanguage, Tag]] = {
    "saudi": "ar-SA",
    "mixed": "ar-SA",
    "msa": "ar",
    "english": "en",
}
# The script a word or a clause is written in: Arabic's, Latin's (English's), or another (the
# spike's Llama replies put Chinese and Greek words into Arabic ones).
Script = Literal["ar", "en", "other"]
# The register of a reply's Arabic, as the judge reads it: Saudi, Modern Standard, or none (a
# reply with no Arabic).
Register = Literal["saudi", "msa", "none"]
REGISTERS: Final = get_args(Register)
# The script and the register a reply held to a tag is in: Arabic in the Saudi register for
# `ar-SA` (Saudi words, or Arabic with English product terms), in MSA for `ar`, English for `en`.
HELD_TO: Final[Mapping[Tag, tuple[Script, Register]]] = {
    "ar-SA": ("ar", "saudi"),
    "ar": ("ar", "msa"),
    "en": ("en", "none"),
}
# The judge's verdict on an answer (the registration's K, Q6): right, partly right, wrong,
# invented, or an honest "not in my knowledge".
Verdict = Literal["right", "partly_right", "wrong", "invented", "not_in_knowledge"]
VERDICTS: Final = get_args(Verdict)
# Why a variant or a scenario has no result to score, which is not an answer: a provider's
# failure, its wall-clock limit passed, or a judge that gave no valid verdict.
Failure = Literal["provider", "stuck", "judge"]
# A model's name, as a run keys its spend and its pacers by it.
ModelName = Annotated[Plain, Field(min_length=1, max_length=128)]
_Seconds = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class TalkerDataError(T2VoiceError):
    """A file runs K and S read that cannot be read as written: the points' text, a scenario, a
    run's own files, a judge's sheet. The message names the file and the fields, never a
    value."""

    code = "talker_data"


class Clause(Model):
    """One clause of a reply as the caller heard it (the facade's `HeardClause`)."""

    text: str
    language: Tag
    fate: Literal["played", "cut", "unplayed"]
    played_fraction: float = Field(ge=0, le=1, allow_inf_nan=False)
    phrase: bool = False  # a fixed phrase (a progress line, the guard's line), not the talker's


class ToolUse(Model):
    """One tool call of a reply (the facade's `TextToolCall`): the tool, the arguments the model
    wrote, what came of it, how long it ran in ms (None while it runs), and when it began, in
    seconds from the caller's request (None when not known)."""

    tool: str = Field(min_length=1)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    outcome: Literal["ok", "failed", "cancelled", "running"]
    ms: _Seconds | None = None
    began_s: _Seconds | None = None

    @property
    def span_s(self) -> tuple[float, float] | None:
        """When it began and ended, in seconds from the caller's request; None until it ends,
        or when its start is not known."""
        if self.began_s is None or self.ms is None:
            return None
        return self.began_s, self.began_s + self.ms / 1000


class CardShown(Model):
    """A card the reply showed: its title, its steps and its source."""

    title: str
    steps: tuple[str, ...] = ()
    source: str | None = None


class HeardTurn(Model):
    """What one of the caller's turns did, as a run keeps it: its fate, the clauses heard, the
    tool calls, the cards, the guard's blocks, the times to the first token and the first clause
    (seconds, on the call's clock, the tools' time in them; `own_first_clause_s` takes it out),
    the model requests and their tokens."""

    fate: str
    clauses: tuple[Clause, ...] = ()
    tools: tuple[ToolUse, ...] = ()
    cards: tuple[CardShown, ...] = ()
    blocked: int = Field(default=0, ge=0)
    first_token_s: _Seconds | None = None
    first_clause_s: _Seconds | None = None
    model_requests: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @property
    def spoken(self) -> tuple[Clause, ...]:
        """The talker's own clauses the caller heard, whole or cut: no fixed phrase, none
        unplayed."""
        return tuple(c for c in self.clauses if not c.phrase and c.fate != "unplayed")

    @property
    def said(self) -> str:
        """What the talker said that the caller heard, its clauses joined."""
        return " ".join(clause.text for clause in self.spoken)

    @property
    def words(self) -> int:
        """The words the talker said that the caller heard."""
        return len(self.said.split())

    def written_in(self, script: Script) -> bool:
        """Whether the talker's own clauses, heard or not, are written in `script`: each that
        has a script (`script_of`), at least one, and no word of any in another script."""
        own = [clause.text for clause in self.clauses if not clause.phrase]
        scripts = [found for found in map(script_of, own) if found is not None]
        other = any(_word_script(word) == "other" for text in own for word in text.split())
        return bool(scripts) and all(found == script for found in scripts) and not other

    @property
    def own_first_clause_s(self) -> float | None:
        """The model's own time to the first clause (Q15, run K's keep rule): the time to it
        less the time its tools ran before it, each from its start to its end, of those that
        ended before the first clause, time two ran at once counted once; so a search is not
        counted. None with no first clause, or a tool that ended before it whose start is not
        known."""
        first = self.first_clause_s
        if first is None:
            return None
        spans = []
        for use in self.tools:
            span = use.span_s
            if span is None and use.ms is not None and use.ms / 1000 <= first:
                return None  # it may have ended before the first clause, from an unknown start
            if span is not None and span[1] <= first:
                spans.append(span)
        ran, reached = 0.0, 0.0
        for began, ended in sorted(spans):
            ran += max(ended - max(began, reached), 0.0)
            reached = max(reached, ended)
        return max(first - ran, 0.0)

    def searched(self, tool: str) -> bool:
        """Whether the reply called the tool `tool`."""
        return any(use.tool == tool for use in self.tools)

    def heard_text(self) -> str:
        """The reply as the caller heard it, for a judge: each of the talker's clauses, a cut one
        marked with the share that played, an unplayed one marked as never heard."""
        marks = {"played": "", "unplayed": " [never heard]"}
        return " ".join(
            clause.text
            + marks.get(clause.fate, f" [cut, {clause.played_fraction:.0%} of it heard]")
            for clause in self.clauses
            if not clause.phrase
        )


def in_language(turn: HeardTurn, tag: Tag, register: Register | None) -> bool:
    """Whether `turn`'s reply is in the language `tag` holds it to (`HELD_TO`): written in its
    script, and, held to Arabic, in its register as the judge read it (`register`)."""
    script, wanted = HELD_TO[tag]
    return turn.written_in(script) and (script != "ar" or register == wanted)


def script_of(text: str) -> Script | None:
    """The script most of `text`'s words are written in, a word's the script most of its letters
    are; None when it holds no letter, or as many words in two scripts (a short Arabic clause
    around English product terms, an English one quoting the screen's Arabic labels)."""
    return _most(_word_script(word) for word in text.split())


def _word_script(word: str) -> Script | None:
    return _most(_letter_script(letter) for letter in word if letter.isalpha())


def _letter_script(letter: str) -> Script:
    name = unicodedata.name(letter, "")
    return "ar" if name.startswith("ARABIC") else "en" if name.startswith("LATIN") else "other"


def _most(scripts: Iterable[Script | None]) -> Script | None:
    ranked = Counter(script for script in scripts if script is not None).most_common(2)
    if not ranked or (len(ranked) == 2 and ranked[0][1] == ranked[1][1]):
        return None
    return ranked[0][0]


class ModelSpend(Model):
    """What a run sent to one model: its requests, those that were a retry of one turned away,
    those that failed after every attempt, those whose provider reported no usage (counted at
    their budget), the tokens read (the cached among them counted again) and written, and their
    cost at the run's prices."""

    model: ModelName
    requests: int = Field(default=0, ge=0)
    retried: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    unreported: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0, allow_inf_nan=False)
