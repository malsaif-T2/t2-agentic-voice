"""The warm-up at the server's start (voice/calls_start.py, voice/spare.py; TD-089): what
`VoiceCalls.start` imports and makes, by default and under `warmup.at_start`, with the fakes'
detectors (kit.py) and a local aiortc peer as the browser, and `Spare` on its own."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.logging import FIELDS
from t2_agentic_voice.core.settings.warmup import WarmupSettings
from t2_agentic_voice.voice import calls_start
from t2_agentic_voice.voice.calls import VoiceCalls
from t2_agentic_voice.voice.spare import Spare

from tests.t2_agentic_voice.session_fakes import AGENT
from tests.t2_agentic_voice.voice.kit import Built, ToneVAD, client_offer, until, voice_calls

CALLER, CONSENT = Caller(subject="made-up"), Consent(version=None, record_audio=False)
ENGLISH = AGENT.languages[0]


class _Imports:
    """`import_call_modules` as a test sees it: each run's thread, and nothing imported."""

    def __init__(self) -> None:
        self.threads: list[int] = []

    def __call__(self) -> None:
        self.threads.append(threading.get_ident())


def _counted(settings: VoiceSettings) -> tuple[Built, list[ToneVAD]]:
    made: list[ToneVAD] = []

    def detector() -> ToneVAD:
        made.append(ToneVAD())
        return made[-1]

    return voice_calls(settings, speech_detector=detector), made


def _run(built: Built, body: Callable[[VoiceCalls], Awaitable[None]]) -> None:
    async def run() -> None:
        await built.calls.start()
        try:
            await body(built.calls)
        finally:
            await built.calls.aclose()

    # The loop serve() gives uvicorn (test_calls.py says why).
    asyncio.run(asyncio.wait_for(run(), timeout=60), loop_factory=asyncio.SelectorEventLoop)


async def _one_call(calls: VoiceCalls) -> None:
    peer, _, offer = await client_offer()
    try:
        await calls.answer("call-1", offer, caller=CALLER, consent=CONSENT, language=ENGLISH)
        await asyncio.sleep(0.2)  # time for a background make, were one started
    finally:
        await peer.close()


def test_the_warm_up_is_off_by_default_and_the_start_runs_as_before(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GP-18's characterization of the default: `warmup.at_start` off, the start imports no
    offer module and makes one pair of detectors it keeps none of, and a call's offer makes its
    own pair, with none made in the background."""
    assert WarmupSettings().at_start is False and settings.warmup.at_start is False
    imports = _Imports()
    monkeypatch.setattr(calls_start, "import_call_modules", imports)
    built, made = _counted(settings)
    started: list[int] = []

    async def body(calls: VoiceCalls) -> None:
        started.append(len(made))
        await _one_call(calls)

    _run(built, body)
    assert imports.threads == []
    assert started == [1] and len(made) == 2 and len(built.analyzers) == 2


def test_at_start_the_offer_modules_are_imported_off_the_loop_and_the_detectors_made_once(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Under `warmup.at_start` the start imports the offer's modules once, in a thread, and
    makes one pair of detectors, which the first call takes; the next pair is made in the
    background as it does, and no more. The start's log line holds its times alone."""
    on = settings.model_copy(update={"warmup": WarmupSettings(at_start=True)})
    imports = _Imports()
    monkeypatch.setattr(calls_start, "import_call_modules", imports)
    caplog.set_level(logging.INFO)
    built, made = _counted(on)
    loop_threads: list[int] = []
    started: list[int] = []

    async def body(calls: VoiceCalls) -> None:
        loop_threads.append(threading.get_ident())
        started.append(len(made))
        await _one_call(calls)
        await until(lambda: len(made) == 2)

    _run(built, body)
    assert len(imports.threads) == 1 and imports.threads[0] not in loop_threads
    assert started == [1] and len(made) == 2 and len(built.analyzers) == 2
    (warmed,) = [r for r in caplog.records if r.getMessage() == "calls_warmed"]
    fields = getattr(warmed, FIELDS)
    assert set(fields) == {"at_start", "import_ms", "detectors_ms"} and fields["at_start"] is True


def test_a_spare_hands_over_what_it_holds_and_makes_the_next_in_the_background() -> None:
    made: list[int] = []

    def make() -> int:
        made.append(len(made))
        return made[-1]

    async def run() -> None:
        spare = Spare(make)
        await spare.fill()
        assert await spare.take() == 0  # the one filled
        await until(lambda: len(made) == 2)
        assert await spare.take() == 1  # the one made in the background
        await spare.aclose()

    asyncio.run(run())


def test_a_spare_made_none_ahead_makes_one_for_each_take() -> None:
    made: list[int] = []

    def make() -> int:
        made.append(len(made))
        return made[-1]

    async def run() -> None:
        spare = Spare(make, ahead=False)
        await spare.fill()
        assert await spare.take() == 1 and await spare.take() == 2
        await asyncio.sleep(0.05)
        assert made == [0, 1, 2]

    asyncio.run(run())


def test_a_failed_background_make_is_logged_and_the_next_take_raises_its_own(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A background make that fails is logged by its type alone, and the next take makes its
    own, whose error reaches the caller."""
    caplog.set_level(logging.INFO)
    failing = [False]

    def make() -> str:
        if failing[0]:
            raise RuntimeError("secret detail")
        return "pair"

    async def run() -> None:
        spare = Spare(make)
        await spare.fill()
        failing[0] = True
        assert await spare.take() == "pair"
        await until(lambda: any(r.getMessage() == "spare_not_made" for r in caplog.records))
        with pytest.raises(RuntimeError):
            await spare.take()
        await spare.aclose()

    asyncio.run(run())
    (line,) = [r for r in caplog.records if r.getMessage() == "spare_not_made"]
    assert getattr(line, FIELDS) == {"error": "RuntimeError"}
    assert "secret detail" not in caplog.text


def test_a_closed_spare_keeps_nothing_made_after() -> None:
    release = threading.Event()

    def make() -> str:
        release.wait(5)
        return "pair"

    async def run() -> None:
        spare = Spare(make)
        release.set()
        await spare.fill()
        release.clear()
        assert await spare.take() == "pair"  # the next one's make now waits
        await spare.aclose()
        release.set()
        await asyncio.sleep(0.05)
        assert spare._held is None

    asyncio.run(run())
