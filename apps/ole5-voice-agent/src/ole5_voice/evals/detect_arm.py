"""Run H's Whisper arm of `stt.live_language = "detected"` (D-038's amendment), as `poe eval
--language-from <a detected pass> --language-base <the call language's baseline>` on dev
(language_arms.py): a live call sends each turn in the call's current language, and a turn of
`stt.detect_from_s` seconds of voiced speech or more also naming no language, at the same time;
when that request heard the agent's other language in a question or request, never a short
reply, the turn's words are its transcript and the call moves.

So the arm sends only the variants whose first turn `detects` in the pass (the bridge's own
voiced-speech gate, as the file-fed pipeline applied it), each whole and naming no language,
with no prompt, as the live request goes. Its answer is then read with the library's rule
(`evals.switch_to`) against the baseline's answer, the request in the call's language: when the
rule moves the call, the variant's answer is the detecting request's, its language the code moved
to; otherwise, and when the detecting request failed, the baseline's stands. Every other variant's
answer is the baseline's, unsent. Each move is logged by the variant's identifiers, its kind and
the code, never its words; and each detecting request's answer, moved or not, by the variant's
identifiers, its time (its requests' latency, retries included) and whether it failed, so the
wait a live turn adds, the slower of its two requests, is read against the baseline's own time
for the same audio.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from t2_agentic_voice import evals, get_logger

from ole5_voice.evals.languages_card import CallLanguage, LanguageResult, call_code
from ole5_voice.evals.languages_setup import CODES
from ole5_voice.evals.models import Item, Variant
from ole5_voice.evals.run_parts import Plan, Todo
from ole5_voice.evals.runs import Answer

log = get_logger(__name__)


@dataclass
class Detecting:
    """The arm over one plan in a call of `call`: the baseline's answer of every variant
    (`base`), the call's code for each one sent (`named`) with its item, and the moves made."""

    call: CallLanguage
    base: Mapping[Variant, Answer]
    named: dict[Variant, tuple[str, Item]] = field(default_factory=dict)
    moved: dict[str, int] = field(default_factory=dict)

    def merge(self, variant: Variant, answer: Answer) -> Answer:
        """The variant's answer once its detecting request came: the detecting request's when
        the library's rule moves the call, else the baseline's (the module's docstring)."""
        base, (code, item) = self.base[variant], self.named[variant]
        log.info(
            "detect_answered",
            item=item.id,
            variant=variant.id,
            kind=item.kind,
            latency_ms=round(sum(r.latency_ms for r in answer.requests), 1),
            base_ms=round(sum(r.latency_ms for r in base.requests), 1),
            attempts=len(answer.requests),
            failure=answer.failure,
        )
        if answer.failure is not None or answer.text is None:
            return base
        moved = evals.switch_to(
            code,
            answer.language,
            codes=CODES,
            named_text=base.text,
            detected_text=answer.text,
        )
        if moved is None:
            return base
        self.moved[item.kind] = self.moved.get(item.kind, 0) + 1
        log.info("language_moved", item=item.id, variant=variant.id, kind=item.kind, to=moved)
        return answer.model_copy(update={"language": moved})


def detected_plan(
    plan: Plan,
    heard: Mapping[tuple[str, str], LanguageResult],
    call: CallLanguage,
    base: Mapping[Variant, Answer],
) -> tuple[Plan, Detecting]:
    """`plan` with each variant whose first turn detects sent naming no language, and the arm
    that reads them; the rest are answered from `base`."""
    arm, todo = Detecting(call=call, base=base), []
    for each in plan.todo:
        found = heard[(each.item.id, each.variant.id)]
        if found.turns and found.turns[0].detects:
            arm.named[each.variant] = (call_code(call, each.item.language), each.item)
            todo.append(_naming_none(each))
        else:
            todo.append(each)
    return replace(plan, todo=tuple(todo)), arm


def _naming_none(todo: Todo) -> Todo:
    return replace(todo, request=todo.request.model_copy(update={"language": None}))
