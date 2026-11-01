"""The language parts: the canonical Arabic normalizer, digit normalization, and the check of a
team's spelling guide. Provisional (D-021). A facade: it only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.domain.text.arabic import normalize_arabic
from t2_agentic_voice.domain.text.digits import normalize_digits
from t2_agentic_voice.domain.text.rulings import SpellingIssue, SpellingRule
from t2_agentic_voice.domain.text.spelling import spelling_issues

__all__ = [
    "SpellingIssue",
    "SpellingRule",
    "normalize_arabic",
    "normalize_digits",
    "spelling_issues",
]
