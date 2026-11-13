"""What the golden set's commands parse alike, so each rule has one place and one message.

- A name (`models.Name`, one rule and one message for every flag that takes one) and the audio
  roots, given as `--audio ROOT=FOLDER`, each root once. `poe golden` and `poe record` take them
  as argparse types; `poe eval` refuses through its own `refused` (`run_parts.audio_roots`).
- The numbers a run's flags take: `count` (1 or more), `amount` (a finite number, 0 or more: a
  price, a cap), `seconds` (above 0: every timeout and limit, so no 0 stands for the default),
  and `model_price`, a voice's `MODEL=USD` per million characters; and `EFFORTS`, the library's
  own choices of `llm.reasoning_effort`.
- `require`: the flags a run needs, each given and not empty, and a note with no install
  placeholder, refused by argparse (exit 2) before anything is read.
"""

from __future__ import annotations

import argparse
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Final, get_args

from t2_agentic_voice import LlmSettings

from ole5_voice.evals.models import NAME_RULE, is_name
from ole5_voice.evals.runs import holds_placeholder

EFFORTS: Final = get_args(LlmSettings.model_fields["reasoning_effort"].annotation)
_PRICE: Final = "give a price as MODEL=USD, per million characters"


def name(value: str) -> str:
    """An argparse type: `value`, when it is a name."""
    if not is_name(value):
        raise argparse.ArgumentTypeError(f"not a name, which is {NAME_RULE}")
    return value


def audio_root(value: str) -> tuple[str, Path]:
    """`ROOT=FOLDER` as the root's name and its folder, `~` expanded; ValueError saying the rule
    when it is not."""
    root, equals, folder = value.partition("=")
    if not equals or not folder:
        raise ValueError("give a root as ROOT=FOLDER, such as talkover=<its folder>")
    if not is_name(root):
        raise ValueError(f"a root's name is {NAME_RULE}")
    return root, Path(folder).expanduser()


def audio_root_type(value: str) -> tuple[str, Path]:
    """`audio_root` as an argparse type."""
    try:
        return audio_root(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def audio_roots(given: Iterable[tuple[str, Path]]) -> dict[str, Path]:
    """Each root's folder; ValueError when a root is given twice."""
    roots: dict[str, Path] = {}
    for root, folder in given:
        if root in roots:
            raise ValueError("each --audio root is given once")
        roots[root] = folder
    return roots


def count(text: str) -> int:
    """An argparse type: a whole number, 1 or more."""
    if (value := int(text)) < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


def amount(text: str) -> float:
    """An argparse type: a finite number, 0 or more."""
    if not math.isfinite(value := float(text)) or value < 0:
        raise argparse.ArgumentTypeError("must be a finite number, 0 or more")
    return value


def seconds(text: str) -> float:
    """An argparse type: a finite number of seconds above 0."""
    if not math.isfinite(value := float(text)) or value <= 0:
        raise argparse.ArgumentTypeError("must be a finite number of seconds above 0")
    return value


def model_price(text: str) -> tuple[str, float]:
    """An argparse type: a voice's price, `MODEL=USD` per million characters, one message for
    every way it can be wrong."""
    model, equals, given = text.partition("=")
    try:
        value = float(given)
    except ValueError:
        value = -1.0
    if not equals or not model or not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError(_PRICE)
    return model, value


def missing(value: object) -> bool:
    """Whether a flag's value counts as not given: none, or empty text."""
    return value is None or value == ""


def require(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    named: Iterable[str],
    *,
    noun: str = "run",
) -> None:
    """Refused by argparse (exit 2): a `named` flag not given or given empty, saying every one
    such ("a run needs --out, --note"; a `noun` other than a run's names its own), then a note
    holding an install placeholder, which the docs check refuses in the committed history."""
    if lacking := [f"--{each.replace('_', '-')}" for each in named if missing(getattr(args, each))]:
        parser.error(f"a {noun} needs {', '.join(lacking)}")
    note = getattr(args, "note", None)
    if note is not None and holds_placeholder(note):
        parser.error("--note holds an install placeholder, which the docs check refuses")
