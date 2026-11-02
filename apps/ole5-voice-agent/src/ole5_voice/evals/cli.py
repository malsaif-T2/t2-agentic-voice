"""What the golden set's commands parse alike: a name (`models.Name`, one rule and one message
for every flag that takes one) and the audio roots, given as `--audio ROOT=FOLDER`, each root
once. `poe golden` and `poe record` take them as argparse types; `poe eval` refuses through its
own `refused` (`run_parts.audio_roots`).
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path

from ole5_voice.evals.models import NAME_RULE, is_name


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
