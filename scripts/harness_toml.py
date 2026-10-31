"""Reading harness.toml's tables one value at a time, for scripts/harness_config.py.

A `Table` hands out typed values and records each problem (missing key, wrong kind, unknown
key) as a HARNESS-CONFIG violation, with the line it sits on, instead of stopping at the first:
the agent then fixes the file in one pass.
"""

from __future__ import annotations

import re
from typing import Any

from scripts._common import Violation

CONFIG_FILE = "harness.toml"
RULE = "HARNESS-CONFIG"
FIX = (
    "Fix harness.toml; its comments say what each key means. Every key is required, and a "
    "key the harness does not know is an error, so a misspelt key never passes unnoticed."
)


class Lines:
    """Where a table or a key sits in the file's text, for the violation's line number."""

    def __init__(self, text: str) -> None:
        self.lines = text.splitlines()

    def of(self, table: str, key: str | None = None, index: int = 0) -> int:
        """The line of `key` in the `index`-th `[table]` or `[[table]]`; else the table's own."""
        header = re.compile(rf"^\s*\[\[?\s*{re.escape(table)}\s*\]\]?\s*(#.*)?$")
        starts = [n for n, line in enumerate(self.lines) if header.match(line)]
        if index >= len(starts):
            return 1
        start = starts[index]
        if key is not None:
            assignment = re.compile(rf"^\s*{re.escape(key)}\s*=")
            for n in range(start + 1, len(self.lines)):
                if self.lines[n].lstrip().startswith("["):
                    break
                if assignment.match(self.lines[n]):
                    return n + 1
        return start + 1


class Table:
    """One table of the file. `name` is how violations show it: `docs`, `owners` (2nd)."""

    def __init__(
        self,
        name: str,
        data: object,
        lines: Lines,
        problems: list[Violation],
        index: int = 0,
    ) -> None:
        self.name = name
        self.index = index
        self.lines = lines
        self.problems = problems
        self.data: dict[str, Any] = data if isinstance(data, dict) else {}
        self.seen: set[str] = set()
        if not isinstance(data, dict):
            self.problem(None, f"[{name}] is missing or is not a table")

    def problem(self, key: str | None, text: str) -> None:
        line = self.lines.of(self.name, key, self.index)
        self.problems.append(Violation(CONFIG_FILE, line, RULE, text, FIX))

    def _value(self, key: str) -> object:
        self.seen.add(key)
        if key not in self.data:
            self.problem(None, f"[{self.name}] needs `{key}`")
            return None
        return self.data[key]

    def string(self, key: str, *, empty: bool = False) -> str:
        value = self._value(key)
        if key in self.data and (not isinstance(value, str) or (not empty and not value)):
            self.problem(key, f"[{self.name}] {key} must be a non-empty string")
        return value if isinstance(value, str) else ""

    def integer(self, key: str, *, minimum: int = 1) -> int:
        value = self._value(key)
        valid = isinstance(value, int) and not isinstance(value, bool) and value >= minimum
        if key in self.data and not valid:
            self.problem(key, f"[{self.name}] {key} must be a whole number of at least {minimum}")
        return value if isinstance(value, int) and valid else minimum

    def number(self, key: str) -> float:
        value = self._value(key)
        valid = isinstance(value, int | float) and not isinstance(value, bool) and value > 0
        if key in self.data and not valid:
            self.problem(key, f"[{self.name}] {key} must be a number above 0")
        return float(value) if isinstance(value, int | float) and valid else 1.0

    def strings(
        self, key: str, *, non_empty: bool = False, blank_items: bool = False
    ) -> tuple[str, ...]:
        value = self._value(key)
        valid = isinstance(value, list) and all(
            isinstance(v, str) and (v or blank_items) for v in value
        )
        if key in self.data and (not valid or (non_empty and not value)):
            kind = "a non-empty list" if non_empty else "a list"
            items = "strings" if blank_items else "non-empty strings"
            self.problem(key, f"[{self.name}] {key} must be {kind} of {items}")
        return tuple(value) if isinstance(value, list) and valid else ()

    def table(self, key: str) -> Table:
        self.seen.add(key)
        return Table(f"{self.name}.{key}", self.data.get(key), self.lines, self.problems)

    def finish(self) -> None:
        """Report every key this table holds that nothing read."""
        for key in sorted(set(self.data) - self.seen):
            self.problem(key, f"[{self.name}] has an unknown key `{key}`")


def tables(data: dict[str, Any], key: str, lines: Lines, problems: list[Violation]) -> list[Table]:
    """An optional array of tables (`[[key]]`): none when the file has no such table."""
    value = data.get(key, [])
    if not isinstance(value, list):
        problems.append(
            Violation(CONFIG_FILE, lines.of(key), RULE, f"`{key}` must be [[{key}]] tables", FIX)
        )
        return []
    return [Table(key, item, lines, problems, index=i) for i, item in enumerate(value)]
