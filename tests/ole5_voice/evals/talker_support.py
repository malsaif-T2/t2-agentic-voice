"""What the tests of runs K and S share: a made-up knowledge set and points' snapshot in a run's
world (`run_support.World`), made-up records and scorecards, and the parts a run is built from
on the fakes of talker_fakes.py, so nothing is sent and no time passes."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ole5_voice.evals.judge import Judged
from ole5_voice.evals.knowledge_set import KnowledgeItem, KnowledgeVariant
from ole5_voice.evals.run_parts import DATA
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.talker_args import TalkerParts
from ole5_voice.evals.talker_data import Clause, HeardTurn
from ole5_voice.evals.talker_score import PriceShown, TalkerRun, VariantRecord, scorecard
from pydantic import BaseModel
from t2_agentic_voice import VoiceAgent
from t2_agentic_voice.ports import KnowledgeBase

from tests.ole5_voice.evals.run_support import FakeClock, World, make_world
from tests.ole5_voice.evals.samples import WHEN
from tests.ole5_voice.evals.talker_fakes import (
    DOCUMENT,
    JUDGE,
    TALKER,
    TOOL,
    Calls,
    FakeChat,
    FakeKnowledgeBase,
    agent,
)


def item(
    item_id: str,
    *,
    split: str = "dev",
    kind: str = "answerable",
    asked: Sequence[tuple[str, str]] = (("english", "How do I print?"), ("saudi", "كيف أطبع؟")),
    expected: Sequence[str] = ("guide-001",),
) -> KnowledgeItem:
    """A made-up item: its variants' words are `asked` with the item's ID at their end."""
    return KnowledgeItem(
        id=item_id,
        split=split,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        needs_search=kind in ("answerable", "none"),
        variants=tuple(
            KnowledgeVariant(language=language, text=f"{text} {item_id}")  # type: ignore[arg-type]
            for language, text in asked
        ),
        expected=tuple(expected) if kind == "answerable" else (),
        key_facts=(f"A first made-up fact of {item_id}.", f"A second one of {item_id}."),
        notes="A made-up item.",
    )


def _toml(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, tuple | list):
        return "[" + ", ".join(_toml(each) for each in value) + "]"
    raise TypeError(value)


def write_knowledge(data: Path, items: Sequence[KnowledgeItem], points: int = 6) -> None:
    """The items under `data/knowledge/`, with a `points.toml` of one document's `points`."""
    folder = data / "knowledge"
    folder.mkdir(parents=True, exist_ok=True)
    for each in items:
        dumped = each.model_dump(mode="json")
        lines = [f"{k} = {_toml(v)}" for k, v in dumped.items() if k != "variants"]
        for variant in each.variants:
            lines += ["", "[[variants]]", f"language = {_toml(variant.language)}"]
            lines += [f"text = {_toml(variant.text)}"]
        (folder / f"{each.id}.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    text = ["[[documents]]", 'key = "guide"', f"name = {_toml(DOCUMENT)}"]
    for n in range(1, points + 1):
        text += ["", "[[points]]", f'id = "guide-{n:03d}"', 'document = "guide"']
        text += [f'chunk = "chunk_{n:03d}"']
    (folder / "points.toml").write_text("\n".join(text) + "\n", encoding="utf-8")


def write_points_text(path: Path, points: int = 6) -> Path:
    """A made-up snapshot of the points' payloads, one a line, the last with no text."""
    lines = [
        json.dumps(
            {
                "id": n,
                "payload": {
                    "group_id": "made-up",
                    "metadata": {
                        "document_name": DOCUMENT,
                        "chunk_id": f"chunk_{n:03d}",
                        "source_text": f"The made-up text of point {n}.",
                    },
                },
            },
            ensure_ascii=False,
        )
        for n in range(1, points + 1)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class Lines:
    """Stands in for the shared history's appender: keeps each line and its path."""

    def __init__(self) -> None:
        self.lines: list[tuple[BaseModel, Path]] = []

    def __call__(self, line: BaseModel, path: Path) -> None:
        self.lines.append((line, path))


@dataclass
class Setup:
    """A run's world and the fakes it is built from, to read back after `main`."""

    world: World
    clock: FakeClock = field(default_factory=FakeClock)
    chat: FakeChat = field(default_factory=FakeChat)
    kb: FakeKnowledgeBase = field(default_factory=FakeKnowledgeBase)
    calls: Calls = field(default_factory=Calls)
    lines: Lines = field(default_factory=Lines)
    today: Counter[str] = field(default_factory=Counter)
    accepts: bool = True

    @property
    def data(self) -> Path:
        return self.world.top / DATA

    @property
    def points_text(self) -> Path:
        return self.world.main / "points.jsonl"

    def out(self, name: str = "k1-a") -> Path:
        return self.world.main / "var" / "runs" / name

    def load(self, spec: str) -> Callable[..., object]:
        def knowledge(env_file: Path | None) -> FakeKnowledgeBase:
            return self.kb

        def built(kb: KnowledgeBase) -> VoiceAgent:
            self.calls.kb = kb
            return agent(kb)

        found: dict[str, Callable[..., object]] = {
            "ole5_voice.fake:agent": built,
            "ole5_voice.fake:kb": knowledge,
        }
        return found[spec]

    def parts(self) -> TalkerParts:
        return TalkerParts(
            folder=self.world.top,
            git=self.world.git,
            chat=lambda settings: self.chat,
            call=self.calls,
            load_factory=self.load,
            append_line=self.lines,
            history_accepts=lambda line: self.accepts,
            requests_today=lambda path, day: self.today,
            now=lambda: WHEN,
            clock=self.clock,
            sleep=self.clock.sleep,
        )

    def argv(self, *extra: str, out: str = "k1-a", cap: str = "1") -> list[str]:
        found = ["--arm", "k1", "--model", TALKER, "--reasoning-effort", "low"]
        found += ["--max-output-tokens", "512", "--timeout-s", "8", "--judge-model", JUDGE]
        found += ["--price", f"{TALKER}=0.15/0.60", "--price", f"{JUDGE}=0.59/0.79"]
        for flag, n in (("--rpm", 30), ("--tpm", 100_000), ("--rpd", 1000)):
            found += [flag, f"{TALKER}={n}", flag, f"{JUDGE}={n}"]
        found += ["--cap-usd", cap, "--agent", "ole5_voice.fake:agent"]
        found += ["--knowledge", "ole5_voice.fake:kb", "--search-tool", TOOL]
        found += ["--points-text", str(self.points_text), "--out", str(self.out(out))]
        return [*found, "--note", "a made-up run", *extra]


def record(
    item: str,
    variant: str = "v1",
    *,
    kind: str = "answerable",
    language: str = "english",
    passed: bool | None = True,
    hit: bool | None = True,
    first_clause_s: float | None = 0.5,
    split: str = "dev",
    failure: str | None = None,
) -> VariantRecord:
    turn = HeardTurn(
        fate="answered",
        clauses=(Clause(text="one two three", language="en", fate="played", played_fraction=1.0),),
        first_clause_s=first_clause_s,
        first_token_s=0.2,
        model_requests=2,
    )
    return VariantRecord(
        item=item,
        variant=variant,
        split=split,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        language=language,  # type: ignore[arg-type]
        needs_search=True,
        tag="en",
        turn=turn,
        own_hit=hit if kind == "answerable" and failure is None else None,
        raw_hit=hit if kind == "answerable" and failure is None else None,
        search_right=True if failure is None else None,
        language_right=True if failure is None else None,
        judged=Judged(verdict="right" if passed else "wrong", requests=1)
        if failure is None
        else None,
        passed=passed if failure is None else None,
        failure=failure,  # type: ignore[arg-type]
    )


def write_run(
    folder: Path,
    records: Sequence[VariantRecord],
    *,
    arm: str = "k1",
    model: str = "openai/gpt-oss-120b",
    split: str = "dev",
    commit: str = "ab" * 20,
    effort: str = "low",
    complete: bool = True,
) -> Path:
    run = TalkerRun(
        name=folder.name,
        started_at=WHEN,
        commit=commit,
        arm=arm,
        model=model,
        judge_model="llama-3.3-70b-versatile",
        split=split,  # type: ignore[arg-type]
        settings={
            "llm.model": model,
            "llm.reasoning_effort": effort,
            "run.arm": arm,
            f"run.price.{model}": "1/2",
        },
        prices={model: PriceShown(input_usd=1, output_usd=2)},
        cap_usd=1.0,
        data_digest="cd" * 32,
        note="made up",
    )
    card = scorecard(run, list(records), complete=complete, stopped=None, sessions=[])
    folder.mkdir(parents=True)
    (folder / SCORECARD_FILE).write_text(card.model_dump_json(), encoding="utf-8")
    return folder


def make_setup(tmp_path: Path, items: Sequence[KnowledgeItem] | None = None) -> Setup:
    """A world with `items` (two dev items and one held-out, by default) and their snapshot."""
    setup = Setup(make_world(tmp_path))
    found = items or (
        item("a1"),
        item("a2", expected=("guide-002",)),
        item("n1", kind="none"),
        item("h1", split="held-out"),
        item("h2", split="held-out", expected=("guide-003",)),
        item("h3", split="held-out", kind="small_talk"),
    )
    write_knowledge(setup.data, found)
    write_points_text(setup.points_text)
    return setup
