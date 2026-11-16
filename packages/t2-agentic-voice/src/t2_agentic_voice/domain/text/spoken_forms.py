"""Times, dates, durations and amounts in words, by register: Saudi Arabic, MSA or English, for
the lines a team renders in code (a booking's read-back, its `done`), which the talker never
writes. Public through the `languages` facade.

Each function takes the reply's language tag and, for Arabic, its register (`Register`; the
call's, agent/language.py's `call_register`); with no register, an `ar-SA` reply is Saudi and an
`ar` one MSA (`said_in`). The forms, Saudi, then MSA, then English:

- 09:10: «تسع وعشر دقايق الصبح», «التاسعة وعشر دقائق صباحًا», "nine ten in the morning".
- 16:00: «أربع العصر», «الرابعة عصرًا», "four in the afternoon".
- 2026-12-17: «الخميس سبعطعش ديسمبر», «الخميس السابع عشر من ديسمبر», "Thursday the
  seventeenth of December": the day a cardinal in Saudi, an ordinal in MSA and English.
- 7 hours 5 minutes: «سبع ساعات وخمس دقايق», «سبع ساعات وخمس دقائق», "seven hours and five
  minutes".
- 2450 riyals: «ألفين وأربع مية وخمسين ريال», «ألفان وأربعمئة وخمسون ريالًا», "two thousand
  four hundred fifty riyals".

The words come from domain/text/spoken_words.py, the Arabic numbers from the library's own
tables (domain/text/arabic_numbers.py). English numbers say no "and" ("four hundred fifty").
The Saudi forms are the agent's until a native speaker checks them once (TD-058's check).
"""

from __future__ import annotations

from datetime import date, time, timedelta

from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.text.arabic_numbers import (
    AND,
    HIGHEST,
    Register,
    arabic_number,
    feminine_count,
    msa_ordinal,
)
from t2_agentic_voice.domain.text.speaking import speak_number
from t2_agentic_voice.domain.text.spoken_words import (
    CLOCK_HOURS,
    EN_ORDINALS,
    HOUR,
    MINUTE,
    MONTHS_AR,
    MONTHS_EN,
    OF,
    ONE_AFTER,
    PARTS_OF_HOUR,
    RIYAL,
    WEEKDAYS_AR,
    WEEKDAYS_EN,
    part_of_day,
    said_in,
)


def english(number: int) -> str:
    """`number` in English words as a spoken line says it: no comma, no "and"."""
    return speak_number(number, language="en").replace(" and ", " ")


def _counted(count: int, noun: tuple[str, str, str, str], register: Register) -> str:
    """`count` (1 or more) of a noun, the noun in the form the count takes («ساعة»,
    «ساعتين», «سبع ساعات», «احدعش ساعة»)."""
    one, two, plural, past_ten = noun
    if count == 1:
        return one
    if count == 2:
        return two
    if 3 <= count <= 10:
        return f"{feminine_count(count, register)} {plural}"
    return f"{feminine_count(count, register)} {past_ten}"


def speak_time(at: time, *, language: LanguageTag, register: Register | None = None) -> str:
    """A time of day with its part of the day: «تسع وعشر دقايق الصبح», «التاسعة وعشر دقائق
    صباحًا», "nine ten in the morning"."""
    said = said_in(language, register)
    part = part_of_day(at, said)
    if said == "en":
        minute = english(at.minute) if at.minute else ""
        if 0 < at.minute < 10:
            minute = f"oh {minute}"
        return " ".join(p for p in (english(at.hour % 12 or 12), minute, part) if p)
    whole = PARTS_OF_HOUR[said].get(at.minute)
    clock = at.hour + 1 if whole is not None and at.minute >= 40 else at.hour
    minutes = whole or (f"{AND}{_counted(at.minute, MINUTE[said], said)}" if at.minute else "")
    return " ".join(p for p in (CLOCK_HOURS[said][clock % 12], minutes, part) if p)


def _en_ordinal(day: int) -> str:
    if day <= 12:
        return EN_ORDINALS[day]
    if day < 20:
        return f"{english(day)}th"
    unit, ten = day % 10, day // 10
    if not unit:
        return f"{english(ten * 10)[:-1]}ieth"  # twenty: twentieth
    return f"{english(ten * 10)}-{EN_ORDINALS[unit]}"


def speak_date(day: date, *, language: LanguageTag, register: Register | None = None) -> str:
    """A day with its weekday and month, never its year: «الخميس سبعطعش ديسمبر», «الخميس
    السابع عشر من ديسمبر», "Thursday the seventeenth of December"."""
    said = said_in(language, register)
    if said == "en":
        weekday, month = WEEKDAYS_EN[day.weekday()], MONTHS_EN[day.month - 1]
        return f"{weekday} the {_en_ordinal(day.day)} of {month}"
    weekday, month = WEEKDAYS_AR[day.weekday()], MONTHS_AR[day.month - 1]
    if said == "saudi":
        return f"{weekday} {arabic_number(day.day, 'saudi')} {month}"
    return f"{weekday} {msa_ordinal(day.day)} {OF} {month}"


def speak_duration(
    length: timedelta, *, language: LanguageTag, register: Register | None = None
) -> str:
    """A length of time in hours and minutes, seconds left out: «سبع ساعات وخمس دقايق», «سبع
    ساعات وخمس دقائق», "seven hours and five minutes". ValueError below one minute."""
    hours, minutes = divmod(int(length.total_seconds()) // 60, 60)
    if hours == minutes == 0:
        raise ValueError("speak_duration says a length of one minute or more")
    said = said_in(language, register)
    if said == "en":
        parts = [
            f"{english(count)} {noun}{'' if count == 1 else 's'}"
            for count, noun in ((hours, "hour"), (minutes, "minute"))
            if count
        ]
        return " and ".join(parts)
    parts = [
        _counted(count, noun[said], said)
        for count, noun in ((hours, HOUR), (minutes, MINUTE))
        if count
    ]
    return f" {AND}".join(parts)


def speak_amount(riyals: int, *, language: LanguageTag, register: Register | None = None) -> str:
    """An amount of Saudi riyals, 0 to 999 999: «ألفين وأربع مية وخمسين ريال», «ألفان وأربعمئة
    وخمسون ريالًا», "two thousand four hundred fifty riyals". ValueError outside that range."""
    if not 0 <= riyals <= HIGHEST:
        raise ValueError(f"speak_amount says 0 to {HIGHEST} riyals")
    said = said_in(language, register)
    if said == "en":
        return f"{english(riyals)} {'riyal' if riyals == 1 else 'riyals'}"
    one, two, plural, past_ten = RIYAL[said]
    if riyals == 1:
        return f"{one} {ONE_AFTER}"
    if riyals == 2:
        return two
    number = arabic_number(riyals, said)
    last = riyals % 100
    if 3 <= last <= 10:
        return f"{number} {plural}"
    return f"{number} {past_ten if last > 10 else one}"
