"""The library's lines for an action that leaves them out (domain/action_lines.py's
`default_action_lines`): every field in every preset's language, short, generic to any action,
for the ear only, and none a claim that the action was done, the sending line least of all (the
owner's ruling, plan 007)."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import primary_code
from t2_agentic_voice.domain.action_lines import ActionLines, default_action_lines
from t2_agentic_voice.domain.claims import check_claims, default_claims
from t2_agentic_voice.domain.presets import ACTION_LINES
from t2_agentic_voice.domain.text.words import holds_words
from t2_agentic_voice.domain.words import rule_form

TAGS: tuple[LanguageTag, ...] = ("ar-SA", "ar", "en")
# What a caller who only hears the agent cannot use (D-075): a screen, a card, a page, a button.
SEEN = ("screen", "card", "page", "button", "click", "الشاشه", "بطاقه", "الصفحه", "زر", "اضغط")


@pytest.mark.parametrize("tag", TAGS)
def test_every_line_is_given_in_every_presets_language(tag: LanguageTag) -> None:
    lines = default_action_lines(tag)
    assert set(ACTION_LINES[tag]) == set(ActionLines.model_fields)
    assert all(getattr(lines, field) == text for field, text in ACTION_LINES[tag].items())


def test_the_saudi_and_the_msa_lines_differ_in_register() -> None:
    saudi, msa = default_action_lines("ar-SA"), default_action_lines("ar")
    assert all(getattr(saudi, f) != getattr(msa, f) for f in ActionLines.model_fields)
    assert default_action_lines("en").sending == "Sending it now, just a few seconds."


@pytest.mark.parametrize("tag", TAGS)
def test_no_line_claims_the_action_was_done(tag: LanguageTag) -> None:
    """The guard never checks a template, but no default line would pass its claim rule with
    no record either: the sending line is progress, never "done"."""
    code = primary_code(tag)
    for field, text in ACTION_LINES[tag].items():
        verdict = check_claims(
            text,
            claims={},
            any_action=default_claims(code),
            evidence=(),
            settings=GuardSettings(),
            year=2026,
        )
        assert verdict.passed and verdict.claimed == (), field


@pytest.mark.parametrize("tag", TAGS)
def test_each_line_is_short_and_for_the_ear(tag: LanguageTag) -> None:
    for field, text in ACTION_LINES[tag].items():
        said = rule_form(text)
        assert len(said.split()) <= 16, field
        assert not [word for word in SEEN if holds_words(said, rule_form(word))], field
        assert not any(mark in text for mark in "{}0123456789"), field  # no value, no number
