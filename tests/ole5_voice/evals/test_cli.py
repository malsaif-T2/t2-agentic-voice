"""What the golden set's commands parse alike (`cli.py`): a name, with the one message that states
its whole rule, and `--audio ROOT=FOLDER`, each root once and its folder's `~` expanded, in
`poe golden`, `poe record` and `poe eval` alike (plan 004, app4 and app5)."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from ole5_voice.evals import cli, golden, import_recordings, recorder
from ole5_voice.evals.models import NAME_RULE, is_name

LONGEST = "a" * 128


def test_a_name_is_a_lowercase_letter_or_digit_then_up_to_127_more() -> None:
    assert [is_name(text) for text in ("r1-large-v3", "0.a_b", LONGEST)] == [True] * 3
    for text in ("", "R1", "-r1", ".r1", "r 1", "r/1", LONGEST + "a"):
        assert not is_name(text), text
        with pytest.raises(argparse.ArgumentTypeError, match="not a name, which is a lowercase"):
            cli.name(text)
    assert "127" in NAME_RULE and "'_', '.' or '-'" in NAME_RULE


def test_an_audio_root_is_a_name_and_a_folder() -> None:
    assert cli.audio_root("talkover=~/lab") == ("talkover", Path("~/lab").expanduser())
    for value, problem in (
        ("talkover", "ROOT=FOLDER"),
        ("talkover=", "ROOT=FOLDER"),
        ("=x", "a root's name is a lowercase"),
        ("Talkover=x", "a root's name is a lowercase"),
    ):
        with pytest.raises(ValueError, match=problem):
            cli.audio_root(value)
        with pytest.raises(argparse.ArgumentTypeError, match=problem):
            cli.audio_root_type(value)
    assert cli.audio_roots([("a", Path("x")), ("b", Path("y"))]) == {"a": Path("x"), "b": Path("y")}
    with pytest.raises(ValueError, match="each --audio root is given once"):
        cli.audio_roots([("a", Path("x")), ("a", Path("y"))])


@pytest.mark.parametrize(
    ("command", "argv", "problem"),
    [
        (golden.main, ["--audio", "Talkover=x"], "a root's name is"),
        (golden.main, ["--audio", "a=x", "--audio", "a=y"], "each --audio root is given once"),
        (recorder.main, ["--out", "o", "--audio", "talkover"], "ROOT=FOLDER"),
        (recorder.main, ["--out", "o", "--audio", "a=x", "--audio", "a=y"], "given once"),
        (recorder.main, ["--out", "o", "--session", "Laptop"], "not a name, which is"),
        (import_recordings.main, ["--takes", "t", "--root", "Owner"], "not a name, which is"),
    ],
)
def test_each_command_refuses_a_name_or_a_root_with_the_same_words(
    command: object, argv: list[str], problem: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert callable(command)
    with pytest.raises(SystemExit) as done:
        command(argv)
    assert done.value.code == 2 and problem in capsys.readouterr().err
