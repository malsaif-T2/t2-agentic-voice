"""Fixtures for the harness's own tests.

ARCH-DEPS (scripts/arch_deps.py) maps each module to the distributions that install it through
`importlib.metadata.packages_distributions`, which reads every installed distribution's files:
seconds on Windows, for each of the many tests here that run the architecture check on a small
project. The installed environment cannot change during a run, so the first test's reading is
kept and handed to the others, the same mapping the check would read again."""

from __future__ import annotations

import functools
import importlib.metadata
from collections.abc import Mapping

import pytest

_READ = importlib.metadata.packages_distributions


@functools.cache
def _installed() -> Mapping[str, list[str]]:
    return _READ()


@pytest.fixture(autouse=True)
def _installed_distributions_read_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """`packages_distributions` answers from the session's first reading, in this test only."""
    monkeypatch.setattr(importlib.metadata, "packages_distributions", _installed)
