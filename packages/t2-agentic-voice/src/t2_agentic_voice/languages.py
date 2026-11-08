"""The language parts: the canonical Arabic normalizer, digit normalization, numbers and IDs said
in words, the clause splitter, the text a text-to-speech provider is sent for a phrase (the
characters no one sees made a space or dropped), the pronunciation map (`VoiceAgent.pronounce`'s
type, and the function that applies one), the check of a team's spelling guide, and the Whisper
prompt of a call's language (`whisper_prompt`: the vocabulary's terms, then the command words as
they should be written), and the register of an Arabic turn as the talker reads it (`register_of`:
Saudi when its words hold a Saudi or Gulf dialect form, MSA when they hold none), which a team's
measurement holds a reply to. Provisional (D-021). A facade: it only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.agent.language import register_of
from t2_agentic_voice.domain.text.arabic import normalize_arabic
from t2_agentic_voice.domain.text.clauses import split_clauses
from t2_agentic_voice.domain.text.digits import normalize_digits
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.domain.text.pronounce import Pronunciations, pronounce
from t2_agentic_voice.domain.text.rulings import SpellingIssue, SpellingRule
from t2_agentic_voice.domain.text.speaking import speak_id, speak_number
from t2_agentic_voice.domain.text.spelling import spelling_issues
from t2_agentic_voice.domain.whisper_prompt import WhisperPrompt, whisper_prompt

__all__ = [
    "Pronunciations",
    "SpellingIssue",
    "SpellingRule",
    "WhisperPrompt",
    "normalize_arabic",
    "normalize_digits",
    "pronounce",
    "provider_text",
    "register_of",
    "speak_id",
    "speak_number",
    "spelling_issues",
    "split_clauses",
    "whisper_prompt",
]
