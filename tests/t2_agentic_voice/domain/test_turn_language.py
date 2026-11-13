"""The rule that picks the language each turn is sent to speech-to-text in (domain/turn_language.py;
D-086, plan 007's Q17 and Q18): in order, `short` when the turn's speech had not reached
`from_s` when its request went, then `late`, `busy`, `failed`, `unsure` (the best share under
`min_share`), else `classified`; only `classified` moves the call's current language, and under
`session` (no rule) the call's language stands whatever the verdict. Every share here is made up
for the test."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.events import LanguageBy
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.language_classifier import LanguageScores
from t2_agentic_voice.domain.turn_language import (
    LanguageChoice,
    LanguageRule,
    Verdict,
    choose_language,
    current_after,
    spoken_codes,
)

RULE = LanguageRule(from_s=2.0, min_share=0.7)
AMONG = ("ar", "en")


def _scores(en: float) -> LanguageScores:
    return LanguageScores.parsed({"ar": 1 - en, "en": en}, among=AMONG, mass=0.9)


def _choice(verdict: Verdict, speech_s: float = 3.0) -> LanguageChoice:
    return choose_language("ar", verdict, speech_s=speech_s, rule=RULE)


def test_a_turn_whose_speech_had_not_reached_from_s_is_short_whatever_the_verdict() -> None:
    for verdict in (_scores(0.99), "pending", "busy", "failed"):
        assert _choice(verdict, speech_s=1.99) == LanguageChoice(language="ar", by="short")


def test_speech_of_exactly_from_s_is_not_short() -> None:
    assert _choice(_scores(0.9), speech_s=2.0) == LanguageChoice(language="en", by="classified")


@pytest.mark.parametrize(
    ("verdict", "by"), [("pending", "late"), ("busy", "busy"), ("failed", "failed")]
)
def test_no_verdict_in_hand_keeps_the_current_language(verdict: Verdict, by: LanguageBy) -> None:
    assert _choice(verdict) == LanguageChoice(language="ar", by=by)


def test_a_best_share_under_min_share_is_unsure_and_exactly_min_share_classified() -> None:
    assert _choice(_scores(0.69)) == LanguageChoice(language="ar", by="unsure")
    assert _choice(_scores(0.7)) == LanguageChoice(language="en", by="classified")
    assert _choice(_scores(0.2)) == LanguageChoice(language="ar", by="classified")


def test_the_current_language_moves_only_on_classified() -> None:
    assert current_after("ar", LanguageChoice(language="en", by="classified")) == "en"
    for by in ("short", "late", "busy", "failed", "unsure", "overlap", "session"):
        assert current_after("ar", LanguageChoice(language="ar", by=by)) == "ar"
    after = current_after("ar", _choice(_scores(0.95)))
    assert after == "en"  # a later short turn keeps English (Q17)
    assert choose_language(after, "pending", speech_s=0.8, rule=RULE).language == "en"


def test_under_session_the_call_language_stands_whatever_the_verdict() -> None:
    for verdict in (_scores(0.99), "pending", "busy", "failed"):
        for speech_s in (0.5, 2.0, 9.0):
            found = choose_language("ar", verdict, speech_s=speech_s, rule=None)
            assert found == LanguageChoice(language="ar", by="session")
    assert choose_language(None, _scores(0.99), speech_s=9.0, rule=None).language is None


def test_the_rule_refuses_numbers_it_cannot_apply() -> None:
    for from_s, min_share in ((0.0, 0.7), (-1.0, 0.7), (2.0, 0.0), (2.0, 1.01), (2.0, -0.1)):
        with pytest.raises(ValueError, match=r"from_s|min_share"):
            LanguageRule(from_s=from_s, min_share=min_share)


def test_an_agent_speaks_each_primary_code_once_in_its_order() -> None:
    both = VoiceAgent(
        name="both",
        languages=[
            Language.saudi_arabic(greeting="hala"),
            Language.english(greeting="Hello."),
            Language.arabic(greeting="ahlan"),
        ],
    )
    one = VoiceAgent(name="one", languages=[Language.english(greeting="Hello.")])
    assert spoken_codes(both) == ("ar", "en") and spoken_codes(one) == ("en",)
