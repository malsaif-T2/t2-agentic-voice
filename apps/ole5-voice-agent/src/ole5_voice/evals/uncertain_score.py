"""The scorer of `poe uncertain` (plan 006's registration, U, the uncertain middle): which stored
overlaps it reads, each judged under the rule (U0) and under the model arm, the numbers of each,
and the keep rule; the scorecard and the history line are uncertain_card.py's.

**The overlaps** are those of a stored dev overlap run (plan 005's O1 or O2, `poe overlap`'s
scorecard), each judged again under the session's rule at this commit (uncertain_rejudge.py),
whose verdict is a short output or too few words (`UNCERTAIN_REASONS`), the deciding request
answered and its words not empty; each with the reply it was played over (its clauses joined,
as the replay spoke them as one phrase) and those words. What each should do is its kind's
action, a repeat request counted as a stop, since with a talker a stop hands the words to the
talker, which says the reply again. **U0** is that verdict, the rule (D-061) with its one
revision (D-068), the session's default, which O1 and O2 ran before; no model request gives it.
**The arm's**
verdict is the model's one-word answer; an answer that is neither word is `unclear` and takes
the rule's verdict, as a call would; a request that failed is an infrastructure failure, counted
apart and left out of both arms' numbers.

**The keep rule** (the registration's, `keep_rule`): the arm raises the right verdicts by the
sign test on items (each item's net over its overlaps, the arm's right less the rule's; p below
`ALPHA`, more better than worse), stops no more listening sounds than U0, and answers within
`ANSWER_BOUND_MS` at the median (from the request sent to its stream's end, on the wall clock).
Quantiles are type 7 (`scorecard.quantile`), as plan 002 took them.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Annotated, Final, Literal

from pydantic import Field
from t2_agentic_voice import evals

from ole5_voice.evals.models import Device, Kind, Language, Model, Name
from ole5_voice.evals.overlap_card import OverlapScorecard
from ole5_voice.evals.scorecard import quantile

UNCERTAIN_REASONS: Final = ("short_output", "too_few_words")  # the rule's steps 6 and 7
ALPHA: Final = 0.05
ANSWER_BOUND_MS: Final = 300.0
LISTENING_KIND: Final = "listening_sound"
# What an overlap should do, and what a verdict did: stop the agent, or let it go on.
Binary = Literal["stop", "go_on"]
# What the model answered: one of the two words, or neither.
Answered = Literal["stop", "go_on", "unclear"]
_Ms = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class UncertainOverlap(Model):
    """One overlap the arms judge: its strata, what it should do, the rule's stored verdict and
    the step that gave it, the reply it was played over and the words heard over it."""

    item: Name
    variant: Name
    kind: Kind
    language: Language
    device: Device
    expected: Binary
    rule: Binary
    reason: Name
    reply: str = Field(min_length=1)
    words: str = Field(min_length=1)


def uncertain_overlaps(card: OverlapScorecard) -> tuple[UncertainOverlap, ...]:
    """The overlaps of `card`, its verdicts this commit's rule's, the arms judge (the module's
    docstring), in its order."""
    found = []
    for result in card.variants:
        verdict = result.verdict
        if result.judged.failed or not verdict.opened or verdict.reason not in UNCERTAIN_REASONS:
            continue
        deciding = (verdict.decided_turn, verdict.decided_by)
        words = next((r.text for r in verdict.requests if (r.turn_id, r.part) == deciding), None)
        if words is None or not words.strip():
            continue
        found.append(
            UncertainOverlap(
                item=result.item,
                variant=result.variant,
                kind=result.kind,
                language=result.language,
                device=result.device,
                expected="go_on" if result.expected == "go_on" else "stop",
                rule="go_on" if verdict.action in (None, "go_on") else "stop",
                reason=verdict.reason,
                reply=" ".join(result.reply),
                words=words.strip(),
            )
        )
    return tuple(found)


class ArmAnswer(Model):
    """What the model answered for one overlap: its word (None for a failure), the failure
    (a `ProviderError` kind, or `stuck` at the item's time limit), the attempts, the times from
    the request sent to its first text and to its stream's end, and the tokens it used."""

    answer: Answered | None = None
    failure: str | None = None
    attempts: int = Field(default=1, ge=1)
    first_text_ms: _Ms | None = None
    answer_ms: _Ms | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)


class UncertainResult(Model):
    """One overlap judged: the rule's verdict and whether it is right, and the arm's (the rule's
    for an unclear answer; None for a failure)."""

    overlap: UncertainOverlap
    answer: ArmAnswer
    rule_right: bool
    arm: Binary | None
    arm_right: bool | None


def judged(overlap: UncertainOverlap, answer: ArmAnswer) -> UncertainResult:
    """`overlap` judged with the model's `answer`."""
    arm: Binary | None = None
    if answer.failure is None:
        given = answer.answer
        arm = "stop" if given == "stop" else "go_on" if given == "go_on" else overlap.rule
    return UncertainResult(
        overlap=overlap,
        answer=answer,
        rule_right=overlap.rule == overlap.expected,
        arm=arm,
        arm_right=None if arm is None else arm == overlap.expected,
    )


class ArmMetrics(Model):
    """One arm's numbers over the overlaps not failed: right verdicts, the stops it should make
    and made, the go-ons it should leave and stopped, the listening sounds it stopped, its
    unclear answers, and (the model's) its time to an answer."""

    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    failed: int = Field(ge=0)
    right: int = Field(ge=0)
    should_stop: int = Field(ge=0)
    stopped: int = Field(ge=0)
    should_go_on: int = Field(ge=0)
    false_stops: int = Field(ge=0)
    listening: int = Field(ge=0)
    listening_stops: int = Field(ge=0)
    unclear: int = Field(default=0, ge=0)
    answer_median_ms: _Ms | None = None
    answer_p90_ms: _Ms | None = None


def metrics(results: Sequence[UncertainResult], *, arm: bool) -> ArmMetrics:
    """The numbers of `results` under the model's arm (`arm`) or the rule's."""
    scored = [r for r in results if r.arm is not None]

    def verdict(result: UncertainResult) -> Binary:
        return result.arm if arm and result.arm is not None else result.overlap.rule

    stops = [r for r in scored if r.overlap.expected == "stop"]
    go_ons = [r for r in scored if r.overlap.expected == "go_on"]
    listening = [r for r in scored if r.overlap.kind == LISTENING_KIND]
    times = sorted(t for r in scored if (t := r.answer.answer_ms) is not None) if arm else []
    return ArmMetrics(
        items=len({r.overlap.item for r in scored}),
        variants=len(results),
        failed=len(results) - len(scored),
        right=sum(verdict(r) == r.overlap.expected for r in scored),
        should_stop=len(stops),
        stopped=sum(verdict(r) == "stop" for r in stops),
        should_go_on=len(go_ons),
        false_stops=sum(verdict(r) == "stop" for r in go_ons),
        listening=len(listening),
        listening_stops=sum(verdict(r) == "stop" for r in listening),
        unclear=sum(r.answer.answer == "unclear" for r in scored) if arm else 0,
        answer_median_ms=quantile(times, 0.5),
        answer_p90_ms=quantile(times, 0.9),
    )


class KeepRule(Model):
    """The registration's keep rule on one run: the items better and worse under the arm, the
    sign test's p, and whether each of its three parts holds."""

    better: int = Field(ge=0)
    worse: int = Field(ge=0)
    p: float = Field(ge=0, le=1)
    raises_right: bool
    listening_no_more: bool
    answers_in_time: bool
    kept: bool


def keep_rule(results: Sequence[UncertainResult]) -> KeepRule:
    """The keep rule (the module's docstring) on `results`."""
    nets: dict[str, int] = defaultdict(int)
    for result in results:
        if result.arm_right is not None:
            nets[result.overlap.item] += int(result.arm_right) - int(result.rule_right)
    better = sum(net > 0 for net in nets.values())
    worse = sum(net < 0 for net in nets.values())
    p = evals.sign_test(better, worse)
    arm, rule = metrics(results, arm=True), metrics(results, arm=False)
    raises = better > worse and p < ALPHA
    quiet = arm.listening_stops <= rule.listening_stops
    median = arm.answer_median_ms
    fast = median is not None and median <= ANSWER_BOUND_MS
    return KeepRule(
        better=better,
        worse=worse,
        p=p,
        raises_right=raises,
        listening_no_more=quiet,
        answers_in_time=fast,
        kept=raises and quiet and fast,
    )
