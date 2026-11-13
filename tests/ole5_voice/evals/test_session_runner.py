"""What the spending runs share (session_runner.py): a refusal before anything is sent exits 2,
a library error once a run began ends it as not complete (exit 1, as run T's always did, its
card written by the caller), a bug is raised; a held-out run's library lines but its errors are
held back; what a run built is closed whenever it ends; and S's and A's even order of plays.
Each run's own tests show both exit paths end to end (test_talker_run.py, test_scenario_run.py,
test_action_run.py, test_knowledge_depth.py, test_first_audio_failures.py)."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from ole5_voice.evals import session_runner
from ole5_voice.evals.factories import Closing
from t2_agentic_voice import InvalidRequestError, T2VoiceError


@pytest.fixture
def library_level() -> Iterator[None]:
    """The library logger's level put back, which a held-out run's command lowers."""
    library = logging.getLogger("t2_agentic_voice")
    level = library.level
    yield
    library.setLevel(level)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe made-up")
    parser.add_argument("--split")
    return parser


def _main(argv: list[str], result: int | BaseException) -> int:
    def run(args: argparse.Namespace) -> int:
        if isinstance(result, BaseException):
            raise result
        return result

    return session_runner.main_of(_parser(), argv, lambda p, a: None, run, "made_up_refused")


def test_a_refusal_before_anything_is_sent_exits_2_and_a_result_is_the_runs(
    library_level: None, capsys: pytest.CaptureFixture[str]
) -> None:
    refused = InvalidRequestError("Made up. FIX: none.", details={})
    assert _main(["--split", "dev"], refused) == 2
    assert "made_up_refused" in capsys.readouterr().out
    assert _main(["--split", "dev"], 1) == 1 and _main([], 0) == 0
    assert logging.getLogger("t2_agentic_voice").level != logging.ERROR
    assert _main(["--split", "held-out"], 0) == 0
    assert logging.getLogger("t2_agentic_voice").level == logging.ERROR  # its lines held back


async def _raising(error: BaseException) -> None:
    raise error


def test_once_a_run_began_a_library_error_or_an_interrupt_ends_it_and_a_bug_is_raised() -> None:
    assert session_runner.measured(_raising(T2VoiceError("Made up.")), done=lambda: 1, of=2) == (
        "error"
    )
    assert session_runner.measured(_raising(KeyboardInterrupt()), done=lambda: 1, of=2) == (
        "interrupted"
    )
    with pytest.raises(RuntimeError, match="a bug"):
        session_runner.measured(_raising(RuntimeError("a bug")), done=lambda: 1, of=2)


class _Built:
    closed = 0

    async def aclose(self) -> None:
        self.closed += 1


def test_what_a_run_built_is_closed_whenever_it_ends() -> None:
    built = _Built()

    def refusing(closing: Closing) -> int:
        closing.add(built)
        raise InvalidRequestError("Made up. FIX: none.", details={})

    with pytest.raises(InvalidRequestError):
        session_runner.closed(refusing)
    assert built.closed == 1
    assert session_runner.closed(lambda closing: len([closing.add(built)])) == 1
    assert built.closed == 2


@dataclass(frozen=True)
class _Scenario:
    id: str


def test_every_scenario_is_played_once_before_any_is_played_again() -> None:
    a, b = _Scenario("a"), _Scenario("b")
    assert session_runner.evenly([a, b], 2, []) == [(a, 1), (b, 1), (a, 2), (b, 2)]
    assert session_runner.evenly([a, b], 2, [("a", 1), ("b", 1), ("a", 2)]) == [(b, 2)]
