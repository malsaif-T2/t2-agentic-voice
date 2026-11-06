"""`poe eval` (evaluation.md, "Running"), with the fake `SpeechToText`, a fake `git` and
temporary folders: what is refused before any call, the smoke test, results kept after an
interruption, a held-out run's silence about its items, the cap, the history line, and that no
line shows a key or a transcript."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable
from pathlib import Path

import pytest
from ole5_voice.evals import run, run_settings
from ole5_voice.evals.groq_answerer import Policy
from ole5_voice.evals.items import HISTORY_FILE
from ole5_voice.evals.models import Item
from ole5_voice.evals.runs import HistoryLine, VariantResult
from t2_agentic_voice import ConfigurationError, ProviderError, VoiceSettings
from t2_agentic_voice.ports import AudioClip, SpeechToText, Transcript

from tests.ole5_voice.evals.fakes import FakeSpeechToText
from tests.ole5_voice.evals.run_support import DEV, HELD_OUT, Setup, World
from tests.ole5_voice.evals.samples import WHEN

KEY = "gsk_made-up-key-0000"  # never a real key


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        ([], "a run needs --answerer, --split, --out, --note"),
        (["--answerer", "groq", *DEV[2:]], "--price-per-hour, --cap-usd"),
        ([*HELD_OUT, "--questions", "q"], "held-out run"),
        ([*HELD_OUT, "--tracing-endpoint", "http://127.0.0.1:6006/v1/traces"], "untraced"),
        ([*DEV, "--smoke-only", "--windows-ms", "500"], "and no windows"),
        ([*DEV, "--variant-timeout-s", "0"], "--variant-timeout-s: must be a finite number of"),
        ([*DEV, "--clips-from", "c"], "serves a windows run"),
        (["--max-rpm", "0", "--show-settings"], "must be 1 or more"),
        (["--cap-usd", "nan", "--show-settings"], "finite"),
    ],
)
def test_a_run_needs_its_flags_together(
    argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as done:
        run.main(argv)
    assert done.value.code == 2 and message in capsys.readouterr().err


def test_a_runs_policy_defaults_are_the_answerers(capsys: pytest.CaptureFixture[str]) -> None:
    """The flags take `groq_answerer.Policy`'s defaults, and their help says them."""
    args = run._parser().parse_args([])
    given = (args.max_attempts, args.max_rpm, args.variant_timeout_s)
    assert given == (Policy().max_attempts, Policy().max_rpm, Policy().variant_timeout_s)
    with pytest.raises(SystemExit):
        run.main(["--help"])
    shown = " ".join(capsys.readouterr().out.split())
    assert (
        f"at most ({Policy().max_rpm})" in shown
        and f"limit ({Policy().variant_timeout_s:g})" in shown
    )


def test_show_settings_says_whether_the_key_is_set_never_the_key_or_the_env_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = Setup(tmp_path)
    env = tmp_path / "made-up.env"
    env.write_text(f"# a private note\nT2V_GROQ__API_KEY={KEY}\nT2V_STT__TIMEOUT_S=7\n", "utf-8")
    # Neither the SDK's own name for a key nor a tracing endpoint in the environment reaches a run.
    monkeypatch.setenv("GROQ_API_KEY", f"{KEY}-shell")
    monkeypatch.setenv("T2V_TRACING__ENDPOINT", "http://127.0.0.1:6006/v1/traces")
    argv = ["--show-settings", "--env-file", str(env), "--model", "whisper-large-v3-turbo"]
    argv += ["--audio", f"owner={setup.world.audio}", "--out", str(setup.out())]
    assert run.main(argv, parts=setup.parts()) == 0
    out = capsys.readouterr().out
    for shown in (
        "name=groq.api_key value=set",
        "name=groq.api_key_file value='not set'",
        "name=groq.base_url value=https://api.groq.com",
        "name=stt.model value=whisper-large-v3-turbo",
        "name=stt.timeout_s value=7.0",
        "name=tracing.endpoint value=none",
        "state=ready",
        "name=audio.owner",
        "state=new",
    ):
        assert shown in out, shown
    assert KEY not in out and "private note" not in out and str(env) not in out
    assert setup.calls() == 0 and not setup.out().exists()
    key_file = tmp_path / "key.txt"
    key_file.write_text(f"{KEY}\n", encoding="utf-8")
    env.write_text(f"T2V_GROQ__API_KEY_FILE={key_file}\n", encoding="utf-8")
    assert run.main(["--show-settings", "--env-file", str(env)], parts=setup.parts()) == 0
    out = capsys.readouterr().out
    assert "name=groq.api_key value=set" in out and "name=groq.api_key_file value=set" in out
    assert KEY not in out and str(key_file) not in out
    assert run.main(["--show-settings"], parts=setup.parts()) == 0
    assert "name=groq.api_key value='not set'" in capsys.readouterr().out


def test_show_settings_says_why_a_run_could_not_start_there(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path)
    setup.world.git.dirty = True
    (setup.out()).mkdir(parents=True)
    assert run.main(["--show-settings", "--out", str(setup.out())], parts=setup.parts()) == 0
    out = capsys.readouterr().out
    assert "has changes" in out and "exists" in out and "name=spelling" in out
    setup.world.git.failing = ("rev-parse",)
    assert run.main(["--show-settings"], parts=setup.parts()) == 0
    assert "not inside a git checkout" in capsys.readouterr().out


def test_settings_that_do_not_load_are_reported_without_their_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path)
    assert setup.main("--env-file", str(tmp_path / "missing.env")) == 2
    assert "env file given cannot be read" in capsys.readouterr().out
    assert setup.main("--tracing-endpoint", "http://user:hunter2@127.0.0.1:6006/v1/traces") == 2
    out = capsys.readouterr().out
    assert "--tracing-endpoint is not" in out and "hunter2" not in out
    assert setup.calls() == 0


def test_a_refusal_while_the_settings_load_is_logged_as_the_library_logs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], new_process_logs: Callable[[str, str], str]
) -> None:
    """Before the settings load, `poe eval` logs with the library's defaults (UTC, ISO 8601),
    never unconfigured, where a new process would show no line at all (app7)."""
    empty = tmp_path / "empty.env"
    empty.write_text("", encoding="utf-8")
    argv = ["--show-settings", "--env-file", str(empty), "--base-url", "http://x.example"]
    assert run.main(argv, parts=Setup(tmp_path).parts()) == 2
    assert "[error" in new_process_logs(capsys.readouterr().out, "eval_refused")


def test_a_setting_other_than_a_url_that_fails_is_refused_not_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `--model` the library does not take (were `MODELS` to drift from it) is a refusal, not
    a KeyError from looking up the URL flags."""
    monkeypatch.setattr(run, "MODELS", (*run_settings.MODELS, "whisper-made-up"))
    argv = ["--show-settings", "--model", "whisper-made-up"]
    assert run.main(argv, parts=Setup(tmp_path).parts()) == 2
    assert "eval_refused" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        ("main checkout", "the main checkout"),
        ("dirty", "has changes"),
        ("out exists", "exists"),
        ("out tracked", "git would track it"),
        ("out name", "is not a name, which is a lowercase letter"),
        ("no key", "T2V_GROQ__API_KEY"),
    ],
)
def test_a_run_is_refused_before_any_call(
    tmp_path: Path, damage: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path)
    out = "R1" if damage == "out name" else "r1"
    if damage == "main checkout":
        setup.world.git.top = setup.world.main
    setup.world.git.dirty = damage == "dirty"
    if damage == "out exists":
        setup.out().mkdir(parents=True)
    if damage == "out tracked":
        setup.world.git.ignored = ()

    def no_key(settings: VoiceSettings) -> SpeechToText:
        raise ConfigurationError("T2V_GROQ__API_KEY is not set. FIX: set it.")

    setup.adapter = no_key if damage == "no key" else None
    assert setup.main(out=out) == 2
    assert message in capsys.readouterr().out
    assert setup.calls() == 0 and setup.writer.calls == [] and setup.history.lines == []
    assert not setup.out("r1").exists() or damage == "out exists"


def test_the_reference_answerer_scores_every_variant_right_and_appends_no_history(
    tmp_path: Path,
) -> None:
    setup = Setup(tmp_path)
    assert setup.main(answerer="reference") == 0
    results = setup.results()
    assert [r.variant for r in results if r.right] == ["a-v1", "b-v1", "b-v2"]
    info, _, complete, out = setup.writer.calls[0]
    assert (info.answerer, info.model, info.price_per_hour_usd) == ("reference", None, 0)
    assert (info.name, info.commit, info.started_at, complete) == ("r1", "ab" * 20, WHEN, True)
    assert out == setup.out().resolve()
    lines = (setup.out() / run.RESULTS_FILE).read_text(encoding="utf-8").splitlines()
    assert [VariantResult.model_validate_json(line) for line in lines] == list(results)
    assert setup.history.lines == [] and setup.calls() == 0


def test_a_groq_run_appends_its_history_line_to_the_worktree_and_beside_the_scorecard(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path)
    setup.stt = FakeSpeechToText(["zebra quartz"] + ["open the inbox"] * 3)
    assert setup.main() == 0
    assert setup.calls() == 4  # the smoke test, then the three variants
    assert [r.right for r in setup.results()] == [True, True, True]
    line, copy = setup.history.lines  # in the worktree's history, and beside the scorecard
    assert copy == line
    assert (line.answerer, line.model, line.split, line.items, line.variants) == (
        "groq",
        "whisper-large-v3",
        "dev",
        2,
        3,
    )
    assert (line.billed_seconds, line.price_per_hour_usd, line.complete) == (40.0, 0.111, True)
    assert line.cost_usd == pytest.approx(40 / 3600 * 0.111)
    assert (line.scorecard, line.commit, line.settings["groq.api_key"]) == (
        "scorecard.json",
        "ab" * 20,
        "not set",
    )
    for history in (setup.world.data / HISTORY_FILE, setup.out() / HISTORY_FILE):
        assert HistoryLine.model_validate_json(history.read_text(encoding="utf-8")) == line
    out = capsys.readouterr().out
    assert "smoke_passed" in out and "variant=b-v2" in out and "verdict=right" in out
    assert "zebra" not in out and "open the inbox" not in out


def test_a_smoke_test_that_needed_a_retry_fails_the_run_before_any_variant(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path)
    setup.stt = FakeSpeechToText([ProviderError("rate_limited", True), "open the inbox"])
    assert setup.main() == 1
    assert setup.calls() == 2 and "smoke_failed" in capsys.readouterr().out
    assert setup.results() == () and not (setup.out() / run.RESULTS_FILE).exists()
    line = setup.history.lines[0]  # it spent: the attempt is recorded
    assert (line.complete, line.variants, line.billed_seconds) == (False, 0, 20.0)


class Interrupting(FakeSpeechToText):
    """Hears the reference, but its call `at` hangs; with `interrupt`, the run is interrupted
    there, as Ctrl+C does."""

    def __init__(self, at: int, *, interrupt: bool = True) -> None:
        super().__init__(["open the inbox"] * 10)
        self.at, self.interrupt = at, interrupt

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        if len(self.calls) == self.at:
            self.calls.append((clip, language, prompt))
            if self.interrupt:
                signal.raise_signal(signal.SIGINT)
            await asyncio.sleep(5)  # cancelled: by the interrupt, or at the variant's limit
        return await super().transcribe(clip, language=language, prompt=prompt)


def test_an_interrupted_dev_run_keeps_what_it_measured(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.stt = Interrupting(at=2)  # the smoke test and one variant are done
    assert setup.main() == 1
    assert [r.variant for r in setup.results()] == ["a-v1"]
    assert setup.writer.calls[0][2] is False  # incomplete
    lines = (setup.out() / run.RESULTS_FILE).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and setup.history.lines[0].complete is False


def test_a_held_out_run_writes_aggregates_only_and_names_no_item(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("T2V_TRACING__ENDPOINT", "http://127.0.0.1:6006/v1/traces")  # as a .env may

    def build(world: World) -> tuple[Item, ...]:
        return world.item("dev-a"), world.item("secret-one"), world.item("secret-two", takes=2)

    setup = Setup(tmp_path, build, held_out=("secret-one", "secret-two"))
    setup.stt = FakeSpeechToText(["open the inbox", "open the inbox", "wrong", "open"])
    assert setup.main(split="held-out", out="h1") == 0
    info, results, complete, _ = setup.writer.calls[0]
    assert (info.split, info.traced, complete, len(results)) == ("held-out", False, True, 3)
    assert not (setup.out("h1") / run.RESULTS_FILE).exists()
    assert setup.history.lines[0].accuracy == pytest.approx(1 / 3)
    out = capsys.readouterr().out
    assert "done=3" in out and "secret" not in out and "verdict" not in out and "wrong" not in out
    assert setup.tracing.spans == []


def test_an_interrupted_held_out_run_keeps_no_result(tmp_path: Path) -> None:
    setup = Setup(tmp_path, lambda w: (w.item("dev-a"), w.item("h", takes=3)), held_out=("h",))
    setup.stt = Interrupting(at=2)
    assert setup.main(split="held-out", out="h1") == 1
    assert setup.results() == () and setup.writer.calls[0][2] is False
    assert setup.history.lines[0].variants == 0


def test_the_cap_ends_a_run_between_requests(tmp_path: Path) -> None:
    """The run's least cost is within the cap, so it starts; a retry it did not count takes it
    to the cap, which ends it before the next request."""
    setup = Setup(tmp_path)
    retried = ["open the inbox", ProviderError("server_error", True)]
    setup.stt = FakeSpeechToText([*retried, *["open the inbox"] * 4])
    # $10 a request: four at the least (the smoke test and three), and the retry.
    assert setup.main("--price-per-hour", "3600", "--cap-usd", "45") == 1
    assert setup.calls() == 4 and [r.variant for r in setup.results()] == ["a-v1", "b-v1"]
    assert setup.history.lines[0].cost_usd == pytest.approx(40.0)


def test_stuck_and_failed_variants_are_infrastructure_failures_of_a_complete_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path)
    setup.stt = FakeSpeechToText(["a", ProviderError("rejected", False), "b", "c"])
    assert setup.main() == 0
    assert [r.answer.failure for r in setup.results()] == ["provider", None, None]
    assert "verdict=provider" in capsys.readouterr().out
    slow = Setup(tmp_path / "slow")
    slow.stt = Interrupting(at=1, interrupt=False)  # the first variant after the smoke test
    assert slow.main("--variant-timeout-s", "0.05") == 0
    assert [r.answer.failure for r in slow.results()] == ["stuck", None, None]
    assert [q.outcome for q in slow.results()[0].answer.requests] == ["stuck"]
    stuck_smoke = Setup(tmp_path / "smoke")
    stuck_smoke.stt = Interrupting(at=0, interrupt=False)
    assert stuck_smoke.main("--variant-timeout-s", "0.05") == 1 and stuck_smoke.results() == ()


def test_a_windows_run_sends_only_the_talkover_windows_unjudged(tmp_path: Path) -> None:
    setup = Setup(tmp_path, lambda w: (w.item("n"), w.item("t", talkover=True)))
    setup.stt = FakeSpeechToText(["open the inbox", "open"])
    assert setup.main("--windows-ms", "500", "1000") == 0
    (result,) = setup.results()
    assert (result.item, result.judged, result.right, result.answer.text) == (
        "t",
        False,
        None,
        None,
    )
    assert [(w.ms, w.text, w.reused) for w in result.answer.windows] == [
        (500, "open", False),
        (1000, "", False),  # the clip is 1 s long: sent whole, with no clip answer to reuse
    ]
    assert setup.writer.calls[0][0].windows_ms == (500, 1000)


def test_a_traced_smoke_test_files_its_span_under_the_runs_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path)
    setup.stt = FakeSpeechToText(["open the inbox"])
    endpoint = "http://127.0.0.1:6006/v1/traces"
    assert setup.main("--smoke-only", "--tracing-endpoint", endpoint, out="p1") == 0
    assert setup.tracing.spans[0] == {"span": "golden_variant", "session_id": "p1"}
    assert setup.tracing.shut and "dropped_spans=0" in capsys.readouterr().out
    (result,) = setup.results()
    assert (result.variant, result.right) == ("a-v1", True)
    info = setup.writer.calls[0][0]
    assert (info.traced, info.settings["tracing.endpoint"]) == (True, endpoint)
    assert setup.history.lines[0].variants == 1


def test_the_smoke_test_says_the_form_of_the_language_the_provider_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """R7's smoke step reads whether Groq names the language it detected by a code or a name
    (TD-011), from the smoke test's line: a label, never a transcript."""
    setup = Setup(tmp_path)
    heard = Transcript(text="zebra quartz", language="Arabic", billed_seconds=10.0)
    setup.stt = FakeSpeechToText([heard])
    assert setup.main("--language-hint", "auto", "--smoke-only") == 0
    out = capsys.readouterr().out
    (line,) = [line for line in out.splitlines() if "smoke_passed" in line]
    assert "language=Arabic" in line and "zebra" not in out
    assert setup.calls() == 1 and setup.stt.calls[0][1] is None
