"""Run K's times are the model's, never the run's pacing (talker_measure.py, the library's
paced_chat.py; Q15): a variant whose talker's model has no room in the minute waits for it before
its call, so its first token and first clause are unchanged by the wait; a request turned away
and sent again inside the call leaves the variant no time, rather than one that holds the retry's
wait.
On the library's real `TextCall`, on the system clock, the minute made short."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from ole5_voice.evals.judge import Judge
from ole5_voice.evals.kb_points import RecordingKnowledge, load_knowledge
from ole5_voice.evals.talker_measure import Measuring, Todo
from ole5_voice.evals.talker_score import VariantRecord
from t2_agentic_voice import ProviderError, VoiceSettings
from t2_agentic_voice.evals import Limits, ModelPacer, PacedChat, Price, Spend, TextCall
from t2_agentic_voice.testing import run_pacing

from tests.ole5_voice.evals.talker_fakes import JUDGE, TALKER, TOOL, FakeChat, agent
from tests.ole5_voice.evals.talker_support import item, make_setup

WINDOW_S = 1.5  # the minute, made short so the test waits for it in real time
FAST_S = WINDOW_S / 3  # a fake model that answers at once is far under it


class _Slept:
    """The system's sleep, each wait recorded."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)
        await asyncio.sleep(seconds)


def _measured(tmp_path: Path, chat: FakeChat, slept: _Slept, *, full: bool) -> VariantRecord:
    """One English variant measured through the real `TextCall`; when `full`, its talker's
    model is allowed one request a minute, and that minute's request was just sent."""
    setup = make_setup(tmp_path, [item("a1")])  # its first variant English
    limits = Limits(rpm=1 if full else 30, tpm=1_000_000, rpd=1000)
    clock = time.perf_counter
    paced = PacedChat(
        chat,
        pacers={
            model: ModelPacer(limits, used_today=0, clock=clock, sleep=slept)
            for model in (TALKER, JUDGE)
        },
        spend=Spend(prices={TALKER: Price(0.15, 0.6), JUDGE: Price(0.59, 0.79)}, cap_usd=1.0),
        input_budget=6000,
        attempts=3,
        sleep=slept,
    )
    if full:
        paced.pacers[TALKER].sent()
    knowledge = RecordingKnowledge(setup.kb)
    data = load_knowledge(setup.data, setup.points_text)
    settings = VoiceSettings.model_validate({"env": "test", "llm": {"model": TALKER}})
    measuring = Measuring(
        agent=agent(knowledge),
        paced=paced,
        settings=settings,
        knowledge=knowledge,
        data=data,
        judge=Judge(paced, model=JUDGE),
        search_tool=TOOL,
        call_language="variant",
        timeout_s=30.0,
        call=TextCall,
        clock=clock,
    )
    return asyncio.run(measuring.variant(Todo(data.items["a1"], 1), "dev"))


@pytest.fixture(autouse=True)
def _short_minute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_pacing, "WINDOW_S", WINDOW_S)


def test_a_wait_for_room_in_the_minute_is_never_in_the_variants_times(tmp_path: Path) -> None:
    slept = _Slept()
    record = _measured(tmp_path, FakeChat(), slept, full=True)
    turn = record.turn
    assert record.failure is None and turn is not None and turn.said == "a short answer"
    assert turn.first_token_s is not None and turn.first_token_s < FAST_S
    assert turn.first_clause_s is not None and turn.first_clause_s < FAST_S
    assert turn.own_first_clause_s is not None and turn.own_first_clause_s < FAST_S
    assert sum(slept.waits) >= FAST_S  # the run did wait for the minute's room


def test_a_request_turned_away_and_sent_again_leaves_the_variant_no_time(tmp_path: Path) -> None:
    """The retry's wait is the run's, inside the call: the variant is still answered and judged,
    but its times are none, so no median holds the wait."""
    chat, slept = FakeChat(), _Slept()
    chat.errors.append(ProviderError("rate_limited", True, retry_after_s=FAST_S))
    record = _measured(tmp_path, chat, slept, full=False)
    turn = record.turn
    assert record.failure is None and record.passed and turn is not None
    assert turn.said == "a short answer" and turn.model_requests == 1
    assert (turn.first_token_s, turn.first_clause_s, turn.own_first_clause_s) == (None,) * 3
    assert slept.waits == [FAST_S]  # the retry's, and no other
