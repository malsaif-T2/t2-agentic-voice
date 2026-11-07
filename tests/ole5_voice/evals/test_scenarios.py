"""Run S's scenarios (scenarios.py): the ten committed scripted calls break no rule, six of them
the rehearsal's, each naming only dev items of the knowledge set; each rule refuses what it
should; and no scenario's words appear in the product's source (evaluation.md, "No item in the
product"), the presets' own words aside."""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.evals.items import EVALS, GoldenSetError
from ole5_voice.evals.knowledge_set import KNOWLEDGE_DIR, load_knowledge_items
from ole5_voice.evals.scenarios import (
    FOLLOWS,
    REGISTER_CHECKS,
    SCENARIOS_DIR,
    Scenario,
    ScriptTurn,
    load_scenarios,
    problems,
)
from t2_agentic_voice.domain.words import PRESET_WORDS, WORD_KINDS

from tests.ole5_voice.evals.talker_support import item
from tests.ole5_voice.evals.test_no_item_in_source import SCANNED, find_pasted, fold

ROOT = Path(__file__).resolve().parents[3]


def test_the_committed_scenarios_break_no_rule() -> None:
    scenarios = load_scenarios(EVALS / SCENARIOS_DIR)
    assert problems(scenarios, load_knowledge_items(EVALS / KNOWLEDGE_DIR)) == []
    assert [s.id for s in scenarios if s.rehearsal] == [
        "s01_password_stop_go_on",
        "s02_archive_repeat_part",
        "s03_english_question",
        "s04_mumble",
        "s05_correction",
        "s09_person_over_reply",
    ]
    whens = {turn.when for scenario in scenarios for turn in scenario.turns}
    assert whens == {None, "agent_speaking", "tool_running"}
    assert {turn.follows for s in scenarios for turn in s.turns} == {None, *FOLLOWS}


def test_no_scenarios_words_appear_in_the_source() -> None:
    presets = {
        fold(word)
        for words in PRESET_WORDS.values()
        for kind in WORD_KINDS
        for word in getattr(words, kind)
    }
    said = {
        fold(turn.says): f"scenario {scenario.id}"
        for scenario in load_scenarios(EVALS / SCENARIOS_DIR)
        for turn in scenario.turns
    }
    assert len(said) > 15
    assert find_pasted(ROOT, SCANNED, said, presets) == []


def _scenario(name: str, *turns: ScriptTurn, rehearsal: bool = False) -> Scenario:
    return Scenario(id=name, rehearsal=rehearsal, language="ar-SA", notes="Made up.", turns=turns)


def test_each_rule_refuses_what_it_should() -> None:
    items = [item("a1"), item("h1", split="held-out")]
    good = ScriptTurn(says="hi", search=False)
    found = problems(
        [
            _scenario("s1", ScriptTurn(says="x", when="agent_speaking", search=True)),
            _scenario("s1", good, ScriptTurn(says="y", cuts_reply=True)),
            _scenario("s3", good, ScriptTurn(says="z", when="tool_running", search=True)),
            _scenario("s4", ScriptTurn(says="w", item="h1"), ScriptTurn(says="v", item="zz")),
            _scenario("s5", ScriptTurn(says="u"), rehearsal=True),
        ],
        items,
    )
    assert found == [
        "5 scenarios, not the registered 10",
        "1 of the rehearsal's scenarios, not 6",
        "the scenario 's1' twice",
        "s1, turn 1: the first turn follows no reply",
        "s1, turn 2: cuts a reply only when said over it (when = agent_speaking)",
        "s4, turn 1: names 'h1', a held-out item, whose answers are read as counts",
        "s4, turn 2: names 'zz', which the knowledge set does not hold",
        "s5, turn 1: expects nothing of its reply",
    ]


def test_a_turns_expectations_are_its_facts_or_its_items_and_what_it_follows() -> None:
    items = {"a1": item("a1")}
    assert ScriptTurn(says="x", item="a1").expectations(items) == items["a1"].key_facts
    turn = ScriptTurn(says="x", item="a1", facts=("Own.",), follows="repeats")
    assert turn.expectations(items) == ("Own.", FOLLOWS["repeats"])
    assert ScriptTurn(says="x").expectations(items) == ()
    # A reply held to Arabic is held to its register too, which the judge is asked apart (run
    # K's first dev round): never one of the expectations; its script is read from its words.
    saudi = ScriptTurn(says="x", language="ar-SA", follows="continues")
    assert saudi.expectations(items) == (FOLLOWS["continues"],)
    assert ScriptTurn(says="x", language="ar").expectations(items) == ()
    assert REGISTER_CHECKS == {"ar-SA": "saudi", "ar": "msa"}
    assert [ScriptTurn(says="x", language=tag).held_register() for tag in ("ar-SA", "ar")] == [
        "saudi",
        "msa",
    ]
    assert ScriptTurn(says="x", language="en").held_register() is None
    assert ScriptTurn(says="x").held_register() is None


def test_a_folder_that_cannot_be_read_is_refused(tmp_path: Path) -> None:
    with pytest.raises(GoldenSetError, match="no such folder"):
        load_scenarios(tmp_path / "none")
    folder = tmp_path / "scenarios"
    folder.mkdir()
    (folder / "s1.toml").write_text(
        'id = "s2"\nrehearsal = false\nlanguage = "en"\nnotes = "x"\n[[turns]]\nsays = "hi"\n',
        encoding="utf-8",
    )
    with pytest.raises(GoldenSetError, match="holds the scenario 's2'"):
        load_scenarios(folder)
    # No turn expects a correction to cancel a search, which TextCall's calm speech outlasts.
    (folder / "s1.toml").write_text(
        'id = "s1"\nrehearsal = false\nlanguage = "en"\nnotes = "x"\n[[turns]]\nsays = "hi"\n'
        "cancels_search = true\n",
        encoding="utf-8",
    )
    with pytest.raises(GoldenSetError):
        load_scenarios(folder)
