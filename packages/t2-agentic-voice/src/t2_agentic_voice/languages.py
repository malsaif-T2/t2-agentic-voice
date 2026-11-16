"""The language parts: the canonical Arabic normalizer, digit normalization, numbers and IDs said
in words, the clause splitter, the text a text-to-speech provider is sent for a phrase (the
characters no one sees made a space or dropped), the pronunciation map (`VoiceAgent.pronounce`'s
type, and the function that applies one), the check of a team's spelling guide, and the Whisper
prompt of a call's language (`whisper_prompt`: the vocabulary's terms, then the command words as
they should be written), and the register of an Arabic turn as the talker reads it (`register_of`:
Saudi when its words hold a Saudi or Gulf dialect form or no Arabic word, MSA when its Arabic
holds no such form), which a team's measurement holds a reply to; and the stray-script rule
(`remove_stray_script`, giving `Kept`): a text as the talker says it, each character of a script
the agent's languages do not write taken out or rewritten; and numbers, times, dates, lengths
of time and amounts said by register (`speak_number`'s `register`, `speak_time`, `speak_date`,
`speak_duration`, `speak_amount`, each taking a `register` of "saudi" or "msa" for an Arabic
reply), for the lines a team renders in code; and key combinations said as their keys
(`speak_keys`) and capitals spelled (`spell_letters`, for a pronunciation map). Provisional
(D-021). A facade: it only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.agent.language import register_of
from t2_agentic_voice.domain.text.arabic import normalize_arabic
from t2_agentic_voice.domain.text.clauses import split_clauses
from t2_agentic_voice.domain.text.digits import normalize_digits
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.domain.text.keys import speak_keys, spell_letters
from t2_agentic_voice.domain.text.pronounce import Pronunciations, pronounce
from t2_agentic_voice.domain.text.rulings import SpellingIssue, SpellingRule
from t2_agentic_voice.domain.text.scripts import Kept, remove_stray_script
from t2_agentic_voice.domain.text.speaking import speak_id, speak_number
from t2_agentic_voice.domain.text.spelling import spelling_issues
from t2_agentic_voice.domain.text.spoken_forms import (
    speak_amount,
    speak_date,
    speak_duration,
    speak_time,
)
from t2_agentic_voice.domain.whisper_prompt import WhisperPrompt, whisper_prompt

__all__ = [
    "Kept",
    "Pronunciations",
    "SpellingIssue",
    "SpellingRule",
    "WhisperPrompt",
    "normalize_arabic",
    "normalize_digits",
    "pronounce",
    "provider_text",
    "register_of",
    "remove_stray_script",
    "speak_amount",
    "speak_date",
    "speak_duration",
    "speak_id",
    "speak_keys",
    "speak_number",
    "speak_time",
    "spell_letters",
    "spelling_issues",
    "split_clauses",
    "whisper_prompt",
]
