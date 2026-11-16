"""What runs K and S share before anything is sent (talker_args.py): the factories named on the
command line, the prices and limits read from it, the two settings a run uses (the adapter's key
from the environment, the call's built in code), every setting recorded with a secret only as
set or not set, and the digest of the files a run depends on."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from ole5_voice.evals.cli import seconds
from ole5_voice.evals.factories import load_factory
from ole5_voice.evals.kb_points import digest
from ole5_voice.evals.talker_args import (
    add_common,
    call_settings,
    chat_settings,
    flat,
    limit,
    price,
    shown,
)
from t2_agentic_voice import ConfigurationError, InvalidRequestError, VoiceSettings
from t2_agentic_voice.evals import Price

from tests.ole5_voice.evals.talker_fakes import JUDGE, TALKER, FakeKnowledgeBase, agent

KEY = "gsk_made_up_key_for_a_test_only"


def _args(*extra: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_common(parser)
    base = ["--arm", "k1", "--model", TALKER, "--reasoning-effort", "low"]
    base += ["--max-output-tokens", "512", "--timeout-s", "7", "--cap-usd", "1"]
    base += ["--price", f"{TALKER}=0.15/0.6", "--rpm", f"{TALKER}=30"]
    base += ["--agent", "ole5_voice.x:y", "--knowledge", "ole5_voice.x:z", "--search-tool", "t"]
    return parser.parse_args([*base, *extra])


def test_a_factory_is_a_callable_of_the_ole5_app() -> None:
    assert load_factory("ole5_voice.evals.talker_args:load_factory") is load_factory


@pytest.mark.parametrize(
    "spec",
    [
        "no_colon",
        "os.path:join",  # outside the app
        "ole5_voice.evals.talker_args:not a name",
        "ole5_voice.no_such_module:x",
        "ole5_voice.evals.talker_args:nothing_here",
        "ole5_voice.evals.talker_args:INPUT_BUDGET",  # not callable
    ],
)
def test_a_factory_outside_the_app_or_not_callable_is_refused(spec: str) -> None:
    with pytest.raises(InvalidRequestError, match="FIX: name a callable of the Ole5 app"):
        load_factory(spec)


def test_prices_and_limits_are_read_as_model_and_amount() -> None:
    assert price(f"{TALKER}=0.15/0.60") == (TALKER, Price(0.15, 0.60))
    assert limit(f"{JUDGE}=30") == (JUDGE, 30)
    for bad in (f"{TALKER}=0.15", "=1/2", f"{TALKER}=-1/2", f"{TALKER}=nan/1"):
        with pytest.raises(argparse.ArgumentTypeError):
            price(bad)
    for bad in ("30", f"{JUDGE}=0"):
        with pytest.raises(argparse.ArgumentTypeError):
            limit(bad)
    with pytest.raises(argparse.ArgumentTypeError):
        seconds("0")


def test_the_adapters_settings_take_the_key_from_the_env_file_alone(tmp_path: Path) -> None:
    env = tmp_path / "made-up.env"
    env.write_text(f"T2V_GROQ__API_KEY={KEY}\nT2V_LLM__TIMEOUT_S=99\n", encoding="utf-8")
    settings = chat_settings(_args("--env-file", str(env)))
    assert settings.groq.resolved_api_key() is not None
    assert settings.llm.timeout_s == 7.0  # the command line's, not the file's
    assert settings.groq.base_url == "https://api.groq.com" and settings.tracing.endpoint is None
    with pytest.raises(ConfigurationError):
        chat_settings(_args("--base-url", "http://not-https.example"))


def test_the_calls_settings_are_the_librarys_with_the_command_lines_llm() -> None:
    settings = call_settings(_args())
    assert settings.env == "test" and settings.llm.model == TALKER
    assert settings.llm.reasoning_effort == "low" and settings.llm.max_output_tokens == 512
    assert settings.session == VoiceSettings(env="test").session


def test_every_setting_is_recorded_a_secret_only_as_set(tmp_path: Path) -> None:
    env = tmp_path / "made-up.env"
    env.write_text(f"T2V_GROQ__API_KEY={KEY}\n", encoding="utf-8")
    args = _args("--env-file", str(env))
    recorded = shown(args, chat_settings(args), call_settings(args), agent(FakeKnowledgeBase()))
    assert recorded["groq.api_key"] == "set" and KEY not in str(recorded)
    assert recorded["llm.model"] == TALKER and recorded["run.agent_version"] == "t1"
    assert recorded[f"run.price.{TALKER}"] == "0.15/0.6"
    assert recorded[f"run.rpm.{TALKER}"] == "30" and "storage.var_dir" not in recorded
    library = flat(VoiceSettings(env="test"))
    assert library["groq.api_key_file"] == "not set" and library["tracing.endpoint"] == "none"
    assert library["tts.languages"] == "ar,ar-SA,en"


def test_the_digest_covers_each_files_name_and_bytes(tmp_path: Path) -> None:
    first, second = tmp_path / "a.toml", tmp_path / "b.toml"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    found = digest([first, second])
    assert found != digest([second, first])
    second.write_text("too", encoding="utf-8")
    assert found != digest([first, second])


def test_the_working_folders_env_is_read_when_no_file_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ole5_voice.evals import run_settings

    env = tmp_path / ".env"
    env.write_text(f"T2V_GROQ__API_KEY={KEY}\n", encoding="utf-8")
    monkeypatch.setattr(run_settings, "DOTENV", env)
    assert chat_settings(_args()).groq.resolved_api_key() is not None
