"""The gate of run H's Scribe `detected` arm (D-115; scribe_arm_run.py): which variants also send
the request naming no language, as a live call under `stt.live_language = "detected"` sends it
only for a turn of `stt.detect_from_s` seconds of voiced speech or more.

The gate is an offline `poe eval-languages --classifier detected` pass (`--language-from`): free,
complete, at the arm's commit, on its split and data (language_arms.py's `language_pass`), each of
its turns recording whether the file-fed pipeline's bridge sent it naming no language too
(`detects`). A variant is sent whole, so it detects when its first turn does, as run H's Whisper
arm reads the same pass (detect_arm.py); a variant with no turn does not. The voiced-speech gate
does not depend on the language a call is held in, so the pass, held in Arabic, gates both calls.
Each refusal comes before anything is sent and names no variant.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from t2_agentic_voice.evals import run_refused

from ole5_voice.evals.language_arms import language_pass
from ole5_voice.evals.run_parts import Todo


@dataclass(frozen=True)
class Gate:
    """The gate's pass by name, and whether each variant, by item and variant, detects."""

    name: str
    detects: Mapping[tuple[str, str], bool]

    def of(self, todo: Todo) -> bool:
        """Whether `todo`'s variant detects."""
        return self.detects[(todo.item.id, todo.variant.id)]

    def shown(self, todo: Sequence[Todo]) -> str:
        """What the pass records of the gate over `todo`."""
        sent = sum(self.of(each) for each in todo)
        return f"{self.name} (detected), {sent} of {len(todo)} variants sent naming no language"


def detect_gate(path: Path, todo: Sequence[Todo], *, split: str, commit: str, digest: str) -> Gate:
    """The gate `path`'s pass gives `todo` (the module's docstring), or the run's refusal."""
    found, results = language_pass(path, split, commit, digest)
    if found.run.classifier != "detected":
        raise run_refused(
            "the --language-from pass is not a detected pass: its turns record no gate",
            "give a complete --classifier detected pass of H1, at this commit",
        )
    by_variant = {(r.item, r.variant): bool(r.turns and r.turns[0].detects) for r in results}
    if any((each.item.id, each.variant.id) not in by_variant for each in todo):
        raise run_refused(
            "the --language-from pass did not feed every variant of the run",
            "give a complete pass of the run's split, at this commit",
        )
    return Gate(name=found.run.name, detects=by_variant)
