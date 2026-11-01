"""The spelling-guide check: where a reference breaks a team's spelling guide.

The guide is data the team passes in (`SpellingRule`, in `rulings.py`), never a list in the
library. Built by plan 002's Track A; until then a stub. Public through the `languages` facade
(D-021).
"""

from __future__ import annotations

from collections.abc import Sequence

from t2_agentic_voice.domain.text.rulings import SpellingIssue, SpellingRule


def spelling_issues(reference: str, rules: Sequence[SpellingRule]) -> list[SpellingIssue]:
    """Every place `reference` holds a spelling one of `rules` avoids, as a whole word or
    phrase, both compared after `normalize_arabic`; empty when it follows them all. Not built
    yet."""
    raise NotImplementedError("spelling_issues is built by plan 002's Track A")
