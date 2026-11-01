"""A spelling guide's rulings as data: each named, quoted and dated."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError
from t2_agentic_voice.domain.text.rulings import SpellingIssue, SpellingRule

RULING = {
    "id": "product-term-outlook",
    "avoid": ["اوتلوك", "أوتلوك"],
    "write": "Outlook",
    "said": "Use these rules",
    "on": "2026-11-01",
}


def test_a_ruling_reads_from_data_as_a_team_writes_it() -> None:
    rule = SpellingRule.model_validate(RULING)
    assert (rule.avoid, rule.on) == (("اوتلوك", "أوتلوك"), date(2026, 11, 1))
    issue = SpellingIssue(rule=rule.id, found=rule.avoid[0], write=rule.write)
    assert (issue.rule, issue.write) == ("product-term-outlook", "Outlook")


@pytest.mark.parametrize(
    "change",
    [
        {"id": "Product Term"},  # an id is a stable lower-case name
        {"avoid": []},  # a ruling avoids at least one spelling
        {"said": ""},  # and quotes who made it
        {"on": "soon"},
        {"extra": "x"},
    ],
)
def test_a_ruling_with_a_missing_or_wrong_part_is_refused(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SpellingRule.model_validate(RULING | change)
