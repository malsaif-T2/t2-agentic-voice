"""The run commands' flags, parsed alike (`cli.py`): a flag a run needs is refused by argparse
when it is empty, in every command; every timeout is a number of seconds above 0, refused as it
is parsed; and a voice's price, `MODEL=USD`, has one message for every way it can be wrong."""

from __future__ import annotations

import argparse
from collections.abc import Callable

import pytest
from ole5_voice.evals import (
    action_run,
    cli,
    eot,
    first_audio,
    knowledge_depth,
    languages_run,
    overlap,
    run,
    scenario_run,
    talker_run,
    timing,
    uncertain,
)

Main = Callable[[list[str]], int]
COMMANDS: list[tuple[Main, str]] = [
    (eot.main, "a run needs"),
    (languages_run.main, "a pass needs"),
    (run.main, "a run needs"),
    (talker_run.main, "a run needs"),
    (scenario_run.main, "a run needs"),
    (action_run.main, "a run needs"),
    (knowledge_depth.main, "a run needs"),
    (first_audio.main, "a run needs"),
    (overlap.main, "a run needs"),
    (timing.main, "a run needs"),
    (uncertain.main, "a run needs"),
]
_PRICE = "give a price as MODEL=USD, per million characters"


def _error(main: Main, argv: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    """The last line argparse wrote, once it refused `argv` with exit 2."""
    with pytest.raises(SystemExit) as done:
        main(argv)
    assert done.value.code == 2
    return capsys.readouterr().err.strip().splitlines()[-1]


@pytest.mark.parametrize(("main", "needs"), COMMANDS)
def test_an_empty_note_is_a_flag_not_given_in_every_command(
    main: Main, needs: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Before, seven of the commands took `--note ""` and failed later, in the run's model."""
    error = _error(main, ["--note", ""], capsys)
    assert needs in error and "--note" in error.partition(needs)[2]


def test_an_empty_flag_a_run_needs_is_named_alone_when_the_rest_are_given() -> None:
    parser = argparse.ArgumentParser(prog="poe made-up")
    for flag in ("--arm", "--out", "--note"):
        parser.add_argument(flag)
    given = parser.parse_args(["--arm", "", "--out", "o", "--note", "why"])
    with pytest.raises(SystemExit):
        cli.require(parser, given, ("arm", "out", "note"))
    cli.require(parser, parser.parse_args(["--arm", "a", "--out", "o", "--note", "why"]), ["note"])
    assert [cli.missing(value) for value in (None, "", " ", 0, "a")] == [True, True, False] + [
        False
    ] * 2


@pytest.mark.parametrize(
    ("main", "flag"),
    [
        (overlap.main, "--timeout-s"),
        (timing.main, "--timeout-s"),
        (first_audio.main, "--timeout-s"),
        (first_audio.main, "--llm-timeout-s"),
        (uncertain.main, "--timeout-s"),
        (uncertain.main, "--item-timeout-s"),
        (run.main, "--timeout-s"),
        (talker_run.main, "--timeout-s"),
        (knowledge_depth.main, "--search-timeout-s"),
    ],
)
def test_a_timeout_of_zero_is_refused_as_it_is_parsed(
    main: Main, flag: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Before, overlap, timing, first-audio and uncertain took 0, which a run's settings read
    as the default (`args.timeout_s or ...`) or as no time at all."""
    error = _error(main, [flag, "0"], capsys)
    assert flag in error and "must be a finite number of seconds above 0" in error


@pytest.mark.parametrize("main", [timing.main, first_audio.main])
@pytest.mark.parametrize("given", ["orpheus", "=1", "orpheus=abc", "orpheus=-1", "orpheus=inf"])
def test_a_voice_price_is_refused_with_one_message(
    main: Main, given: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Before, a timing run said "invalid _price value" for a price that is no number, and
    "must be a finite number, 0 or more" for one below 0."""
    assert _PRICE in _error(main, ["--tts-price", given], capsys)


def test_a_voice_price_is_its_model_and_its_amount() -> None:
    assert cli.model_price("canopylabs/orpheus-v1-english=22.5") == (
        "canopylabs/orpheus-v1-english",
        22.5,
    )
    assert cli.model_price("m=0") == ("m", 0.0)
    for bad in ("m=nan", "m=1e400", "m=-0.5"):
        with pytest.raises(argparse.ArgumentTypeError, match=_PRICE):
            cli.model_price(bad)
