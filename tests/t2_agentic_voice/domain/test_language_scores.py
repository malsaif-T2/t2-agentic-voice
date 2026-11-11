"""A classifier's answer parsed at the port (domain/ports/language_classifier.py; plan 007's Block
H; docs/SECURITY.md, invariant 4). Adversarial (GP-08): a share of NaN, -0.1 or 1.2, shares
summing to 0.9, a code not asked, a code missing and an empty answer are each refused at the
port as a failure, and the turn keeps its language; an answer that is not the port's type is a
failure too; and a classifier sure of a third language still chooses only between the agent's,
its low `mass` recorded. Every share here is made up for the test."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.domain.ports.language_classifier import LanguageScores, scores_for
from t2_agentic_voice.domain.turn_language import LanguageRule, choose_language

AMONG = ("ar", "en")
RULE = LanguageRule(from_s=2.0, min_share=0.7)


@pytest.mark.parametrize(
    "shares",
    [
        {"ar": math.nan, "en": 0.5},
        {"ar": -0.1, "en": 1.1},
        {"ar": 1.2, "en": -0.2},
        {"ar": 0.45, "en": 0.45},  # sums to 0.9
        {"ar": 0.5, "en": 0.4, "fr": 0.1},  # a code not asked
        {"ar": 1.0},  # a code missing
        {},  # an empty answer
        {"ar": math.inf, "en": 0.0},
        {"ar": "0.5", "en": "0.5"},
    ],
)
def test_an_answer_that_does_not_parse_is_a_failure_and_the_turn_keeps_its_language(
    shares: dict[str, object],
) -> None:
    with pytest.raises(ProviderError) as refused:
        LanguageScores.parsed(shares, among=AMONG, mass=0.9)
    assert refused.value.kind == "server_error" and not refused.value.retryable
    assert choose_language("ar", "failed", speech_s=3.0, rule=RULE).language == "ar"


@pytest.mark.parametrize("mass", [math.nan, -0.01, 1.01, "high", None])
def test_a_mass_outside_0_to_1_is_refused(mass: object) -> None:
    with pytest.raises(ProviderError):
        LanguageScores.parsed({"ar": 0.5, "en": 0.5}, among=AMONG, mass=mass)


def test_the_model_itself_refuses_shares_that_do_not_sum_to_one() -> None:
    with pytest.raises(ValidationError):
        LanguageScores(shares={"ar": 0.2, "en": 0.2}, mass=0.5)
    with pytest.raises(ValidationError):
        LanguageScores(shares={}, mass=0.5)


def test_a_good_answer_parses_with_its_best_code() -> None:
    scores = LanguageScores.parsed({"ar": 0.25, "en": 0.75}, among=AMONG, mass=0.98)
    assert scores.best == ("en", 0.75) and scores.mass == 0.98
    assert scores_for(scores, among=AMONG) is scores
    assert scores_for(None, among=AMONG) is None  # a busy classifier


@pytest.mark.parametrize("answer", ["en", {"ar": 0.5, "en": 0.5}, 0.9, ("en", 0.9)])
def test_an_answer_of_another_type_is_a_failure(answer: object) -> None:
    with pytest.raises(ProviderError):
        scores_for(answer, among=AMONG)


def test_scores_of_other_codes_than_those_asked_are_a_failure() -> None:
    three = LanguageScores.parsed(
        {"ar": 0.2, "en": 0.3, "fr": 0.5}, among=("ar", "en", "fr"), mass=1.0
    )
    with pytest.raises(ProviderError):
        scores_for(three, among=AMONG)


def test_a_classifier_sure_of_a_third_language_chooses_only_between_the_agents() -> None:
    """French at 0.95 of the whole output: Arabic and English hold 0.05 of it, renormalized to
    0.6 and 0.4, its low mass kept; the best share is under 0.7, so the turn stays Arabic."""
    scores = LanguageScores.renormalized({"ar": 0.03, "en": 0.02}, among=AMONG)
    assert scores.shares == pytest.approx({"ar": 0.6, "en": 0.4})
    assert scores.mass == pytest.approx(0.05)
    assert choose_language("en", scores, speech_s=3.0, rule=RULE).by == "unsure"
    assert choose_language("en", scores, speech_s=3.0, rule=RULE).language == "en"


@pytest.mark.parametrize(
    "probabilities",
    [
        {"ar": 0.0, "en": 0.0},  # no share left for the agent's codes
        {"ar": 0.7, "en": 0.6},  # more than the whole output
        {"ar": math.nan, "en": 0.1},
        {"en": 0.5},
    ],
)
def test_probabilities_that_cannot_be_renormalized_are_a_failure(
    probabilities: dict[str, float],
) -> None:
    with pytest.raises(ProviderError):
        LanguageScores.renormalized(probabilities, among=AMONG)
