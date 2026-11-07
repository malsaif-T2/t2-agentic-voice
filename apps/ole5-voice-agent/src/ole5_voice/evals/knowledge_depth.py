"""`poe knowledge-depth`: run K0, the passages' depth (Q20; plan 006's registration, K0), into a
folder, `--out`. Each answerable dev variant's raw words are searched once in the real knowledge
base, as run K's reference search (`talker_measure.CALLER`, in the language its words are held
to, `talker_data.TAGS`), with a limit of `DEPTH`, and no chat model, so no Groq request is sent;
then come the numbers at each k from 1 to `DEPTH` and the kept k (knowledge_depth_card.py).
Held-out is never read by K0: `--split held-out` is refused, and only dev items are searched.

Before anything is sent, a run refuses the main checkout and a dirty tree, an `--out` that exists
or that git would track, a knowledge set that cannot be read or holds no answerable dev item,
and a `--knowledge` factory that gives no knowledge base (built as run K builds it, given
`--env-file`: factories.py). The first variant's search is the smoke test: one that fails,
passes `--search-timeout-s`, finds nothing, or finds no passage the knowledge set's points hold
(the passage IDs' form would score every search a miss, kb_points.py) stops the run before any
other search. Each variant's record is written as it finishes (`results.jsonl`), with a progress
line of identifiers and counts, never a text; a later search that fails or passes its limit is
counted apart. Each passage's characters are counted as the library's knowledge tool hands it
to the talker (knowledge_depth_card.py's `talker_chars`), so K0 counts what the talker would
read. Whatever ends the run,
its scorecard is written and its history line (`DepthLine`) appended to the worktree's
`history.jsonl` and copied beside the scorecard.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, get_args

from pydantic import TypeAdapter, ValidationError
from t2_agentic_voice import T2VoiceError, configure_logging, get_logger
from t2_agentic_voice.ports import KnowledgeBase, Passage

from ole5_voice import LOGGERS
from ole5_voice.evals.factories import Closing, env_file_of, knowledge_of
from ole5_voice.evals.items import HISTORY_FILE, GoldenSetError, read_toml
from ole5_voice.evals.kb_points import PointIndex, digest
from ole5_voice.evals.knowledge_depth_card import (
    DEPTH,
    MARGIN,
    PASSAGE_CHARS,
    DepthRecord,
    DepthRun,
    Failure,
    Stopped,
    depth_line,
    scorecard,
    talker_chars,
)
from ole5_voice.evals.knowledge_set import KNOWLEDGE_DIR, POINTS_FILE, Points, load_knowledge_items
from ole5_voice.evals.models import Split
from ole5_voice.evals.run_folder import RunFolder, folder_for
from ole5_voice.evals.run_parts import DATA
from ole5_voice.evals.runs import holds_placeholder
from ole5_voice.evals.talker_args import TalkerParts, seconds
from ole5_voice.evals.talker_data import TAGS
from ole5_voice.evals.talker_measure import CALLER, Todo, todo_of
from ole5_voice.evals.worktree import refused, run_checkout

_DESCRIPTION = "Run K0: each answerable dev variant searched once, k from 1 to 8, into --out."
_PASSAGES: Final = TypeAdapter(list[Passage])
log = get_logger(__name__)


@dataclass(frozen=True)
class _Data:
    """The knowledge set as K0 reads it: each answerable dev variant, the points' index and the
    digest of every file of the set."""

    todo: list[Todo]
    index: PointIndex
    digest: str


def _load(data: Path) -> _Data:
    """The answerable dev variants under `data`; refused when the set cannot be read or holds
    none."""
    folder = data / KNOWLEDGE_DIR
    try:
        items = load_knowledge_items(folder)
        points = read_toml(folder / POINTS_FILE, Points)
    except GoldenSetError as error:
        raise refused(
            f"the knowledge set cannot be read ({error})", "fix it; `poe check`"
        ) from None
    todo = [each for each in todo_of(items, "dev") if each.item.kind == "answerable"]
    if not todo:
        raise refused("the knowledge set holds no answerable dev item", "fix it; `poe check`")
    return _Data(todo, PointIndex(points), digest(sorted(folder.glob("*.toml"))))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe knowledge-depth", description=_DESCRIPTION)
    add = parser.add_argument
    add("--split", choices=get_args(Split), help="dev: held-out is never read by K0")
    add("--knowledge", help="the knowledge base's factory, ole5_voice.<module>:<name>")
    add("--env-file", type=Path, help="the .env the knowledge base's access loads from")
    add("--search-timeout-s", type=seconds, default=30.0, help="each search's limit (30)")
    add("--out", type=Path, help="a new folder outside the worktree, which git ignores")
    add("--note", help="why the run is made")
    return parser


def _require(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    named = ("split", "knowledge", "out", "note")
    if lacking := [f"--{name}" for name in named if getattr(args, name) is None]:
        parser.error(f"a run needs {', '.join(lacking)}")
    if args.split != "dev":
        parser.error("held-out is never read by K0: give --split dev")
    if holds_placeholder(args.note):
        parser.error("--note holds an install placeholder, which the docs check refuses")


def _shown(args: argparse.Namespace) -> dict[str, str]:
    """Every setting a run has, as its scorecard and history line record them."""
    return {
        "run.knowledge": args.knowledge,
        "run.chat_model": "none",
        "run.depth": str(DEPTH),
        "run.passage_chars": str(PASSAGE_CHARS),
        "run.margin": f"{float(MARGIN):g}",
        "run.search_timeout_s": str(args.search_timeout_s),
    }


async def _search(
    kb: KnowledgeBase, todo: Todo, index: PointIndex, timeout_s: float
) -> DepthRecord:
    """`todo`'s raw words searched once, as run K's reference search, at most `DEPTH`
    passages; a failure of the base or a search past `timeout_s` counted as its failure."""
    asked = todo.asked
    failure: Failure | None = None
    found: list[Passage] = []
    try:
        searched = kb.search(asked.text, language=TAGS[asked.language], caller=CALLER, limit=DEPTH)
        found = _PASSAGES.validate_python(await asyncio.wait_for(searched, timeout_s))[:DEPTH]
    except TimeoutError:
        failure = "stuck"
    except (T2VoiceError, ValidationError):  # the base's failure, or what is no passage
        failure = "provider"
    return DepthRecord(
        item=todo.item.id,
        variant=todo.variant,
        language=asked.language,
        expected=todo.item.expected,
        passages=tuple(passage.id for passage in found),
        points=tuple(index.point_of(passage.id) for passage in found),
        chars=await talker_chars(found),
        failure=failure,
    )


def _smoke_problem(record: DepthRecord) -> str | None:
    """Why the smoke search did not pass, or None when it did."""
    if record.failure is not None:
        return f"the search failed ({record.failure})"
    if not record.passages:
        return "the search found nothing"
    if all(point is None for point in record.points):
        return "no passage found is a point of the knowledge set"
    return None


def _first_hit(record: DepthRecord) -> int | None:
    """The place, from 1, of the first expected point found, or None."""
    places = [n for n, point in enumerate(record.points, start=1) if point in record.expected]
    return places[0] if places else None


async def _measure(
    kb: KnowledgeBase,
    data: _Data,
    found: list[DepthRecord],
    folder: RunFolder,
    args: argparse.Namespace,
    parts: TalkerParts,
    closing: Closing,
) -> Stopped | None:
    """Each variant searched, its record kept and written as it finishes; `smoke_failed` when
    the first search does not pass."""
    try:
        for number, each in enumerate(data.todo, start=1):
            began = parts.clock()
            record = await _search(kb, each, data.index, args.search_timeout_s)
            record = record.model_copy(update={"seconds": max(parts.clock() - began, 0.0)})
            if number == 1:
                if (problem := _smoke_problem(record)) is not None:
                    log.error("smoke_failed", problem=problem, item=record.item)
                    return "smoke_failed"
                log.info("smoke_passed", found=len(record.passages))
            found.append(record)
            folder.add_result(record)
            log.info(
                "variant_searched",
                done=number,
                of=len(data.todo),
                item=record.item,
                variant=record.variant,
                failure=record.failure,
                found=len(record.passages),
                first_hit=_first_hit(record),
                seconds=round(record.seconds, 3),
            )
        return None
    finally:
        await closing.aclose()  # the knowledge base, in the run's own loop


def _run(args: argparse.Namespace, parts: TalkerParts) -> int:
    """The run, what it built closed whenever it ends, a refusal's included."""
    closing = Closing()
    try:
        return _built(args, parts, closing)
    finally:
        closing.close_now()


def _built(args: argparse.Namespace, parts: TalkerParts, closing: Closing) -> int:
    checkout = run_checkout(parts.folder, parts.git)
    data = _load(checkout.top / DATA)
    kb = closing.add(knowledge_of(parts.load_factory, args.knowledge, env_file_of(args)))
    folder = folder_for(args.out, resume=False, checkout=checkout, git=parts.git)
    run = DepthRun(
        name=folder.out.name,
        started_at=parts.now(),
        commit=checkout.commit,
        settings=_shown(args),
        data_digest=data.digest,
        note=args.note,
    )
    folder.begin(run)
    found: list[DepthRecord] = []
    stopped: Stopped | None = None
    log.info("run_started", run=run.name, variants=len(data.todo))
    try:
        stopped = asyncio.run(_measure(kb, data, found, folder, args, parts, closing))
    except KeyboardInterrupt:
        stopped = "interrupted"
        log.warning("run_interrupted", done=len(found), of=len(data.todo))
    except BaseException as error:
        stopped = "error"
        log.error("run_failed", error=type(error).__name__, done=len(found))
        raise
    finally:
        complete = stopped is None and len(found) == len(data.todo)
        card = scorecard(run, found, complete=complete, stopped=stopped)
        folder.write_scorecard(card)
        line = depth_line(card)
        parts.append_line(line, checkout.top / DATA / HISTORY_FILE)
        parts.append_line(line, folder.out / HISTORY_FILE)
        log.info("run_finished", complete=complete, variants=len(found), kept_k=card.kept_k)
    return 0 if stopped is None else 1


def main(argv: Sequence[str] | None = None, *, parts: TalkerParts | None = None) -> int:
    """`uv run poe knowledge-depth`: run K0 on dev. 0 when the run is complete, 1 when it is
    not (a failed smoke search, an interrupt), 2 when it is refused before anything is sent."""
    parser = _parser()
    args = parser.parse_args(argv)
    _require(parser, args)
    configure_logging(loggers=LOGGERS)
    try:
        return _run(args, TalkerParts() if parts is None else parts)
    except T2VoiceError as error:
        log.error("depth_refused", code=error.code, message=error.message)
        return 2


if __name__ == "__main__":
    sys.exit(main())
