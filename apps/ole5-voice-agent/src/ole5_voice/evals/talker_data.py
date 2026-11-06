"""The shapes runs K and S share (plan 006's registration): the language tags a reply is held to,
the judge's verdicts, what one turn of a `TextCall` did as a run keeps it (`HeardTurn`, read from
the `evals` facade's turn data, never from the talker's own events), and what a run spent on each
model (`ModelSpend`). Strict, as every model of the golden set's commands: a result read back is
checked as it is read, and an error never echoes the value it refused.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
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
    wrote, what came of it, and how long it ran in ms (None while it runs)."""

    tool: str = Field(min_length=1)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    outcome: Literal["ok", "failed", "cancelled", "running"]
    ms: _Seconds | None = None


class CardShown(Model):
    """A card the reply showed: its title, its steps and its source."""

    title: str
    steps: tuple[str, ...] = ()
    source: str | None = None


class HeardTurn(Model):
    """What one of the caller's turns did, as a run keeps it: its fate, the clauses heard, the
    tool calls, the cards, the guard's blocks, the times to the first token and the first clause
    (seconds, on the call's clock), the model requests and their tokens."""

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

    @property
    def language(self) -> Tag | None:
        """The language most of the talker's clauses were spoken in, None when it said none."""
        found = Counter(clause.language for clause in self.clauses if not clause.phrase)
        return found.most_common(1)[0][0] if found else None

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
