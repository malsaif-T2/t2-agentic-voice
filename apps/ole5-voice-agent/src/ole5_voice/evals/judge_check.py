"""`poe judge-check`: the owner's check of run K's judge (plan 006, Q6), on a dev run.

`draw RUN` draws `SHEET_SIZE` judged answers of the run at random (seeded by `--seed`, and
stratified by verdict: one of each verdict the run gave, then the rest in proportion to each
verdict's share, by the largest remainders) into a sheet the owner fills, `judge-sheet.toml` in
the run's folder unless `--sheet` names another: for each answer, the caller's words, what the
talker said and showed, the item's expected points' text and key facts, the judge's verdict and
reason, and a blank, `owner`, for the owner's verdict. The points' text comes from
`--points-text`, and the knowledge set from this worktree, refused unless their digest is the
run's, so the sheet shows what the judge read. `read RUN` reads the filled sheet back, each blank
filled with a verdict, and writes `judge-check.json` in the run's folder: more than
`MOST_DISAGREEMENTS` disagreements mark the run's verdicts for the owner to judge, which
`eval-talker-compare` and `eval-talker-keep` then refuse. A held-out run's answers are never
drawn. The sheet holds a dev run's texts, in the run's folder outside the worktree, which git
ignores; nothing is logged but counts.
"""

from __future__ import annotations

import argparse
import random
import sys
import tomllib
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import Field, ValidationError
from t2_agentic_voice import T2VoiceError, configure_logging, get_logger

from ole5_voice import LOGGERS
from ole5_voice.evals.files import first_problem, read_model, read_text
from ole5_voice.evals.kb_points import load_knowledge
from ole5_voice.evals.models import Model, Name
from ole5_voice.evals.run_parts import DATA
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.talker_data import VERDICTS, HeardTurn, TalkerDataError, Verdict
from ole5_voice.evals.talker_score import TalkerScorecard, VariantRecord
from ole5_voice.evals.worktree import Git, inspect, run_git

SHEET_SIZE: Final = 24
MOST_DISAGREEMENTS: Final = 3
SHEET_FILE: Final = "judge-sheet.toml"
CHECK_FILE: Final = "judge-check.json"
_DESCRIPTION = "Draw judged answers of a dev run of K for the owner, or read the filled sheet."
_NAMED = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}
log = get_logger(__name__)


class SheetAnswer(Model):
    """One drawn answer on the owner's sheet."""

    item: Name
    variant: Name
    caller_said: str
    answer: str
    card: str
    points: tuple[str, ...]
    key_facts: tuple[str, ...]
    judge: Verdict
    judge_reason: str
    owner: str  # the owner's verdict, one of `VERDICTS`, blank until filled


class Sheet(Model):
    """The owner's sheet of one run."""

    run: Name
    seed: int
    answers: tuple[SheetAnswer, ...] = Field(min_length=1)


class JudgeCheck(Model):
    """What the owner's check found: the answers drawn, those the owner judged otherwise, and
    whether the run's verdicts are marked for the owner to judge."""

    run: Name
    seed: int
    drawn: int = Field(ge=1)
    disagreements: int = Field(ge=0)
    owner_judges: bool


def load_card(path: Path) -> TalkerScorecard:
    """A run's scorecard, from its folder or its file."""
    file = path / SCORECARD_FILE if path.is_dir() else path
    return read_model(file, TalkerScorecard, lambda p: TalkerDataError(f"{file.name}: {p}"))


def marked(folder: Path) -> bool:
    """Whether the owner's check marked the run in `folder` for the owner to judge."""
    path = folder / CHECK_FILE
    if not path.exists():
        return False
    check = read_model(path, JudgeCheck, lambda p: TalkerDataError(f"{CHECK_FILE}: {p}"))
    return check.owner_judges


def draw(
    records: Sequence[VariantRecord], seed: int, size: int = SHEET_SIZE
) -> list[VariantRecord]:
    """`size` judged records drawn at random, seeded, stratified by verdict (the module's
    docstring); every judged record when there are no more."""
    by_verdict: dict[str, list[VariantRecord]] = defaultdict(list)
    for record in records:
        if record.judged is not None and record.judged.verdict is not None:
            by_verdict[record.judged.verdict].append(record)
    total = sum(len(group) for group in by_verdict.values())
    if total <= size:
        return [r for verdict in VERDICTS for r in by_verdict.get(verdict, [])]
    rest, others = size - len(by_verdict), total - len(by_verdict)
    exact = {v: (len(group) - 1) * rest / others for v, group in by_verdict.items()}
    shares = {verdict: 1 + int(share) for verdict, share in exact.items()}
    left = size - sum(shares.values())
    by_remainder = sorted(exact, key=lambda v: (int(exact[v]) - exact[v], VERDICTS.index(v)))
    for verdict in by_remainder[:left]:
        shares[verdict] += 1
    rng = random.Random(seed)  # noqa: S311 - a seeded draw, not a secret
    return [
        record
        for verdict in VERDICTS
        if verdict in by_verdict
        for record in rng.sample(by_verdict[verdict], shares[verdict])
    ]


def _string(text: str) -> str:
    """`text` as a TOML basic string, every control character escaped."""
    escaped = "".join(
        _NAMED.get(c) or (f"\\u{ord(c):04x}" if ord(c) < 0x20 or ord(c) == 0x7F else c)
        for c in text
    )
    return f'"{escaped}"'


def _strings(texts: Sequence[str]) -> str:
    return "[" + ", ".join(_string(text) for text in texts) + "]"


def sheet_text(run: str, seed: int, answers: Sequence[SheetAnswer]) -> str:
    """The sheet's TOML, which `tomllib` reads back as the same `Sheet`."""
    lines = [
        "# The owner's check of the judge (plan 006, Q6): for each answer, read what the caller",
        "# said, the answer and its card beside the points and the key facts, and write your own",
        f"# verdict in `owner`: {', '.join(VERDICTS)}. Then run `poe judge-check read`.",
        f"run = {_string(run)}",
        f"seed = {seed}",
    ]
    for answer in answers:
        lines += ["", "[[answers]]"]
        lines += [f"item = {_string(answer.item)}", f"variant = {_string(answer.variant)}"]
        lines += [f"caller_said = {_string(answer.caller_said)}"]
        lines += [f"answer = {_string(answer.answer)}", f"card = {_string(answer.card)}"]
        lines += [f"points = {_strings(answer.points)}"]
        lines += [f"key_facts = {_strings(answer.key_facts)}"]
        lines += [f"judge = {_string(answer.judge)}"]
        lines += [f"judge_reason = {_string(answer.judge_reason)}", 'owner = ""']
    return "\n".join(lines) + "\n"


def read_sheet(path: Path) -> Sheet:
    """The filled sheet at `path`; TalkerDataError naming the fields when it cannot be read."""
    text = read_text(path)
    if text is None:
        raise TalkerDataError(f"{path.name} cannot be read as UTF-8 text")
    try:
        return Sheet.model_validate(tomllib.loads(text))
    except tomllib.TOMLDecodeError as error:
        problem = f"not TOML ({error})"
    except ValidationError as error:
        problem = first_problem(error)
    raise TalkerDataError(f"{path.name}: {problem}")


def card_text(turn: HeardTurn) -> str:
    """The cards a reply showed, as one line: each title, then its steps."""
    return " | ".join(
        f"{card.title}: " + " / ".join(card.steps) if card.steps else card.title
        for card in turn.cards
    )


def _answers(
    card: TalkerScorecard, drawn: Sequence[VariantRecord], args: argparse.Namespace, git: Git
) -> list[SheetAnswer]:
    checkout = inspect(Path.cwd() if args.folder is None else args.folder, git)
    data = load_knowledge(checkout.top / DATA, args.points_text)
    if data.digest != card.run.data_digest:
        raise TalkerDataError(
            "the knowledge set or the points' text is not the run's (their digest differs)"
        )
    answers = []
    for record in drawn:
        item = data.items[record.item]
        turn, verdict, reason = judged_of(record)
        answers.append(
            SheetAnswer(
                item=record.item,
                variant=record.variant,
                caller_said=item.variants[int(record.variant.removeprefix("v")) - 1].text,
                answer=turn.said,
                card=card_text(turn),
                points=data.evidence(item).points,
                key_facts=item.key_facts,
                judge=verdict,
                judge_reason=reason,
                owner="",
            )
        )
    return answers


def judged_of(record: VariantRecord) -> tuple[HeardTurn, Verdict, str]:
    """A judged record's reply, verdict and reason; TalkerDataError for one with none."""
    turn, judged = record.turn, record.judged
    if turn is None or judged is None or judged.verdict is None:
        raise TalkerDataError(f"{record.item}/{record.variant} has no verdict to check")
    return turn, judged.verdict, judged.reason


def _draw(args: argparse.Namespace, git: Git) -> int:
    card = load_card(args.run)
    if card.run.split != "dev":
        raise TalkerDataError("a held-out run's answers are read only as counts: draw from dev")
    drawn = draw(card.variants, args.seed)
    if not drawn:
        raise TalkerDataError("the run holds no judged answer to draw")
    answers = _answers(card, drawn, args, git)
    sheet = args.sheet or args.run / SHEET_FILE
    sheet.write_bytes(sheet_text(card.run.name, args.seed, answers).encode("utf-8"))
    log.info("sheet_drawn", run=card.run.name, answers=len(answers), sheet=str(sheet))
    return 0


def _read(args: argparse.Namespace) -> int:
    card = load_card(args.run)
    sheet = read_sheet(args.sheet or args.run / SHEET_FILE)
    if sheet.run != card.run.name:
        raise TalkerDataError(f"the sheet is run {sheet.run}'s, not {card.run.name}'s")
    blank = [n for n, answer in enumerate(sheet.answers, start=1) if answer.owner not in VERDICTS]
    if blank:
        raise TalkerDataError(
            f"{len(blank)} answer(s) have no owner's verdict, the first number {blank[0]}: "
            f"write one of {', '.join(VERDICTS)}"
        )
    disagreements = sum(answer.owner != answer.judge for answer in sheet.answers)
    check = JudgeCheck(
        run=sheet.run,
        seed=sheet.seed,
        drawn=len(sheet.answers),
        disagreements=disagreements,
        owner_judges=disagreements > MOST_DISAGREEMENTS,
    )
    (args.run / CHECK_FILE).write_bytes((check.model_dump_json(indent=2) + "\n").encode("utf-8"))
    log.info("judge_checked", run=check.run, drawn=check.drawn, disagreements=disagreements)
    if check.owner_judges:
        log.warning(
            "owner_judges",
            run=check.run,
            fix="the owner judges every answer of this run; compare and keep refuse it",
        )
    return 0


def main(argv: Sequence[str] | None = None, *, git: Git = run_git) -> int:
    """`uv run poe judge-check draw|read RUN`: draw the owner's sheet of a dev run of K, or
    read it back. 0 when done, 1 when refused."""
    parser = argparse.ArgumentParser(prog="poe judge-check", description=_DESCRIPTION)
    parser.add_argument("action", choices=("draw", "read"), help="draw the sheet, or read it")
    parser.add_argument("run", type=Path, help="the dev run's --out folder")
    parser.add_argument("--sheet", type=Path, help=f"the sheet (the run's {SHEET_FILE})")
    parser.add_argument("--seed", type=int, default=6, help="the draw's seed (6)")
    parser.add_argument("--points-text", type=Path, help="the snapshot of the points the run read")
    parser.add_argument("--folder", type=Path, help="a folder of the worktree (the current one)")
    args = parser.parse_args(argv)
    if args.action == "draw" and args.points_text is None:
        parser.error("draw needs --points-text, the snapshot the run judged with")
    configure_logging(loggers=LOGGERS)
    try:
        return _draw(args, git) if args.action == "draw" else _read(args)
    except T2VoiceError as error:
        log.error("judge_check_refused", code=error.code, message=error.message)
        return 1


if __name__ == "__main__":
    sys.exit(main())
