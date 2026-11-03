"""The language parts: the canonical Arabic normalizer, digit normalization, numbers and IDs said
in words, the clause splitter, the text a text-to-speech provider is sent for a phrase (the
characters no one sees made a space or dropped), the pronunciation map (`VoiceAgent.pronounce`'s
type, and the function that applies one), and the check of a team's spelling guide. Provisional
(D-021). A facade: it only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.domain.text.arabic import normalize_arabic
from t2_agentic_voice.domain.text.clauses import split_clauses
from t2_agentic_voice.domain.text.digits import normalize_digits
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.domain.text.pronounce import Pronunciations, pronounce
from t2_agentic_voice.domain.text.rulings import SpellingIssue, SpellingRule
from t2_agentic_voice.domain.text.speaking import speak_id, speak_number
from t2_agentic_voice.domain.text.spelling import spelling_issues

__all__ = [
    "Pronunciations",
    "SpellingIssue",
    "SpellingRule",
    "normalize_arabic",
    "normalize_digits",
    "pronounce",
    "provider_text",
    "speak_id",
    "speak_number",
    "spelling_issues",
    "split_clauses",
]
