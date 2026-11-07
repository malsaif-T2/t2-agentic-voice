"""`poe first-audio` as a run (plan 006's registration, T): the recorded requests of a split
replayed, each as a call of the factory's agent, the arm's settings pinned, the smoke test
first, paced, capped before and during the run, stopped at a model's day, each result and each
reply's opening kept for a dev run, aggregates only for a held-out one, and every refusal before
anything is sent."""

from __future__ import annotations

import runpy
import sys
import warnings
import wave
from pathlib import Path

import pytest
from ole5_voice.evals import first_audio
from ole5_voice.evals.first_audio_run import LEAD_S
from ole5_voice.evals.first_audio_score import ReplayedCall, ReplayedTurn
from ole5_voice.evals.first_audio_setup import FirstAudioParts, agent_of, phrase_cache
from ole5_voice.evals.models import Item
from ole5_voice.evals.run_lines import TimingLine
from t2_agentic_voice import ProviderError, StorageSettings, T2VoiceError, VoiceAgent, VoiceSettings
from t2_agentic_voice.stores import PhraseCache

from tests.ole5_voice.evals.eot_support import paused
from tests.ole5_voice.evals.first_audio_support import CHAT, TRun, agent, call, t_run
from tests.ole5_voice.evals.run_support import World
from tests.ole5_voice.evals.timing_support import ARABIC, WHISPER
from tests.t2_agentic_voice.fakes import FakeTextToSpeech

# The tail after each recording at the tests' time limits: the turn's end (1 s), the transcript
# (6 s), the talker's three model requests (8 s each), its tool twice (5 s each) and the voice's
# first request (6 s), so any reply that still answers is heard.
TAIL = 47.0


def _fast() -> ReplayedTurn:
    return ReplayedTurn(ttfa_ms=1200.0)


def test_a_dev_run_replays_each_recorded_request_as_a_call_of_the_agent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = t_run(tmp_path, call(), call(), call(_fast()), call(ReplayedTurn(ttfa_ms=1500.0)))
    assert first_audio.main(run.argv(), parts=run.parts()) == 0
    built = run.replay.built
    assert isinstance(built["agent"], VoiceAgent) and len(built["agent"].tools) == 1
    assert built["phrases"] is run.cache and run.cache.declared == [built["agent"]]
    asked = [(a["language"], a["end_ms"], a["lead_s"], a["tail_s"]) for a in run.replay.asked]
    assert asked == [  # the smoke test's, then each recorded request, n20 marked at 1500 ms
        ("ar-SA", 1500.0, LEAD_S, TAIL),
        ("ar-SA", 1500.0, LEAD_S, TAIL),
        ("ar-SA", None, LEAD_S, TAIL),
        ("en", None, LEAD_S, TAIL),
    ]
    assert run.replay.started == run.replay.closed == 1 and run.stt.closed and run.tts.closed
    settings = run.built[0]
    assert (settings.tts.trim_silence, settings.llm.model, settings.llm.max_output_tokens) == (
        True,
        CHAT,
        512,
    )
    card = run.card()
    assert card.complete and card.phrase_requests == 4
    assert card.run.tail_s == TAIL and card.run.settings["run.tail_s"] == str(TAIL)
    assert [(v.item, v.end) for v in card.variants] == [
        ("n20_made_up", "label"),
        ("n02_made_up", "detector"),
        ("n21_made_up", "detector"),
    ]
    paths = card.totals.paths
    assert (paths["search"].turns, paths["search"].median_ms) == (1, 2500.0)
    assert (paths["no_search"].turns, paths["no_search"].median_ms) == (2, 1350.0)
    assert card.totals.progress_lines == 1 and card.totals.progress_late == 0
    held = {target.name: target.holds for target in card.targets}
    assert held == {
        "no_search_median_ms": True,
        "no_search_p90_ms": True,
        "search_median_ms": True,
        "search_p90_ms": True,
        "progress_late": True,
    }
    assert card.chat.requests == 8 and card.run.settings["run.tools"] == "declared"
    first = card.variants[0].openings[0]
    assert first == "replies/n20_made_up-laptop-0.wav"
    with wave.open(str(run.out / first), "rb") as reader:
        assert (reader.getframerate(), reader.getnframes()) == (24_000, 2400)
    assert len((run.out / "results.jsonl").read_text(encoding="utf-8").splitlines()) == 3
    (line, _), (copy, _) = run.lines.appended
    assert isinstance(line, TimingLine) and line == copy
    assert line.medians_ms["search"] == 2500.0 and line.medians_ms["no_search"] == 1350.0
    assert line.requests == {WHISPER: 4, ARABIC: 4, CHAT: 8}
    assert line.cost_usd == pytest.approx(card.cost_usd) and card.cost_usd > 0
    assert "variant_done" in capsys.readouterr().out


def test_an_msa_request_is_held_in_the_language_the_agent_gives_an_msa_caller(
    tmp_path: Path,
) -> None:
    """The agent speaks Saudi Arabic and English only, as Ole5's talker does: an MSA request's
    call is held in Saudi Arabic, the agent's language for an `ar` locale, and answered in its
    voice, as a real call of the agent would be."""

    def items(world: World) -> list[Item]:
        return [paused(world, "n20_made_up"), paused(world, "n07_made_up", language="msa")]

    run = t_run(tmp_path, call(_fast()), items=items)
    assert first_audio.main(run.argv(), parts=run.parts()) == 0
    assert [a["language"] for a in run.replay.asked] == ["ar-SA", "ar-SA", "ar-SA"]
    assert [v.language for v in run.card().variants] == ["saudi", "msa"]


def test_arm_tn_leaves_the_agents_tools_out(tmp_path: Path) -> None:
    run = t_run(tmp_path, call(_fast()))
    assert first_audio.main(run.argv("--no-tools", "--smoke-only"), parts=run.parts()) == 0
    assert run.replay.built["agent"].tools == ()
    assert run.replay.asked[0]["tail_s"] == TAIL - 10.0  # no tool runs
    card = run.card()
    assert card.run.tools is False and card.run.settings["run.tools"] == "none"
    assert card.variants == () and card.complete


def test_a_held_out_run_keeps_aggregates_only(tmp_path: Path) -> None:
    def items(world: World) -> list[Item]:
        held = [paused(world, f"n0{n}_held", kind="request") for n in range(3, 7)]
        return [paused(world, "n20_made_up"), *held]

    held = tuple(f"n0{n}_held" for n in range(3, 7))
    run = t_run(tmp_path, call(), call(_fast()), items=items, held_out=held)
    assert first_audio.main(run.argv(split="held-out"), parts=run.parts()) == 0
    card = run.card()
    assert card.variants == () and card.breakdowns == {} and card.totals.variants == 4
    assert card.totals.paths["no_search"].median_ms == 1200.0  # 4 items: shown
    assert card.totals.paths["search"].median_ms is None  # none: withheld
    assert not (run.out / "results.jsonl").exists() and not (run.out / "replies").exists()
    assert run.replay.asked[0]["end_ms"] == 1500.0  # the smoke test is the dev recording


@pytest.mark.parametrize(
    "smoke",
    [
        call(ReplayedTurn(failure="server_error")),
        call(ReplayedTurn(ttfa_ms=900.0), ReplayedTurn(ttfa_ms=900.0)),
        call(ReplayedTurn(searched=True)),  # a reply never heard by the call's end
    ],
)
def test_a_smoke_test_that_failed_stops_the_run(tmp_path: Path, smoke: ReplayedCall) -> None:
    run = t_run(tmp_path, smoke)
    assert first_audio.main(run.argv(), parts=run.parts()) == 1
    card = run.card()
    assert card.stopped == "smoke_failed" and card.variants == () and len(run.replay.asked) == 1


def test_a_phrase_cache_that_failed_stops_the_run_before_any_call(tmp_path: Path) -> None:
    run = t_run(tmp_path)

    async def failing(agent: VoiceAgent) -> int:
        raise ProviderError("server_error", True)

    run.cache.declare = failing  # type: ignore[method-assign]
    assert first_audio.main(run.argv(), parts=run.parts()) == 1
    assert run.card().stopped == "phrases_failed" and run.replay.asked == []


def test_a_rate_limited_call_is_replayed_after_a_minute(tmp_path: Path) -> None:
    limited = call(ReplayedTurn(failure="rate_limited"))
    run = t_run(tmp_path, call(), limited, call(), call())
    assert first_audio.main(run.argv(), parts=run.parts()) == 0
    assert 60.0 in run.clock.pauses
    assert [v.attempts for v in run.card().variants] == [2, 1, 1]


def test_a_cut_call_is_reported_apart(tmp_path: Path) -> None:
    cut = call(_fast(), _fast())
    run = t_run(tmp_path, call(), cut, call(), call())
    assert first_audio.main(run.argv(), parts=run.parts()) == 0
    card = run.card()
    assert card.totals.cut == 1 and card.variants[0].timed is None
    assert card.totals.paths["search"].turns == 2


def test_the_day_stops_the_run_before_a_recording_a_model_has_no_room_for(tmp_path: Path) -> None:
    run = t_run(tmp_path, call(), call(remaining=1), call())
    assert first_audio.main(run.argv(), parts=run.parts()) == 1
    card = run.card()
    assert card.stopped == "day_limit" and len(card.variants) == 1


def test_the_cap_stops_the_run_before_a_recording_it_cannot_afford(tmp_path: Path) -> None:
    costly = call()
    spent = costly.chat.model_copy(update={"input_tokens": 3_000_000, "cached_tokens": 0})
    run = t_run(tmp_path, call(), ReplayedCall(costly.turns, costly.openings, costly.usage, spent))
    argv = run.argv()
    argv[argv.index("--cap-usd") + 1] = "0.5"  # the budget of 4 recordings, about $0.14, fits
    assert first_audio.main(argv, parts=run.parts()) == 1
    card = run.card()
    assert card.stopped == "cap" and len(card.variants) == 1 and card.cost_usd > 0.45


def test_an_interrupt_keeps_what_was_measured(tmp_path: Path) -> None:
    run = t_run(tmp_path, call(), call(), KeyboardInterrupt())
    assert first_audio.main(run.argv(), parts=run.parts()) == 1
    card = run.card()
    assert card.stopped == "interrupted" and len(card.variants) == 1


def _refused(run: TRun, argv: list[str], capsys: pytest.CaptureFixture[str], says: str) -> None:
    assert first_audio.main(argv, parts=run.parts()) == 2
    assert says in capsys.readouterr().out
    assert run.replay.asked == [] and run.cache.declared == [] and not run.out.exists()


def test_each_refusal_comes_before_anything_is_sent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = t_run(tmp_path)
    _refused(run, run.argv(factory="missing"), capsys, "--agent names no factory")
    _refused(run, run.argv(factory="no_agent"), capsys, "gives no agent with instructions")
    _refused(run, run.argv(factory="echo_agent"), capsys, "gives no agent with instructions")
    _refused(run, run.argv(factory="english_agent"), capsys, "the agent speaks no ar-SA")
    argv = run.argv()
    argv[argv.index("--cap-usd") + 1] = "0.01"
    _refused(run, argv, capsys, "passes --cap-usd")
    argv = run.argv()
    argv.remove(f"{ARABIC}=40")
    argv.remove("--tts-price")
    _refused(run, argv, capsys, f"--tts-price names no price for {ARABIC}")
    argv = run.argv()
    argv[argv.index("--out") + 1] = str(run.world.main / "var" / "runs" / "T1")
    _refused(run, argv, capsys, "is not a name")
    _refused(run, run.argv("--set", "llm.model=made-up"), capsys, "--set")
    none = t_run(tmp_path / "none", items=lambda world: [paused(world, "s01_made_up")])
    _refused(none, none.argv(), capsys, "no recorded request")


def test_until_the_replay_is_wired_a_run_is_refused_before_anything_is_sent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = t_run(tmp_path)
    unwired = run.parts(replay=FirstAudioParts().replay)
    assert first_audio.main(run.argv(), parts=unwired) == 2
    assert "replay is not wired" in capsys.readouterr().out
    assert run.cache.declared == [] and not run.out.exists()


@pytest.mark.parametrize(
    ("flag", "value"), [("--cap-usd", "-1"), ("--stt-rpm", "0"), ("--tts-price", "made-up")]
)
def test_a_flag_out_of_its_range_is_refused(
    tmp_path: Path, flag: str, value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as done:
        first_audio.main([*t_run(tmp_path).argv(), flag, value])
    assert done.value.code == 2 and flag in capsys.readouterr().err


def test_a_run_names_its_arm_models_prices_and_cap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as done:
        first_audio.main(["--split", "dev", "--note", "n"])
    err = capsys.readouterr().err
    assert done.value.code == 2 and "--trim-silence" in err and "--llm-input-tokens" in err
    argv = t_run(tmp_path).argv()
    argv[argv.index("--note") + 1] = "{{" + "NAME" + "}}"  # apart, or the docs check flags it
    with pytest.raises(SystemExit):
        first_audio.main(argv)
    assert "install placeholder" in capsys.readouterr().err


@pytest.mark.parametrize(
    "module", ["ole5_voice.evals.first_audio", "ole5_voice.evals.first_audio_listen"]
)
def test_the_commands_print_their_help_and_run_nothing(
    module: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", [module, "--help"])
    with warnings.catch_warnings(), pytest.raises(SystemExit) as done:
        warnings.simplefilter("ignore", RuntimeWarning)  # imported already, by the other tests
        runpy.run_module(module, run_name="__main__", alter_sys=True)
    assert done.value.code == 0 and capsys.readouterr().out.startswith("usage: poe first-audio")


def test_a_reply_with_no_opening_keeps_none(tmp_path: Path) -> None:
    run = t_run(tmp_path, call(), call(opening=False))
    assert first_audio.main(run.argv(), parts=run.parts()) == 0
    assert {v.openings for v in run.card().variants} == {(None,)}


@pytest.mark.parametrize("named", ["made_up_missing_module:agent", "no-colon", ":agent"])
def test_an_agent_factory_that_cannot_be_found_is_refused(named: str) -> None:
    with pytest.raises(T2VoiceError, match="--agent names no factory"):
        agent_of(named, tools=True)


def test_the_phrase_cache_is_kept_in_the_agents_own_folder(tmp_path: Path) -> None:
    settings = VoiceSettings(env="test", storage=StorageSettings(var_dir=tmp_path))
    cache = phrase_cache(settings, FakeTextToSpeech(), agent())
    assert isinstance(cache, PhraseCache) and list(tmp_path.iterdir()) == []
