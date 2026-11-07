"""What `poe eval-talker` refuses before anything is sent (talker_run.py): the command line's
missing flags, a checkout or an `--out` a run may not use, data it cannot read, an agent it
cannot measure, a model with no price or limits, a cap or a day with no room, a shared history
that cannot hold its line, and a resume of another run. Each refusal sends no request and
creates no folder."""

from __future__ import annotations

import dataclasses
import runpy
import sys
import warnings
from collections.abc import Callable
from pathlib import Path

import pytest
from ole5_voice.evals import run_folder, talker_run
from ole5_voice.evals.history import read_history, render_history
from ole5_voice.evals.talker_args import TalkerParts
from ole5_voice.evals.talker_lines import TalkerLine
from t2_agentic_voice import Language, VoiceAgent
from t2_agentic_voice.ports import KnowledgeBase

from tests.ole5_voice.evals.talker_fakes import JUDGE, TALKER, agent
from tests.ole5_voice.evals.talker_support import Setup, item, make_setup, write_points_text

DEV = ["--split", "dev", "--call-language", "variant"]


@pytest.fixture
def setup(tmp_path: Path) -> Setup:
    return make_setup(tmp_path)


def _refused(setup: Setup, argv: list[str], words: str, capsys: pytest.CaptureFixture[str]) -> None:
    parts = setup.parts()
    assert talker_run.main(argv, parts=parts) == 2
    assert words in capsys.readouterr().out
    assert setup.chat.requests == [] and setup.calls.said == []
    assert not (setup.out() / "run.json").exists()


@pytest.mark.parametrize(
    ("drop", "flag"),
    [("--arm", "--arm"), ("--split", "--split"), ("--call-language", "--call-language")],
)
def test_a_run_needs_each_flag(
    setup: Setup, drop: str, flag: str, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [*setup.argv(), *DEV]
    at = argv.index(drop)
    del argv[at : at + 2]
    with pytest.raises(SystemExit) as done:
        talker_run.main(argv, parts=setup.parts())
    assert done.value.code == 2 and flag in capsys.readouterr().err


@pytest.mark.parametrize(
    ("extra", "words"),
    [
        (["--split", "held-out", "--resume"], "one whole session"),
        (["--split", "held-out", "--smoke-only"], "one whole session"),
        (["--resume", "--smoke-only"], "no --smoke-only"),
        (["--arm", "K1"], "--arm is not a name"),
        (["--note", "a {{" + "NAME" + "}}"], "install placeholder"),
    ],
)
def test_the_command_line_refuses_what_a_run_cannot_be(
    setup: Setup, extra: list[str], words: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        talker_run.main([*setup.argv(), *DEV, *extra], parts=setup.parts())
    assert words in capsys.readouterr().err


def test_a_dirty_tree_is_refused(setup: Setup, capsys: pytest.CaptureFixture[str]) -> None:
    setup.world.git.dirty = True
    _refused(setup, [*setup.argv(), *DEV], "the worktree has changes", capsys)


def test_an_out_that_exists_is_refused(setup: Setup, capsys: pytest.CaptureFixture[str]) -> None:
    setup.out().mkdir(parents=True)
    _refused(setup, [*setup.argv(), *DEV], "exists", capsys)


def test_an_out_whose_name_is_not_a_name_is_refused(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    _refused(setup, [*setup.argv(out="K1 A"), *DEV], "is not a name", capsys)


def test_a_snapshot_without_an_expected_points_text_is_refused(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    write_points_text(setup.points_text, points=1)  # a2 expects point 2
    _refused(setup, [*setup.argv(), *DEV], "no text for 1 expected point(s)", capsys)


def test_an_unreadable_knowledge_set_is_refused(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    (setup.data / "knowledge" / "a1.toml").write_text("id = 1\n", encoding="utf-8")
    _refused(setup, [*setup.argv(), *DEV], "the knowledge set cannot be read", capsys)


def test_an_agent_without_the_search_tool_is_refused(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [*setup.argv(), *DEV]
    argv[argv.index("--search-tool") + 1] = "other_tool"
    _refused(setup, argv, "the agent has no tool other_tool", capsys)


def _loading(setup: Setup, **made: Callable[..., object]) -> None:
    load = setup.load

    def loader(spec: str) -> Callable[..., object]:
        return made.get(spec.rpartition(":")[2], load(spec))

    setup.parts = lambda: dataclasses.replace(Setup.parts(setup), load_factory=loader)  # type: ignore[method-assign]


def test_a_knowledge_factory_that_gives_no_base_is_refused(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    _loading(setup, kb=lambda env_file: object())
    _refused(setup, [*setup.argv(), *DEV], "gave no knowledge base", capsys)


def test_an_agent_factory_that_gives_no_agent_is_refused(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    _loading(setup, agent=lambda kb: "not an agent")
    _refused(setup, [*setup.argv(), *DEV], "gave no VoiceAgent", capsys)


def test_variants_in_a_language_the_agent_does_not_speak_are_refused(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    def english_only(kb: KnowledgeBase) -> VoiceAgent:
        declared = agent(kb)
        return VoiceAgent(
            name=declared.name,
            languages=[Language.english(greeting="Hello.")],
            instructions="Answer.",
            tools=declared.tools,
        )

    _loading(setup, agent=english_only)
    _refused(setup, [*setup.argv(), *DEV], "speaks no language of the saudi variants", capsys)


@pytest.mark.parametrize(("flag", "model"), [("--price", JUDGE), ("--rpd", TALKER)])
def test_a_model_with_no_price_or_limit_is_refused(
    setup: Setup, flag: str, model: str, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [*setup.argv(), *DEV]
    at = next(n for n, value in enumerate(argv) if value == flag and argv[n + 1].startswith(model))
    del argv[at : at + 2]
    _refused(setup, argv, f"{flag} names nothing for {model}", capsys)


def test_a_cap_with_no_room_for_one_variant_is_refused(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    _refused(setup, [*setup.argv(cap="0.001"), *DEV], "leaves no room for one more", capsys)


def test_a_held_out_run_that_would_pass_the_days_limit_is_refused(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    setup.today[JUDGE] = 990
    argv = [*setup.argv(), "--split", "held-out", "--call-language", "first"]
    _refused(setup, argv, "daily limit leaves 10 requests today", capsys)


def test_a_history_that_cannot_hold_the_line_is_refused(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    setup.accepts = False
    _refused(setup, [*setup.argv(), *DEV], "takes no line of run K's kind yet", capsys)


def test_the_shared_history_takes_run_ks_line_and_reads_it_back(setup: Setup) -> None:
    parts = dataclasses.replace(
        setup.parts(),
        history_accepts=run_folder.history_accepts,
        append_line=run_folder.append_shared,
    )
    assert talker_run.main([*setup.argv(), *DEV], parts=parts) == 0
    (line,) = read_history(setup.data / "history.jsonl")
    assert isinstance(line, TalkerLine) and line.arm == "k1" and line.complete
    assert read_history(setup.out() / "history.jsonl") == (line,)
    assert "## Talker runs" in render_history([line])


def test_a_resume_of_a_folder_with_no_run_is_refused(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    _refused(setup, [*setup.argv(), *DEV, "--resume"], "holds no run", capsys)


def test_a_resume_with_another_command_line_is_refused(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    setup.today[TALKER] = 998
    assert talker_run.main([*setup.argv(), *DEV], parts=setup.parts()) == 1
    setup.today[TALKER] = 0
    argv = [*setup.argv(), *DEV, "--resume"]
    argv[argv.index("--note") + 1] = "another reason"
    requests = len(setup.chat.requests)
    assert talker_run.main(argv, parts=setup.parts()) == 2
    assert "differs in note" in capsys.readouterr().out
    assert len(setup.chat.requests) == requests


def test_each_command_prints_its_help(capsys: pytest.CaptureFixture[str]) -> None:
    from ole5_voice.evals import judge_check, scenario_run, talker_compare, talker_keep

    for command in (talker_run, scenario_run, talker_compare, talker_keep, judge_check):
        with pytest.raises(SystemExit) as done:
            command.main(["--help"])
        assert done.value.code == 0
        assert capsys.readouterr().out.startswith("usage: poe ")


def test_a_knowledge_set_with_none_of_the_split_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = make_setup(tmp_path, [item("a1"), item("a2")])
    argv = [*setup.argv(), "--split", "held-out", "--call-language", "first"]
    _refused(setup, argv, "holds no dev variant, or none of the split", capsys)


def test_the_parts_of_a_real_run_are_the_librarys_and_the_systems() -> None:
    parts = TalkerParts()
    assert parts.folder.name == "evals" and parts.now().tzinfo is not None
    assert parts.history_accepts is run_folder.history_accepts


@pytest.mark.parametrize(
    "module",
    [
        "ole5_voice.evals.talker_run",
        "ole5_voice.evals.talker_compare",
        "ole5_voice.evals.talker_keep",
        "ole5_voice.evals.judge_check",
        "ole5_voice.evals.scenario_run",
    ],
)
def test_a_command_run_as_its_task_runs_it_prints_its_help(
    module: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", [module, "--help"])
    with warnings.catch_warnings(), pytest.raises(SystemExit) as done:
        warnings.simplefilter("ignore", RuntimeWarning)  # runpy: the module was imported already
        runpy.run_module(module, run_name="__main__", alter_sys=True)
    assert done.value.code == 0 and capsys.readouterr().out.startswith("usage: poe ")
