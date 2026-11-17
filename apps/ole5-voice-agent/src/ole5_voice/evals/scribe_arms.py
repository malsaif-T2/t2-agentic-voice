"""Run H's Scribe arms (D-115), each a pass of `poe eval-languages --scribe-arm ARM`
(scribe_arm_run.py): the shape of each arm's requests (`asks`), one variant's answers
(`ArmResult`, a line of the pass's `ARM_TURNS_FILE`), and the library's rule read over them for
a call held in each of the agent's languages (`ArmTurn`, `turn_of`).

Each checked variant of the split is one turn, sent whole, as `poe eval` and run H's H2 arms send
it (the golden set's reference is a variant's), and read twice: as a turn of a call held in
Arabic and as one of a call held in English (`CALL_CODES`). The arms:

- **`hinted`**, (a): the call's language as the hint (`language_code`) and the agent's other
  language beside it (`secondary_language_codes`, the clip's `other_languages`), with the call
  language's prompt (its keyterms), as `stt.live_language = "hinted"` sends every request;
- **`secondary`**, (b): no hint, the agent's two languages as secondary ones, with the call
  language's prompt. ElevenLabs' guide names secondary languages "alongside `language_code`"
  and says nothing of them alone, so a request it refuses is counted as a failure;
- **`none`**, (c): no hint and no secondary language, with the call language's prompt;
- **`detected`**, the reference: `stt.live_language = "detected"`'s requests, the call's
  language with its prompt, and, for a variant whose first turn `detects` (its voiced speech
  `stt.detect_from_s` or more, in an offline `--classifier detected` pass, the gate, as run H's
  Whisper arm reads it, detect_arm.py), one naming none with no prompt (`DETECTING`), read with
  `evals.switch_to`. Every other variant sends the first alone and never moves the call, as live.

The first three are read with `evals.hinted_switch` (D-115's rule) at a threshold: the pass's
`stt.switch_min_probability`, or each of the scorecard's table. `detected`'s rule has none; at a
threshold of the table its move also needs the detecting answer's probability at that or above.
A turn's transcript is its one answer's, or under `detected` the detecting request's when the
call moves and the call language's otherwise, as the live bridge takes it; its time is its
request's, or the slower of `detected`'s two when the gate sent both, which a live turn sends at
once. A request the arm's two calls share goes once (`distinct_asks`); a pass sends each alone,
in turn.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal, get_args

from pydantic import Field
from t2_agentic_voice import evals

from ole5_voice.evals.models import Device, Kind, Language, Model, Name

ArmName = Literal["hinted", "secondary", "none", "detected"]
ARM_NAMES: Final[tuple[ArmName, ...]] = get_args(ArmName)
CallCode = Literal["ar", "en"]
CALL_CODES: Final[tuple[CallCode, ...]] = get_args(CallCode)
ARM_TURNS_FILE: Final = "arm_turns.jsonl"  # every variant's answers, one line each
_Seconds = Field(ge=0, allow_inf_nan=False)


class Ask(Model):
    """One request's shape: the language it names (None: none), the other languages its clip
    gives beside it, and the language whose prompt it carries (None: none)."""

    named: CallCode | None
    others: tuple[CallCode, ...] = ()
    prompt: CallCode | None = None


def _other(call: CallCode) -> CallCode:
    return "en" if call == "ar" else "ar"


DETECTING: Final = Ask(named=None)  # `detected`'s second request: no language, no prompt


def asks(arm: ArmName, call: CallCode, *, detects: bool = True) -> tuple[Ask, ...]:
    """The requests a turn of a call held in `call` sends under `arm` (the module's docstring),
    the call language's own first; under `detected`, `DETECTING` only when the turn `detects`."""
    if arm == "hinted":
        return (Ask(named=call, others=(_other(call),), prompt=call),)
    if arm == "secondary":
        return (Ask(named=None, others=CALL_CODES, prompt=call),)
    if arm == "none":
        return (Ask(named=None, prompt=call),)
    named = Ask(named=call, prompt=call)
    return (named, DETECTING) if detects else (named,)


def distinct_asks(arm: ArmName, *, detects: bool = True) -> tuple[Ask, ...]:
    """Every request a variant sends under `arm`, each once, in order (`asks`)."""
    found = (ask for call in CALL_CODES for ask in asks(arm, call, detects=detects))
    return tuple(dict.fromkeys(found))


class ArmAnswer(Model):
    """One request's answer: its words, the transcript's language and the one the provider
    heard with its probability (None where it gave none), its time from send to answer and its
    billed seconds; or its failure's kind, with no words."""

    ask: Ask
    text: str | None = None
    language: str | None = None
    heard: str | None = None
    probability: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    seconds: float = _Seconds
    billed_seconds: float = _Seconds
    failure: str | None = None


class ArmResult(Model):
    """One variant of an arm's pass: its strata, its reference, each request's answer and,
    under `detected`, whether its first turn `detects` in the gate's pass, so `DETECTING` was
    sent (None under the other arms, which have no gate)."""

    item: Name
    variant: Name
    kind: Kind
    language: Language
    device: Device
    reference: str
    answers: tuple[ArmAnswer, ...]
    detects: bool | None = None

    def answer(self, ask: Ask) -> ArmAnswer:
        """The answer of the request shaped `ask`; KeyError when none was sent."""
        for each in self.answers:
            if each.ask == ask:
                return each
        raise KeyError("no answer of that request")


@dataclass(frozen=True)
class ArmTurn:
    """One variant read as a turn of a call held in `call`: the code the rule moved the call to
    (None: no move), the transcript the turn keeps (None: its request failed), the seconds to
    it, and the answer the rule read the language from (`detected`'s detecting one; its named
    one when the gate sent none)."""

    result: ArmResult
    call: CallCode
    moved: str | None
    text: str | None
    seconds: float
    read: ArmAnswer


def _hinted_move(answer: ArmAnswer, call: CallCode, threshold: float) -> str | None:
    if answer.text is None:
        return None
    rule = evals.HintRule(min_probability=threshold, codes=CALL_CODES)
    return evals.hinted_switch(call, answer.heard, answer.probability, text=answer.text, rule=rule)


def _detected_move(
    named: ArmAnswer, detecting: ArmAnswer, call: CallCode, threshold: float | None
) -> str | None:
    if detecting.text is None:
        return None
    if threshold is not None and (detecting.probability or 0.0) < threshold:
        return None
    return evals.switch_to(
        call,
        detecting.heard or detecting.language,
        codes=CALL_CODES,
        named_text=named.text,
        detected_text=detecting.text,
    )


def turn_of(arm: ArmName, result: ArmResult, call: CallCode, *, threshold: float | None) -> ArmTurn:
    """`result` read as a turn of a call held in `call` under `arm`, at `threshold` (the
    module's docstring): None reads `detected` by its own rule, and is refused for the others,
    whose rule takes one (ValueError)."""
    if arm != "detected" and threshold is None:
        raise ValueError("a hinted arm's rule moves the call at a threshold")
    shaped = [result.answer(ask) for ask in asks(arm, call, detects=result.detects is not False)]
    seconds = max(answer.seconds for answer in shaped)
    if arm != "detected" and threshold is not None:
        (answer,) = shaped
        moved = _hinted_move(answer, call, threshold)
        return ArmTurn(result, call, moved, answer.text, seconds, answer)
    if len(shaped) == 1:  # the gate sent no detecting request: the call stays, as live
        (named,) = shaped
        return ArmTurn(result, call, None, named.text, seconds, named)
    named, detecting = shaped
    moved = _detected_move(named, detecting, call, threshold)
    text = detecting.text if moved is not None else named.text
    return ArmTurn(result, call, moved, text, seconds, detecting)


def turns_of(
    arm: ArmName, results: Sequence[ArmResult], *, threshold: float | None
) -> tuple[ArmTurn, ...]:
    """Every result read as a turn of each call language (`turn_of`)."""
    return tuple(turn_of(arm, r, call, threshold=threshold) for r in results for call in CALL_CODES)
