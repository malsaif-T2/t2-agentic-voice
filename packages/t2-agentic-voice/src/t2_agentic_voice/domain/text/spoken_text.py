"""A text's numbers, times and dates said by register, as the `tts.spoken_numbers` setting's
`by_register` asks: what a clause of the talker's, or an action's line, says once the output
guard has read its digits (the design's 8.2).

Its register is the reply's: Saudi or MSA, the caller's (agent/language.py's `call_register`,
which the talker gives each clause), or with none the tag's (`ar-SA` Saudi, `ar` MSA); English
has one form. In that register:

- a time written as a clock writes it, "09:10" or "21:30" (hours 0 to 23, two digits of
  minutes, standing free), is said with its part of the day: «تسع وعشر دقايق الصبح», "nine ten
  in the morning"; the part is left out when the text already says it right after the time
  ("09:10 الصبح" says the part once);
- a date written as ISO writes it, "2026-12-17", is said with its weekday and month, never its
  year: «الخميس سبعطعش ديسمبر»; a date that does not exist is read as digits;
- every other number is said in the register's words (`speak_digits` with the register:
  «ألفين وأربع مية وخمسين» for 2450 in Saudi), and IDs digit by digit as before; an amount
  whose thousands a space parts ("total 3 080", "1 140 riyals") is one number, as with a
  comma: the model writes one so now and then (run F's f09, f-dev-lean-4), and its total was
  said "three zero eight zero". Only an amount: one group of one to three digits, with no
  leading zero and no letter or digit glued before it, a space (a no-break, thin or narrow
  no-break one too), then exactly three digits with no digit or group after them, and riyals
  right after it («ريال», "SAR") or a total a few words before it («المجموع», «الإجمالي»).
  A flight's name ("T2 401"), a reference read in groups ("482 913"), a phone number and two
  numbers side by side are read as before.

With the setting's default, `as_written`, none of this runs: a text is said by `speak_digits`
alone, as it always was (num2words' MSA, a time read as two runs of digits).
"""

from __future__ import annotations

import re
from datetime import date, time

from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.text.arabic_numbers import Register
from t2_agentic_voice.domain.text.digits import DIGIT_CHARACTERS
from t2_agentic_voice.domain.text.speaking import DIGIT, speak_digits
from t2_agentic_voice.domain.text.spoken_forms import speak_date, speak_time
from t2_agentic_voice.domain.text.spoken_words import part_of_day, said_in

# A time or a date standing free: no digit, and no colon or point before a digit, on either
# side, so never a part of "1:2:3", "10:30:15" or "192.168.1.1".
_FREE_BEFORE = rf"(?<!{DIGIT})(?<!{DIGIT}[:.\-])"
_FREE_AFTER = rf"(?![:.\-]?{DIGIT})"
_TIME = re.compile(rf"{_FREE_BEFORE}(?P<hour>{DIGIT}{{1,2}}):(?P<minute>{DIGIT}{{2}}){_FREE_AFTER}")
_DATE = re.compile(
    rf"{_FREE_BEFORE}(?P<year>{DIGIT}{{4}})-(?P<month>{DIGIT}{{2}})-(?P<day>{DIGIT}{{2}})"
    rf"{_FREE_AFTER}"
)


# A space between a number's thousands (a space, a no-break space, a thin space, a narrow
# no-break space), and a number so parted (the module's docstring): one group, its first digit
# no zero, glued to no letter or digit, before exactly three digits.
_GAP = "[ \u00a0\u2009\u202f]"
_SPACED = re.compile(
    rf"(?<![^\W_])(?<!{DIGIT}{_GAP})(?![0\u0660\u06f0]){DIGIT}{{1,3}}{_GAP}{DIGIT}{{3}}"
    rf"(?!{_GAP}?{DIGIT})"
)
# An amount's marks: riyals right after it («ريال», «ريالات» too), or a total up to
# three words of letters before it (al-majmuu', al-ijmaali).
_RIYALS_AFTER = re.compile(r"\s*(?:(?:riyals?|sar|sr)(?![^\W_])|ريال|ر\.س)", re.IGNORECASE)
_TOTAL_BEFORE = re.compile(
    r"(?:(?<![^\W_])total|مجموع|إجمالي)(?:\W+[^\W\d_]+){0,3}\W*$", re.IGNORECASE
)


def _joined(match: re.Match[str]) -> str:
    """A number its thousands a space parts, the space a comma when it is an amount (the
    module's docstring); else as it was."""
    text = match.string
    if _RIYALS_AFTER.match(text, match.end()) or _TOTAL_BEFORE.search(text[: match.start()]):
        return re.sub(_GAP, ",", match.group())
    return match.group()


def _number(match: re.Match[str], group: str) -> int:
    return int(match.group(group).translate(DIGIT_CHARACTERS))


def speak_text(text: str, *, language: LanguageTag, register: Register | None = None) -> str:
    """`text` with its times, dates and numbers said in `language` and `register` (the
    module's docstring)."""
    arabic: Register | None = None
    if language != "en":
        arabic = register or ("saudi" if language == "ar-SA" else "msa")

    def said_date(match: re.Match[str]) -> str:
        try:
            day = date(_number(match, "year"), _number(match, "month"), _number(match, "day"))
        except ValueError:
            return match.group()
        return speak_date(day, language=language, register=arabic)

    def said_time(match: re.Match[str]) -> str:
        hour, minute = _number(match, "hour"), _number(match, "minute")
        if hour > 23 or minute > 59:
            return match.group()
        at = time(hour, minute)
        words = speak_time(at, language=language, register=arabic)
        part = part_of_day(at, said_in(language, arabic))
        if match.string[match.end() :].lstrip().startswith(part):
            words = words.removesuffix(part).rstrip()
        return words

    dated = _DATE.sub(said_date, text)
    timed = _TIME.sub(said_time, dated)
    joined = _SPACED.sub(_joined, timed)
    return speak_digits(joined, language=language, register=arabic)
