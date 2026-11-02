"""The answerers: `reference`, and `groq` against the fake `SpeechToText` (no request leaves the
process): its pacing, its retries and their pauses, provider failures, a stuck variant, the cap,
the windows, tracing, and that no line it logs holds a transcript."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from ole5_voice.evals import answerers
from ole5_voice.evals.answerers import (
    Budget,
    CapReachedError,
    GroqAnswerer,
    Policy,
    ReferenceAnswerer,
    make_answerer,
)
from ole5_voice.evals.models import Variant
from ole5_voice.evals.runs import Answer, AnswerRequest
from ole5_voice.evals.windows import measurer
from t2_agentic_voice import ProviderError, Settings
from t2_agentic_voice.ports import Transcript

from tests.ole5_voice.evals.fakes import (
    FakeMatcher,
    FakeSpeechToText,
    FakeTracing,
    fake_normalize,
)
from tests.ole5_voice.evals.test_run_parts import FakeClock, World, make_world

MEASURE = measurer(fake_normalize, FakeMatcher().is_right)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return make_world(tmp_path)


def _groq(
    settings: Settings,
    script: list[str | Transcript | ProviderError],
    *,
    budget: Budget | None = None,
    policy: Policy | None = None,
    delay_s: float = 0.0,
    real_sleep: bool = False,
    reuse: dict[Variant, str] | None = None,
    tracing: FakeTracing | None = None,
    run_name: str = "run",
) -> tuple[GroqAnswerer, FakeSpeechToText, FakeClock]:
    clock = FakeClock()
    stt = FakeSpeechToText(script, delay_s=delay_s)
    answerer = make_answerer(
        "groq",
        settings,
        stt=stt,
        policy=policy,
        budget=budget,
        measure=MEASURE,
        reuse=reuse,
        tracing=tracing,
        run_name=run_name,
        clock=clock,
        sleep=asyncio.sleep if real_sleep else clock.sleep,
    )
    assert isinstance(answerer, GroqAnswerer)
    return answerer, stt, clock


def _ask(
    answerer: answerers.RunAnswerer,
    variant: Variant,
    segments: tuple[Path, ...],
    windows_ms: tuple[int, ...] = (),
) -> Answer:
    request = AnswerRequest(segments=segments, language="en", windows_ms=windows_ms)
    return asyncio.run(answerer.answer(variant, request))


def _one(world: World, seconds: float = 1.0, segments: int = 1) -> tuple[Variant, tuple[Path, ...]]:
    variant = world.item("a", segments=segments, seconds=seconds).variants[0]
    return variant, tuple(world.audio / ref.path for ref in variant.segments)


def test_the_reference_answerer_gives_each_variant_its_reference_and_sends_nothing(
    world: World, settings: Settings
) -> None:
    variant, paths = _one(world)
    answerer = make_answerer("reference", settings, measure=MEASURE)
    assert (answerer.spends, answerer.needs_audio, answerer.name) == (False, False, "reference")
    assert _ask(answerer, variant, (Path("never/read.wav"),)) == Answer(
        variant="a-v1", text="open the inbox"
    )
    windows = _ask(answerer, variant, paths, windows_ms=(500,)).windows
    assert [(w.ms, w.text, w.leading_words) for w in windows] == [(500, "open the inbox", 3)]
    with pytest.raises(ValueError, match="needs a Measure"):
        _ask(ReferenceAnswerer(), variant, paths, windows_ms=(500,))
    asyncio.run(answerer.aclose())


def test_groq_sends_each_clip_once_in_the_hinted_language_with_no_prompt(
    world: World, settings: Settings
) -> None:
    variant, paths = _one(world, seconds=12.5)
    heard = Transcript(text=" open the inbox ", language="en", confidence=-0.2, no_speech_prob=0.1)
    answerer, stt, _ = _groq(settings, [heard])
    answer = _ask(answerer, variant, paths)
    assert (answer.text, answer.language, answer.confidence, answer.no_speech_prob) == (
        "open the inbox",
        "en",
        -0.2,
        0.1,
    )
    assert [(r.attempt, r.outcome, r.billed_seconds) for r in answer.requests] == [(1, "ok", 12.5)]
    clip, language, prompt = stt.calls[0]
    assert (clip.seconds, language, prompt) == (12.5, "en", None)
    assert answerer.spends and answerer.needs_audio


def test_a_take_of_two_segments_is_one_answer_weighted_by_length(
    world: World, settings: Settings
) -> None:
    variant = world.item("t", segments=1, seconds=1.0).variants[0]
    long = world.item("u", segments=1, seconds=3.0).variants[0]
    paths = (world.audio / variant.segments[0].path, world.audio / long.segments[0].path)
    first = Transcript(text="open the", language="en", confidence=-1.0, no_speech_prob=0.4)
    second = Transcript(text="inbox", language="ar", confidence=-0.2, no_speech_prob=None)
    answerer, _, _ = _groq(settings, [first, second])
    answer = _ask(answerer, variant, paths)
    assert (answer.text, answer.language) == ("open the inbox", "ar")  # the longer one's
    assert answer.confidence == pytest.approx((1 * -1.0 + 3 * -0.2) / 4)
    assert answer.no_speech_prob == pytest.approx(0.4)  # only the segment that gave one
    assert [s.text for s in answer.segments] == ["open the", "inbox"]
    assert [r.segment for r in answer.requests] == [0, 1]


@pytest.mark.parametrize(
    ("error", "pause"),
    [
        (ProviderError("rate_limited", True, 30.0), 30.0),  # the provider's own delay
        (ProviderError("rate_limited", True, 5.0), 20.0),  # never under 20 s
        (ProviderError("rate_limited", True), 20.0),
        (ProviderError("server_error", True), 3.0),
        (ProviderError("connection_lost", True), 3.0),
    ],
)
def test_a_request_turned_away_is_asked_again_after_a_pause(
    world: World, settings: Settings, error: ProviderError, pause: float
) -> None:
    variant, paths = _one(world)
    answerer, stt, clock = _groq(settings, [error, "open the inbox"])
    answer = _ask(answerer, variant, paths)
    assert answer.text == "open the inbox" and answer.failure is None
    assert [(r.attempt, r.outcome) for r in answer.requests] == [(1, error.kind), (2, "ok")]
    assert clock.pauses[0] == pause and len(stt.calls) == 2


def test_a_refusal_no_retry_mends_and_the_last_attempt_are_provider_failures(
    world: World, settings: Settings
) -> None:
    variant, paths = _one(world)
    answerer, stt, _ = _groq(settings, [ProviderError("rejected", False)])
    answer = _ask(answerer, variant, paths)
    assert (answer.failure, answer.text, len(stt.calls)) == ("provider", None, 1)
    timeouts: list[str | Transcript | ProviderError] = [ProviderError("timeout", True)] * 5
    answerer, stt, clock = _groq(settings, timeouts, policy=Policy(max_attempts=4))
    answer = _ask(answerer, variant, paths)
    assert answer.failure == "provider" and [r.attempt for r in answer.requests] == [1, 2, 3, 4]
    assert clock.pauses.count(3.0) == 3 and len(stt.calls) == 4


def test_a_variant_still_running_at_its_limit_is_stuck(world: World, settings: Settings) -> None:
    variant, paths = _one(world)
    answerer, _, _ = _groq(settings, ["late"], policy=Policy(variant_timeout_s=0.05), delay_s=10.0)
    answer = _ask(answerer, variant, paths)
    assert (answer.failure, answer.text) == ("stuck", None)
    assert [(r.outcome, r.billed_seconds) for r in answer.requests] == [("stuck", 10.0)]
    # Stuck in a pause after a rate limit: no request in flight.
    answerer, _, _ = _groq(
        settings,
        [ProviderError("rate_limited", True)],
        policy=Policy(variant_timeout_s=0.05),
        real_sleep=True,
    )
    answer = _ask(answerer, variant, paths)
    assert answer.failure == "stuck"
    assert [r.outcome for r in answer.requests] == ["rate_limited"]


def test_a_request_that_would_pass_the_cap_is_never_sent(world: World, settings: Settings) -> None:
    variant, paths = _one(world)
    budget = Budget(price_per_hour_usd=3600.0, cap_usd=25.0)  # a request of 10 s costs $10
    answerer, stt, _ = _groq(settings, ["a", "b", "c"], budget=budget)
    for _ in range(2):
        _ask(answerer, variant, paths)
    with pytest.raises(CapReachedError):
        _ask(answerer, variant, paths)
    assert (len(stt.calls), budget.requests, budget.billed_seconds, budget.cost_usd) == (
        2,
        2,
        20.0,
        20.0,
    )


def test_requests_start_no_closer_than_max_rpm_allows(world: World, settings: Settings) -> None:
    variant, paths = _one(world)
    answerer, _, clock = _groq(settings, ["a", "b", "c"], policy=Policy(max_rpm=20))
    _ask(answerer, variant, paths)
    assert clock.pauses == []
    clock.now += 1.0  # a second later: two more seconds to the next start
    _ask(answerer, variant, paths)
    clock.now += 5.0
    _ask(answerer, variant, paths)
    assert clock.pauses == [pytest.approx(2.0)]


def test_windows_are_cut_from_the_first_segment_and_one_as_long_as_its_clip_reused(
    world: World, settings: Settings
) -> None:
    variant, paths = _one(world, seconds=1.0)
    answerer, stt, _ = _groq(settings, ["open", "open the"], reuse={variant: "open the inbox"})
    answer = _ask(answerer, variant, paths, windows_ms=(500, 750, 1000))
    assert answer.text is None and answer.failure is None
    assert [(w.ms, w.text, w.leading_words, w.reused) for w in answer.windows] == [
        (500, "open", 1, False),
        (750, "open the", 2, False),
        (1000, "open the inbox", 3, True),  # not sent again
    ]
    assert [clip.seconds for clip, _, _ in stt.calls] == [0.5, 0.75]
    answerer, stt, _ = _groq(settings, ["open the inbox", ProviderError("rejected", False)])
    answer = _ask(answerer, variant, paths, windows_ms=(1000, 1500))
    assert [clip.seconds for clip, _, _ in stt.calls] == [1.0, 1.0]  # no answer to reuse: sent
    assert answer.failure == "provider"
    answerer = GroqAnswerer(
        FakeSpeechToText(),
        model="whisper-large-v3",
        policy=Policy(),
        budget=Budget(price_per_hour_usd=0.0),
        measure=None,
        reuse={},
        tracing=None,
        run_name="r1",
        clock=FakeClock(),
        sleep=FakeClock().sleep,
    )
    with pytest.raises(ValueError, match="needs a Measure"):
        _ask(answerer, variant, paths, windows_ms=(500,))


def test_a_traced_request_is_a_speech_to_text_span_under_the_variants_root(
    world: World, settings: Settings
) -> None:
    variant, paths = _one(world)
    tracing = FakeTracing()
    answerer, _, _ = _groq(settings, ["open the inbox"], tracing=tracing, run_name="p1")
    _ask(answerer, variant, paths)
    root, span = tracing.spans
    assert root == {"span": "golden_variant", "session_id": "p1"}
    assert (span["model"], span["language_sent"], span["audio_seconds"]) == (
        "whisper-large-v3",
        "en",
        1.0,
    )
    assert (span["text"], span["billed_seconds"]) == ("open the inbox", 10.0)


def test_no_line_the_answerer_logs_holds_a_transcript_or_a_variant(
    world: World, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    variant, paths = _one(world)
    script: list[str | Transcript | ProviderError] = [
        ProviderError("rate_limited", True, 1.0),
        "zebra quartz marmalade",
        ProviderError("rejected", False),
    ]
    answerer, _, _ = _groq(settings, script)
    _ask(answerer, variant, paths)
    _ask(answerer, variant, paths)
    out = capsys.readouterr().out
    assert "request_refused" in out and "provider_failure" in out and "pause_s=20.0" in out
    assert "zebra" not in out and "a-v1" not in out and "open the inbox" not in out


def test_closing_the_groq_answerer_closes_an_adapter_that_can_close(settings: Settings) -> None:
    class Closing(FakeSpeechToText):
        closed = False

        async def aclose(self) -> None:
            self.closed = True

    stt = Closing()
    asyncio.run(make_answerer("groq", settings, stt=stt).aclose())
    asyncio.run(make_answerer("groq", settings, stt=FakeSpeechToText()).aclose())
    assert stt.closed


def test_the_adapter_is_the_one_stt_provider_names(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeSpeechToText()
    monkeypatch.setattr(answerers, "_ADAPTERS", {"groq": lambda given: fake})
    assert answerers.adapter(settings) is fake
    made = make_answerer("groq", settings)
    assert isinstance(made, GroqAnswerer) and made._stt is fake
    with pytest.raises(ValueError, match="no answerer is called 'whisper'; one of reference, groq"):
        make_answerer("whisper", settings)


def test_the_budget_counts_billed_seconds_at_the_price(settings: Settings) -> None:
    budget = Budget(price_per_hour_usd=0.111)
    budget.charge(10.0)
    budget.charge(7200.0)
    assert (budget.requests, budget.billed_seconds) == (2, 7210.0)
    assert budget.cost_usd == pytest.approx(7210 / 3600 * 0.111)
    assert answerers.GROQ_MINIMUM_S == 10.0
