"""Runs K and S joined to the merged code (talker_run.py, scenario_run.py, factories.py): each
command line reaches its smoke test with Ole5's own agent factory (`talker_agent`, given the
knowledge base) and a knowledge factory of the real one's signature (given the env file), the
library's real `TextCall` on the system clock, a fake chat model and a fake knowledge base, so
nothing is sent; and every run closes its knowledge base and its chat model when it ends, also
after a refusal that comes once they are built. Ole5's knowledge factory reads only the knowledge
base's access, and both of Ole5's factories have the signatures a run gives them."""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Callable
from pathlib import Path

import pytest
from ole5_voice.agent import talker_agent
from ole5_voice.evals import scenario_run, talker_run
from ole5_voice.evals.factories import AgentFactory, KnowledgeFactory, load_factory
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.scenario_score import ScenarioScorecard
from ole5_voice.evals.talker_args import TalkerParts
from ole5_voice.evals.talker_call import ask
from ole5_voice.evals.talker_score import TalkerScorecard
from ole5_voice.knowledge_base import QdrantKnowledgeBase, knowledge_base
from ole5_voice.settings import load_knowledge
from t2_agentic_voice import ConfigurationError, LlmSettings, VoiceSettings
from t2_agentic_voice.evals import TextCall
from t2_agentic_voice.ports import KnowledgeBase

from tests.ole5_voice.evals.talker_fakes import FakeChat, FakeKnowledgeBase
from tests.ole5_voice.evals.talker_support import Setup, make_setup
from tests.ole5_voice.evals.test_scenario_run import write_scenarios

DEV = ["--split", "dev", "--call-language", "variant"]
OLE5_AGENT = "ole5_voice.agent:talker_agent"
OLE5_TOOL = "search_knowledge"
PASSWORD = "made-up-kb-password-0123"


Loader = Callable[[str], Callable[..., object]]


def _ole5(setup: Setup, argv: list[str]) -> tuple[Loader, list[str]]:
    """A loader that gives Ole5's real agent factory, and a fake knowledge base's factory with
    the real one's signature; and `argv` naming them."""

    def knowledge(env_file: Path | None) -> KnowledgeBase:
        return setup.kb

    def load(spec: str) -> Callable[..., object]:
        return knowledge if spec == "ole5_voice.fake:kb" else load_factory(spec)

    named = list(argv)
    named[named.index("--agent") + 1] = OLE5_AGENT
    named[named.index("--search-tool") + 1] = OLE5_TOOL
    return load, named


def _real(setup: Setup, load: Loader) -> TalkerParts:
    return dataclasses.replace(setup.parts(), load_factory=load, call=TextCall)


def test_run_ks_smoke_reaches_ole5s_agent_through_the_real_text_call(tmp_path: Path) -> None:
    setup = make_setup(tmp_path)
    load, argv = _ole5(setup, [*setup.argv("--smoke-only"), *DEV])
    assert talker_run.main(argv, parts=_real(setup, load)) == 0
    card = TalkerScorecard.model_validate_json((setup.out() / SCORECARD_FILE).read_bytes())
    (smoke,) = card.variants
    assert card.complete and smoke.failure is None and smoke.turn is not None
    assert smoke.turn.said == "a short answer" and smoke.turn.first_clause_s is not None
    assert card.run.settings["run.agent_name"] == "ole5" and smoke.judged is not None
    # The talker's requests are Ole5's, its search tool among their tools, and the run closed
    # what it built.
    talker = [r for r in setup.chat.requests if r.model == card.run.model]
    assert talker and OLE5_TOOL in {tool.name for tool in talker[0].tools}
    assert setup.chat.closed and setup.kb.closed


def test_run_ss_smoke_reaches_ole5s_agent_through_the_real_text_call(tmp_path: Path) -> None:
    setup = make_setup(tmp_path)
    folder = setup.data / "scenarios"
    folder.mkdir()
    for n in range(1, 11):
        lines = [f'id = "s{n:02d}"', f"rehearsal = {str(n <= 6).lower()}", 'language = "en"']
        lines += ['notes = "Made up."', "", "[[turns]]", f'says = "question {n}"', "search = false"]
        (folder / f"s{n:02d}.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    load, argv = _ole5(setup, setup.argv("--smoke-only", out="s-a"))
    assert scenario_run.main(argv, parts=_real(setup, load)) == 0
    card = ScenarioScorecard.model_validate_json((setup.out("s-a") / SCORECARD_FILE).read_bytes())
    (smoke,) = card.plays
    assert smoke.failure is None and smoke.passed and smoke.turns[0].said == "a short answer"
    assert setup.chat.closed and setup.kb.closed


@pytest.mark.parametrize("command", [talker_run, scenario_run])
def test_a_refusal_once_the_base_and_the_model_are_built_closes_both(
    tmp_path: Path, command: object, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = make_setup(tmp_path)
    if command is scenario_run:
        write_scenarios(setup.data)
        argv = setup.argv(cap="0.000001", out="s-a")
    else:
        argv = [*setup.argv(cap="0.000001"), *DEV]
    assert command.main(argv, parts=setup.parts()) == 2  # type: ignore[attr-defined]
    assert "leaves no room for one more" in capsys.readouterr().out
    assert setup.chat.requests == [] and setup.chat.closed and setup.kb.closed


def test_a_refusal_before_the_model_is_built_closes_the_knowledge_base(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = make_setup(tmp_path)
    argv = [*setup.argv(), *DEV]
    argv[argv.index("--search-tool") + 1] = "other_tool"
    assert talker_run.main(argv, parts=setup.parts()) == 2
    assert "the agent has no tool other_tool" in capsys.readouterr().out
    assert setup.kb.closed and not setup.chat.closed  # the model was never built


def test_ole5s_factories_have_the_signatures_a_run_gives_them() -> None:
    agent: AgentFactory = talker_agent  # checked by mypy, as the runs call them
    knowledge: KnowledgeFactory = knowledge_base
    assert load_factory(OLE5_AGENT) is agent
    assert load_factory("ole5_voice.knowledge_base:knowledge_base") is knowledge
    assert agent(None).tools == ()  # Tn's talker, with no search
    assert OLE5_TOOL in {tool.name for tool in agent(FakeKnowledgeBase()).tools}


def _env(path: Path, *lines: str) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_ole5s_knowledge_factory_reads_only_the_knowledge_bases_access(tmp_path: Path) -> None:
    env = _env(
        tmp_path / "kb.env",
        "QDRANT_URL=https://made-up.example/qdrant",
        "QDRANT_LOGIN_EMAIL=someone@example.com",
        f"QDRANT_LOGIN_PASSWORD={PASSWORD}",
        "OLE5_VOICE_KB_TENANT=ole5-test",
    )  # no access code, no join key, no widget setting
    access = load_knowledge(env)
    assert (access.qdrant_url, access.tenant) == ("https://made-up.example/qdrant", "ole5-test")
    assert access.login_password.get_secret_value() == PASSWORD and PASSWORD not in repr(access)
    built = knowledge_base(env)
    assert isinstance(built, QdrantKnowledgeBase)
    asyncio.run(built.aclose())


@pytest.mark.parametrize(
    ("lines", "says"),
    [
        ((), "The knowledge base's access is not set"),
        (("QDRANT_URL=https://made-up.example/qdrant",), "set only in part"),
        (
            (
                "QDRANT_URL=http://made-up.example/qdrant",
                "QDRANT_LOGIN_EMAIL=someone@example.com",
                f"QDRANT_LOGIN_PASSWORD={PASSWORD}",
            ),
            "QDRANT_URL must be an https:// URL",
        ),
    ],
)
def test_ole5s_knowledge_factory_refuses_an_access_not_set_naming_never_showing(
    tmp_path: Path, lines: tuple[str, ...], says: str
) -> None:
    with pytest.raises(ConfigurationError, match=says) as caught:
        knowledge_base(_env(tmp_path / "kb.env", *lines))
    assert PASSWORD not in caught.value.message and "made-up.example" not in caught.value.message


def test_the_talkers_assertion_through_the_real_text_call_is_a_stall_never_a_crash() -> None:
    """TextCall raises the talker's AssertionError (a fake model's script that ran out) rather
    than letting the `error` notice pass for it: a run reads it as a stuck variant."""
    chat = FakeChat()
    chat.errors.append(AssertionError("the fake model's script ran out"))
    settings = VoiceSettings(env="test", llm=LlmSettings(model="openai/gpt-oss-120b"))
    agent = talker_agent(FakeKnowledgeBase())
    with pytest.raises(TimeoutError, match="never came"):
        asyncio.run(ask(agent, chat, settings, words="How do I print?", language="en"))
