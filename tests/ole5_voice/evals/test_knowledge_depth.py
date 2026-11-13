"""`poe knowledge-depth` (knowledge_depth.py), run K0, on fakes only: each answerable dev
variant's raw words searched once, as run K's reference search, with a limit of 8 and no chat
model; the order of the passages found decides the k kept; each passage's characters as the
knowledge tool hands them to the talker; the smoke search first; held-out never read; failures
counted apart; and what a run refuses before anything is sent (Q20)."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import runpy
import sys
import warnings
from collections.abc import Callable
from pathlib import Path

import pytest
from ole5_voice.evals import knowledge_depth
from ole5_voice.evals.knowledge_depth_card import DepthLine, DepthScorecard
from ole5_voice.evals.run_folder import RESULTS_FILE, RUN_FILE
from ole5_voice.evals.runs import SCORECARD_FILE
from t2_agentic_voice import Caller, T2VoiceError
from t2_agentic_voice.ports import Passage

from tests.ole5_voice.evals.talker_fakes import DOCUMENT, FakeKnowledgeBase
from tests.ole5_voice.evals.talker_support import Setup, item, make_setup

ITEMS = (
    item("a1", expected=("guide-001", "guide-002")),
    item("a2", expected=("guide-003",)),
    item("n1", kind="none"),
    item("h1", split="held-out"),
)
ASKED = ("How do I print? a1", "كيف أطبع؟ a1", "How do I print? a2", "كيف أطبع؟ a2")


def _passage(n: int, text: str = "Some text.", document: str = DOCUMENT) -> Passage:
    return Passage(id=f"{document}/chunk_{n:03d}", title="A title", text=text, score=0.5)


class _Knowledge(FakeKnowledgeBase):
    """The fake knowledge base, raising `raised`'s error, or never answering, for a query."""

    def __init__(self) -> None:
        super().__init__()
        self.raised: dict[str, BaseException] = {}
        self.stuck: set[str] = set()

    async def search(
        self, query: str, *, language: str, caller: Caller, limit: int
    ) -> list[Passage]:
        if query in self.stuck:
            await asyncio.Event().wait()
        if query in self.raised:
            raise self.raised[query]
        return await super().search(query, language=language, caller=caller, limit=limit)


@pytest.fixture
def setup(tmp_path: Path) -> Setup:
    found = make_setup(tmp_path, ITEMS)
    found.kb = _Knowledge()
    order = {0: (4, 1, 5, 2), 1: (1, 2), 2: (3,), 3: (5, 6, 3)}
    for n, query in enumerate(ASKED):
        found.kb.found[query] = [_passage(point) for point in order[n]]
    return found


def _argv(setup: Setup, *extra: str, out: str = "k0-a") -> list[str]:
    found = ["--split", "dev", "--knowledge", "ole5_voice.fake:kb"]
    return [*found, "--out", str(setup.out(out)), "--note", "a made-up run", *extra]


def _card(setup: Setup, name: str = "k0-a") -> DepthScorecard:
    return DepthScorecard.model_validate_json((setup.out(name) / SCORECARD_FILE).read_bytes())


def test_each_answerable_dev_variant_is_searched_once_and_the_order_decides_the_k(
    setup: Setup,
) -> None:
    assert knowledge_depth.main(_argv(setup), parts=setup.parts()) == 0
    # The smoke search is the first variant's own: each searched once, with a limit of 8, in
    # its words' language; no `none` item, no held-out item, no chat request, no call.
    assert setup.kb.searches == [
        (q, tag, 8) for q, tag in zip(ASKED, ("en", "ar-SA") * 2, strict=True)
    ]
    assert setup.chat.requests == [] and setup.calls.said == []
    card = _card(setup)
    assert card.complete and card.stopped is None and card.run.split == "dev"
    assert (card.items, card.variants, card.failures) == (2, 4, 0)
    first = card.records[0]
    assert first.points == ("guide-004", "guide-001", "guide-005", "guide-002")
    assert first.chars == (10, 10, 10, 10)
    found = [at.found for at in card.depths]
    assert found == pytest.approx([3 / 8, 5 / 8, 7 / 8, 1, 1, 1, 1, 1])
    assert [at.hit for at in card.depths][:2] == pytest.approx([1 / 2, 3 / 4])
    assert card.kept_k == 4  # the smallest k within 0.05 of k = 8's
    deepest = card.depths[-1]
    assert (deepest.chars_median, deepest.chars_p90, deepest.chars_most) == (25, 37, 40)
    lines = (setup.out("k0-a") / RESULTS_FILE).read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["variant"] for line in lines] == ["v1", "v2", "v1", "v2"]
    ((shared, to), (copied, beside)) = setup.lines.lines
    assert shared == copied and isinstance(shared, DepthLine)
    assert to == setup.data / "history.jsonl" and beside == setup.out("k0-a") / "history.jsonl"
    assert shared.kept_k == 4 and shared.complete and shared.depths == card.depths
    assert shared.settings["run.chat_model"] == "none"
    assert shared.settings["run.passage_chars"] == "1500"


def test_the_characters_are_what_the_knowledge_tool_hands_the_talker(setup: Setup) -> None:
    long = "\n".join(["w" * 99] * 40)  # 3,999 characters: the talker reads 15 lines and " ..."
    setup.kb.found[ASKED[0]] = [_passage(1, long), _passage(2, "  Short.  ")]
    assert knowledge_depth.main(_argv(setup), parts=setup.parts()) == 0
    assert _card(setup).records[0].chars == (15 * 99 + 14 + 4, 6)


@pytest.mark.parametrize(
    ("broken", "problem"),
    [
        ("fails", "the search failed (provider)"),
        ("stuck", "the search failed (stuck)"),
        ("nothing", "the search found nothing"),
        ("unknown", "no passage found is a point of the knowledge set"),
    ],
)
def test_a_smoke_search_that_does_not_pass_stops_the_run(
    setup: Setup, broken: str, problem: str, capsys: pytest.CaptureFixture[str]
) -> None:
    kb = setup.kb
    assert isinstance(kb, _Knowledge)
    if broken == "fails":
        kb.failing.add(ASKED[0])
    elif broken == "stuck":
        kb.stuck.add(ASKED[0])
    else:
        unknown = [_passage(1, document="another document")] if broken == "unknown" else []
        kb.found[ASKED[0]] = unknown
    argv = _argv(setup, "--search-timeout-s", "0.05")
    assert knowledge_depth.main(argv, parts=setup.parts()) == 1
    assert problem in capsys.readouterr().out
    assert len(kb.searches) == (0 if broken == "stuck" else 1)  # nothing after the smoke
    card = _card(setup)
    assert card.stopped == "smoke_failed" and not card.complete and card.kept_k is None
    assert card.records == () and not (setup.out("k0-a") / RESULTS_FILE).exists()
    [(line, _), _] = setup.lines.lines
    assert isinstance(line, DepthLine) and not line.complete


@pytest.mark.parametrize("broken", ["fails", "stuck", "not_passages"])
def test_a_later_search_that_fails_is_counted_apart(setup: Setup, broken: str) -> None:
    kb = setup.kb
    assert isinstance(kb, _Knowledge)
    if broken == "fails":
        kb.failing.add(ASKED[3])
    elif broken == "stuck":
        kb.stuck.add(ASKED[3])
    else:
        kb.found[ASKED[3]] = [{"id": "x"}]  # type: ignore[list-item]
    argv = _argv(setup, "--search-timeout-s", "0.05")
    assert knowledge_depth.main(argv, parts=setup.parts()) == 0
    card = _card(setup)
    assert card.complete and (card.items, card.variants, card.failures) == (2, 4, 1)
    assert card.records[3].failure == ("stuck" if broken == "stuck" else "provider")
    assert card.records[3].passages == ()
    # a2 is its first variant alone now: every point found from k = 1.
    assert [at.found for at in card.depths][:4] == pytest.approx([5 / 8, 7 / 8, 7 / 8, 1])
    assert card.kept_k == 4


def test_an_interrupt_keeps_what_was_searched_and_no_k(setup: Setup) -> None:
    kb = setup.kb
    assert isinstance(kb, _Knowledge)
    kb.raised[ASKED[2]] = KeyboardInterrupt()
    assert knowledge_depth.main(_argv(setup), parts=setup.parts()) == 1
    card = _card(setup)
    assert card.stopped == "interrupted" and len(card.records) == 2 and card.kept_k is None
    assert kb.closed


def test_an_error_the_run_does_not_score_is_raised_once_its_scorecard_is_written(
    setup: Setup,
) -> None:
    kb = setup.kb
    assert isinstance(kb, _Knowledge)
    kb.raised[ASKED[1]] = RuntimeError("made up")
    with pytest.raises(RuntimeError, match="made up"):
        knowledge_depth.main(_argv(setup), parts=setup.parts())
    assert _card(setup).stopped == "error" and kb.closed


def test_a_library_error_once_the_run_began_ends_it_as_not_complete(setup: Setup) -> None:
    """Exit 1, as run T's, with its scorecard and line written (2, refused, before: evl-11): a
    clock that raises stands for any library error a variant's search meets past the base's."""
    ticks: list[int] = []

    def clock() -> float:
        ticks.append(1)
        if len(ticks) == 3:  # the second variant's start
            raise T2VoiceError("Made up.")
        return 0.0

    parts = dataclasses.replace(setup.parts(), clock=clock)
    assert knowledge_depth.main(_argv(setup), parts=parts) == 1
    card = _card(setup)
    assert card.stopped == "error" and len(card.records) == 1 and setup.kb.closed
    assert len(setup.lines.lines) == 2


def _refused(setup: Setup, argv: list[str], words: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert knowledge_depth.main(argv, parts=setup.parts()) == 2
    assert words in capsys.readouterr().out
    assert setup.kb.searches == [] and setup.lines.lines == []
    assert not (setup.out("k0-a") / RUN_FILE).exists()


@pytest.mark.parametrize(
    ("extra", "words"),
    [
        (["--split", "held-out"], "held-out is never read by K0"),
        (["--note", "a {{" + "NAME" + "}}"], "install placeholder"),
        (["--search-timeout-s", "0"], "must be a finite number of seconds above 0"),
    ],
)
def test_the_command_line_refuses_what_a_run_cannot_be(
    setup: Setup, extra: list[str], words: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as done:
        knowledge_depth.main(_argv(setup, *extra), parts=setup.parts())
    assert done.value.code == 2 and words in capsys.readouterr().err
    assert setup.kb.searches == []


@pytest.mark.parametrize("flag", ["--split", "--knowledge", "--out", "--note"])
def test_a_run_needs_each_flag(setup: Setup, flag: str, capsys: pytest.CaptureFixture[str]) -> None:
    argv = _argv(setup)
    at = argv.index(flag)
    del argv[at : at + 2]
    with pytest.raises(SystemExit) as done:
        knowledge_depth.main(argv, parts=setup.parts())
    assert done.value.code == 2 and flag in capsys.readouterr().err


def test_a_dirty_tree_and_an_out_that_exists_are_refused(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    setup.world.git.dirty = True
    _refused(setup, _argv(setup), "the worktree has changes", capsys)
    setup.world.git.dirty = False
    setup.out("k0-a").mkdir(parents=True)
    assert knowledge_depth.main(_argv(setup), parts=setup.parts()) == 2
    assert "exists" in capsys.readouterr().out and setup.kb.closed


def test_a_knowledge_set_it_cannot_read_or_with_no_answerable_dev_item_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bare = make_setup(tmp_path / "bare", [item("n1", kind="none"), item("h1", split="held-out")])
    _refused(bare, _argv(bare), "holds no answerable dev item", capsys)
    broken = make_setup(tmp_path / "broken", ITEMS)
    (broken.data / "knowledge" / "a1.toml").write_text("id = 1\n", encoding="utf-8")
    _refused(broken, _argv(broken), "the knowledge set cannot be read", capsys)


def test_a_knowledge_factory_that_gives_no_base_is_refused(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    def loader(spec: str) -> Callable[..., object]:
        return lambda env_file: object()

    setup.parts = lambda: dataclasses.replace(Setup.parts(setup), load_factory=loader)  # type: ignore[method-assign]
    _refused(setup, _argv(setup), "gave no knowledge base", capsys)


def test_the_command_prints_its_help_run_as_its_task_runs_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = "ole5_voice.evals.knowledge_depth"
    monkeypatch.setattr(sys, "argv", [module, "--help"])
    with warnings.catch_warnings(), pytest.raises(SystemExit) as done:
        warnings.simplefilter("ignore", RuntimeWarning)  # runpy: the module was imported already
        runpy.run_module(module, run_name="__main__", alter_sys=True)
    assert done.value.code == 0
    assert capsys.readouterr().out.startswith("usage: poe knowledge-depth")
