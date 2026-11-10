"""The output guard's rule A (the design's 8.2): a clause that holds a claim phrase of an action
passes only if the call's record holds that action or a `reports_on` tool returned it, and every
ID-shaped token in the clause is then a value of that result, never a passage's. Rule C, the
talker's text after an action call, is state on the talker's turn (agent/turn.py), not a rule
of the clause. Pure, and matched on the guard's normalized text.

What `check_claims` does:

- **The phrases.** Each action's own (`claims`, its `Claims` in the clause's language) claim that
  action; the default ones (`any_action`: `default_claims`, with the `guard.claims` setting's
  added) claim any action. Both are matched as whole words of the clause and the phrase, each in
  the guard's form (domain/guard_ids.py's `guard_form`), and also after waw or feh (and, so)
  written onto the phrase's first word («وتم»). A clause with none passes, whatever it holds.
- **The evidence.** A phrase of an action passes only when `evidence` holds that action: the
  texts of its completed results, or of a `reports_on` tool's results about it. A default phrase
  passes when any action has evidence, and stands for each that has.
- **Its numbers.** Every ID-shaped token of a claiming clause is read as rule B reads one
  (domain/guard_ids.py: digits spaced, in groups, said digit by digit or in Arabic-Indic
  digits), against the claimed actions' texts alone: a number a passage or the caller's words
  hold, or another action's, is no evidence that this action made it.
- **The verdict** names the actions claimed and, when it does not pass, the ID-shaped tokens
  with no support. `claimed` empty with `passed` False is a default phrase with no action done
  or reported.

The defaults are past-tense phrases of an agent that did something for the caller, first
person mostly, so that a knowledge answer that tells how a thing is done rarely holds one; a
claim worded otherwise passes (the design's 8.4), which the record of a simulated call and a
team's own phrases are for. The Arabic ones are written in the guard's form with `\\u` escapes,
each comment giving the phrase's sound and meaning.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache

from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.guard_ids import check_ids, guard_form
from t2_agentic_voice.domain.text.words import holds_words

# The letters written onto a phrase's first word that leave it the same phrase: waw, feh (and).
_JOINED = ("\u0648", "\u0641")


@dataclass(frozen=True, slots=True)
class ActionEvidence:
    """What supports claims about one `action`: the texts of its completed results and of the
    results of the `reports_on` tools that report on it."""

    action: str
    texts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClaimVerdict:
    """What rule A made of a clause: the actions it `claimed`, whether it `passed`, and when
    not, the ID-shaped tokens it held with no support (`unsupported`), as normalized (the
    module's docstring)."""

    claimed: tuple[str, ...]
    passed: bool
    unsupported: tuple[str, ...] = ()


# The English defaults: what the agent says it did, or what it says was done for the caller.
_DONE = (
    *("created", "opened", "submitted", "sent", "registered", "logged", "raised", "booked"),
    *("escalated", "transferred", "handed", "filed", "placed"),
)
_ENGLISH = (
    *(f"{who} {done}" for who in ("i ve", "i have", "we ve", "we have") for done in _DONE),
    *(f"i {done}" for done in ("created", "submitted", "registered", "raised", "escalated")),
    *(f"has been {done}" for done in ("created", "submitted", "registered", "escalated")),
    *("has been booked", "has been logged", "has been raised", "has been filed"),
    *(f"successfully {done}" for done in ("created", "submitted", "sent", "registered")),
    "your request has been sent",
)
# The Arabic defaults, both Arabic presets', in the guard's form.
_ARABIC = (
    "\u062a\u0645 \u0627\u0646\u0634\u0627\u0621",  # tamma inshaa', it was created
    # tamma tasjeel talabak, your request was registered
    "\u062a\u0645 \u062a\u0633\u062c\u064a\u0644 \u0637\u0644\u0628\u0643",
    "\u062a\u0645 \u0631\u0641\u0639 \u0637\u0644\u0628\u0643",  # tamma raf' talabak, raised
    # tamma taqdeem talabak, your request was submitted
    "\u062a\u0645 \u062a\u0642\u062f\u064a\u0645 \u0637\u0644\u0628\u0643",
    # tamma irsaal talabak, your request was sent
    "\u062a\u0645 \u0627\u0631\u0633\u0627\u0644 \u0637\u0644\u0628\u0643",
    "\u062a\u0645 \u0641\u062a\u062d \u0637\u0644\u0628",  # tamma fath talab, a request was opened
    # tamma tahweel talabak, your request was transferred
    "\u062a\u0645 \u062a\u062d\u0648\u064a\u0644 \u0637\u0644\u0628\u0643",
    # tamma tas'eed talabak, your request was escalated
    "\u062a\u0645 \u062a\u0635\u0639\u064a\u062f \u0637\u0644\u0628\u0643",
    "\u062a\u0645 \u062d\u062c\u0632",  # tamma hajz, it was booked
    "\u0633\u062c\u0644\u062a \u0644\u0643",  # sajjalt lak, I registered for you
    # sajjalt talabak, I registered your request
    "\u0633\u062c\u0644\u062a \u0637\u0644\u0628\u0643",
    "\u0631\u0641\u0639\u062a \u0644\u0643",  # rafa't lak, I raised for you
    "\u0631\u0641\u0639\u062a \u0637\u0644\u0628\u0643",  # rafa't talabak, I raised your request
    "\u0641\u062a\u062d\u062a \u0644\u0643",  # fatah-t lak, I opened for you
    # arsalt talabak, I sent your request
    "\u0627\u0631\u0633\u0644\u062a \u0637\u0644\u0628\u0643",
    # qaddamt talabak, I submitted your request
    "\u0642\u062f\u0645\u062a \u0637\u0644\u0628\u0643",
    "\u0627\u0646\u0634\u0627\u062a \u0644\u0643",  # ansha't lak, I created for you
    "\u062d\u0648\u0644\u062a\u0643",  # hawwaltak, I transferred you
    # hawwalt talabak, I transferred your request
    "\u062d\u0648\u0644\u062a \u0637\u0644\u0628\u0643",
    # sa''adt talabak, I escalated your request
    "\u0635\u0639\u062f\u062a \u0637\u0644\u0628\u0643",
    # laqad ansha't, sajjalt, arsalt, qaddamt, fatah-t, rafa't, hawwalt: I have created,
    # registered, sent, submitted, opened, raised, transferred (MSA)
    "\u0644\u0642\u062f \u0627\u0646\u0634\u0627\u062a",
    "\u0644\u0642\u062f \u0633\u062c\u0644\u062a",
    "\u0644\u0642\u062f \u0627\u0631\u0633\u0644\u062a",
    "\u0644\u0642\u062f \u0642\u062f\u0645\u062a",
    "\u0644\u0642\u062f \u0641\u062a\u062d\u062a",
    "\u0644\u0642\u062f \u0631\u0641\u0639\u062a",
    "\u0644\u0642\u062f \u062d\u0648\u0644\u062a",
)
_DEFAULTS: Mapping[LanguageCode, tuple[str, ...]] = {"ar": _ARABIC, "en": _ENGLISH}


def default_claims(code: LanguageCode) -> tuple[str, ...]:
    """The short list of phrases that claim any action, in the language `code` (the module's
    docstring), each in the guard's form."""
    return _DEFAULTS[code]


@lru_cache(maxsize=4096)
def _phrase(text: str) -> str:
    return guard_form(text)


def _holds(clause: str, phrases: Sequence[str]) -> bool:
    """Whether `clause`, in the guard's form, holds one of `phrases` as whole words, or after
    waw or feh written onto its first word."""
    for written in phrases:
        phrase = _phrase(written)
        if phrase and any(holds_words(clause, start + phrase) for start in ("", *_JOINED)):
            return True
    return False


def check_claims(
    clause: str,
    *,
    claims: Mapping[str, Sequence[str]],
    any_action: Sequence[str],
    evidence: Sequence[ActionEvidence],
    settings: GuardSettings,
    year: int,
) -> ClaimVerdict:
    """Rule A on `clause`, as the module says: `claims` maps each action to its phrases in the
    clause's language and `any_action` holds the default ones."""
    said = guard_form(clause)
    named = tuple(action for action, phrases in claims.items() if _holds(said, phrases))
    general = _holds(said, any_action)
    if not named and not general:
        return ClaimVerdict(claimed=(), passed=True)
    texts: dict[str, tuple[str, ...]] = {}
    for each in evidence:
        texts[each.action] = (*texts.get(each.action, ()), *each.texts)
    claimed = named or tuple(texts)
    held = all(action in texts for action in claimed) and bool(claimed)
    support = [text for action in claimed for text in texts.get(action, ())]
    numbers = check_ids(clause, evidence=support, settings=settings, year=year)
    return ClaimVerdict(
        claimed=claimed, passed=held and numbers.passed, unsupported=numbers.unsupported
    )
