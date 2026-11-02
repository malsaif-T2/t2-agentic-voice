"""Numbers and IDs, spoken in Arabic and English (the design's 3.1 and 5.1). Built by plan 003's
Track A; until then stubs. Public through the `languages` facade.

A number is said through num2words (the cardinals; MSA forms in Arabic, which num2words gives),
behind these functions alone: only `domain` imports num2words (`[[owners]]`). An ID is read
digit by digit from the library's own table, never through num2words. In a text, a run of digits
is an ID when it has five digits or more, starts with a zero, or follows a cue that names a
number's last digits, in Arabic or in English; any other run is a number (plan 003's decision
log). ASCII and Arabic-Indic digits are both read.
"""

from __future__ import annotations

from t2_agentic_voice.core.settings.tts import LanguageTag

_STUB = "speaking numbers and IDs is built by plan 003's Track A"


def speak_number(number: int, *, language: LanguageTag) -> str:
    """`number` in words, in `language` (MSA forms for both Arabic tags)."""
    raise NotImplementedError(_STUB)


def speak_id(digits: str, *, language: LanguageTag) -> str:
    """`digits` (ASCII or Arabic-Indic) read one by one in `language`, from the library's own
    table."""
    raise NotImplementedError(_STUB)


def speak_digits(text: str, *, language: LanguageTag) -> str:
    """`text` with every run of digits in words, each an ID or a number by the rule above, the
    rest of the text as it was."""
    raise NotImplementedError(_STUB)
