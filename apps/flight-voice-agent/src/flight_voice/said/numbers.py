"""Numbers, times, dates, amounts and the travelers in words, in Saudi Arabic, MSA and English,
for the lines the app renders in code (the booking's read-back and `done`), which the talker
never writes and the speaking rules never reach. Until the library says these forms by register
itself, the app says them here, under the names the library's will take (`speak_number`,
`speak_time`, `speak_date`, `speak_amount`), so the swap is an import.

The Saudi forms are the ones a Saudi speaker says: «سبعطعش» for 17, «مية» and «ميتين», «تسع
وعشر دقايق الصبح» for 09:10, «أربع إلا ربع العصر» for 15:45, «الخميس سبعطعش ديسمبر»; MSA's are
the formal ones: «التاسعة وعشر دقائق صباحًا», «الخميس السابع عشر من ديسمبر», an amount's noun
in the case its number takes («ريالًا» after 11 to 99, «ريالات» after 3 to 10). English numbers
are the library's own words. A native Saudi speaker checks the Saudi forms once (TD-058's
check). Arabic is written plainly, as the app's other word modules write it.
"""

from __future__ import annotations

from datetime import date, time
from typing import Final

from t2_agentic_voice.languages import speak_number as library_number

from flight_voice.airline.airports import Register
from flight_voice.said import words


def _listed(said: str) -> tuple[str, ...]:
    """The words `said` holds, each between bars: "|one|two" is ("", "one", "two")."""
    return tuple(said.split("|"))


_UNITS: Final[dict[Register, tuple[str, ...]]] = {
    "saudi": _listed("|واحد|اثنين|ثلاثة|أربعة|خمسة|ستة|سبعة|ثمانية|تسعة"),
    "msa": _listed("|واحد|اثنان|ثلاثة|أربعة|خمسة|ستة|سبعة|ثمانية|تسعة"),
}
_TEENS: Final[dict[Register, tuple[str, ...]]] = {  # 10 to 19
    "saudi": _listed("عشرة|احدعش|اثنعش|ثلطعش|أربعطعش|خمسطعش|ستطعش|سبعطعش|ثمنطعش|تسعطعش"),
    "msa": _listed(
        "عشرة|أحد عشر|اثنا عشر|ثلاثة عشر|أربعة عشر|خمسة عشر|ستة عشر|سبعة عشر|ثمانية عشر|تسعة عشر"
    ),
}
_TENS: Final[dict[Register, tuple[str, ...]]] = {
    "saudi": _listed("||عشرين|ثلاثين|أربعين|خمسين|ستين|سبعين|ثمانين|تسعين"),
    "msa": _listed("||عشرون|ثلاثون|أربعون|خمسون|ستون|سبعون|ثمانون|تسعون"),
}
_HUNDREDS: Final[dict[Register, tuple[str, ...]]] = {
    "saudi": _listed("|مية|ميتين|ثلاث مية|أربع مية|خمس مية|ست مية|سبع مية|ثمان مية|تسع مية"),
    "msa": _listed("|مئة|مئتان|ثلاثمئة|أربعمئة|خمسمئة|ستمئة|سبعمئة|ثمانمئة|تسعمئة"),
}
# A count of a feminine noun, a minute (دقيقة): 3 to 10 in their short forms, and MSA's units
# before a ten («خمس وعشرون دقيقة»).
_FEMININE: Final[dict[Register, tuple[str, ...]]] = {
    "saudi": _listed("|||ثلاث|أربع|خمس|ست|سبع|ثمان|تسع|عشر"),
    "msa": _listed("|إحدى|اثنتان|ثلاث|أربع|خمس|ست|سبع|ثماني|تسع|عشر"),
}
# The hours of a clock, twelve first, as each register says a time.
_HOURS: Final[dict[Register, tuple[str, ...]]] = {
    "saudi": _listed("اثنعش|واحدة|ثنتين|ثلاث|أربع|خمس|ست|سبع|ثمان|تسع|عشر|احدعش"),
    "msa": _listed(
        "الثانية عشرة|الواحدة|الثانية|الثالثة|الرابعة|الخامسة|السادسة|السابعة|الثامنة|التاسعة|"
        "العاشرة|الحادية عشرة"
    ),
}
# The minutes a clock says as a part of the hour; from 40 on, of the hour to come.
_PARTS_OF_HOUR: Final[dict[Register, dict[int, str]]] = {
    "saudi": {15: "وربع", 20: "وثلث", 25: "ونص إلا خمس", 30: "ونص", 35: "ونص وخمس"}
    | {40: "إلا ثلث", 45: "إلا ربع", 50: "إلا عشر", 55: "إلا خمس"},
    "msa": {15: "والربع", 20: "والثلث", 30: "والنصف", 40: "إلا ثلثًا", 45: "إلا ربعًا"},
}
_MSA_ORDINALS: Final = _listed(
    "|الأول|الثاني|الثالث|الرابع|الخامس|السادس|السابع|الثامن|التاسع|العاشر"
)
_EN_ORDINALS: Final = _listed(
    "|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth"
)
_EN_TENS_ORDINALS: Final = {2: "twentieth", 3: "thirtieth"}


def _below_thousand(number: int, register: Register) -> str:
    parts: list[str] = []
    if number >= 100:
        parts.append(_HUNDREDS[register][number // 100])
    rest = number % 100
    if 10 <= rest < 20:
        parts.append(_TEENS[register][rest - 10])
    elif rest:
        unit, ten = _UNITS[register][rest % 10], _TENS[register][rest // 10]
        parts.append(" و".join(p for p in (unit, ten) if p))
    return " و".join(parts)


def _thousands(count: int, register: Register) -> str:
    if count == 1:
        return "ألف"
    if count == 2:
        return "ألفين" if register == "saudi" else "ألفان"
    if count <= 10:
        return f"{_below_thousand(count, register)} آلاف"
    said = _below_thousand(count, register)
    if register == "msa" and 11 <= count % 100 <= 99:
        return f"{said} ألفًا"
    if register == "msa" and count % 100 == 0 and count // 100 == 2:
        return "مئتا ألف"
    return f"{said} ألف"


def speak_number(number: int, register: Register) -> str:
    """A whole number from 0 to 999 999 in words: «ألفين وأربع مية وخمسين» in Saudi, «ألفان
    وأربعمئة وخمسون» in MSA, the library's "two thousand four hundred and fifty" in English.
    ValueError past that range."""
    if not 0 <= number < 1_000_000:
        raise ValueError("speak_number says 0 to 999 999")
    if register == "en":
        return library_number(number, language="en")
    if number == 0:
        return "صفر"
    parts = [_thousands(number // 1000, register)] if number >= 1000 else []
    if number % 1000:
        parts.append(_below_thousand(number % 1000, register))
    return " و".join(parts)


def _minutes(count: int, register: Register) -> str:
    """`count` minutes after the hour, as a time says them: «وعشر دقايق», «وخمس وعشرون دقيقة»."""
    if register == "saudi":
        if count <= 2:
            return ("", "ودقيقة", "ودقيقتين")[count]
        if count <= 10:
            return f"و{_FEMININE['saudi'][count]} دقايق"
        return f"و{speak_number(count, 'saudi')} دقيقة"
    if count <= 2:
        return ("", "ودقيقة", "ودقيقتان")[count]
    if count <= 10:
        return f"و{_FEMININE['msa'][count]} دقائق"
    unit, ten = count % 10, count // 10
    if ten == 1:
        first = "اثنتا" if unit == 2 else _FEMININE["msa"][unit]
        return f"و{first} عشرة دقيقة"
    said = " و".join(p for p in (_FEMININE["msa"][unit] if unit else "", _TENS["msa"][ten]) if p)
    return f"و{said} دقيقة"


def speak_time(at: time, register: Register) -> str:
    """A departure time with its part of the day: «تسع وعشر دقايق الصبح», «التاسعة وعشر دقائق
    صباحًا», "nine ten in the morning"; the part of the day is the time's own (words.py)."""
    part = words.part_said(at, register)
    if register == "en":
        hour = library_number(at.hour % 12 or 12, language="en")
        minute = "" if not at.minute else library_number(at.minute, language="en")
        if 0 < at.minute < 10:
            minute = f"oh {minute}"
        return " ".join(p for p in (hour, minute, part) if p)
    whole = _PARTS_OF_HOUR[register].get(at.minute)
    clock = at.hour + 1 if whole is not None and at.minute >= 40 else at.hour
    minutes = whole if whole is not None else _minutes(at.minute, register)
    return " ".join(p for p in (_HOURS[register][clock % 12], minutes, part) if p)


def _msa_ordinal(day: int) -> str:
    if day <= 10:
        return _MSA_ORDINALS[day]
    unit, ten = day % 10, day // 10
    first = "الحادي" if unit == 1 else _MSA_ORDINALS[unit]
    if ten == 1:
        return f"{first} عشر"
    tens = f"ال{_TENS['saudi'][ten]}"  # the genitive: «العشرين من ديسمبر»
    return f"{first} و{tens}" if unit else tens


def _en_ordinal(day: int) -> str:
    if day <= 12:
        return _EN_ORDINALS[day]
    if day < 20:
        return f"{library_number(day, language='en')}th"
    unit, ten = day % 10, day // 10
    if not unit:
        return _EN_TENS_ORDINALS[ten]
    return f"{library_number(ten * 10, language='en')}-{_EN_ORDINALS[unit]}"


def speak_date(day: date, register: Register, *, month: bool = True) -> str:
    """A day with its weekday: «الخميس سبعطعش ديسمبر», «الخميس السابع عشر من ديسمبر»,
    "Thursday the seventeenth of December"; without its month when `month` is false, for a day
    said after another of the same month: «الأحد عشرين», «الأحد العشرين», "Sunday the
    twentieth"."""
    weekday, named = words.weekday(day, register), words.month(day.month, register)
    if register == "saudi":
        said = f"{weekday} {speak_number(day.day, 'saudi')}"
        return f"{said} {named}" if month else said
    if register == "msa":
        said = f"{weekday} {_msa_ordinal(day.day)}"
        return f"{said} من {named}" if month else said
    said = f"{weekday} the {_en_ordinal(day.day)}"
    return f"{said} of {named}" if month else said


def speak_amount(riyals: int, register: Register) -> str:
    """An amount in Saudi riyals: «خمسة آلاف ومية وعشرين ريال», «خمسة آلاف ومئة وعشرون ريالًا»,
    "five thousand one hundred and twenty riyals"."""
    said = speak_number(riyals, register)
    if register == "en":
        return f"{said} {'riyal' if riyals == 1 else 'riyals'}"
    last = riyals % 100
    if 3 <= last <= 10:
        return f"{said} ريالات"
    if register == "msa" and last >= 11:
        return f"{said} ريالًا"
    return f"{said} ريال"


def speak_travelers(count: int, register: Register) -> str:
    """Who a booking is for, as the read-back says it first: «لك أنت», «لك ولشخص ثاني»,
    «لثلاثة أشخاص» in Saudi; «لك وحدك», «لشخصين», «لثلاثة أشخاص» in MSA; "you", "two
    travelers" in English, after its "For"."""
    if register == "en":
        return "you" if count == 1 else f"{library_number(count, language='en')} travelers"
    if count == 1:
        return "لك أنت" if register == "saudi" else "لك وحدك"
    if count == 2:
        return "لك ولشخص ثاني" if register == "saudi" else "لشخصين"
    return f"ل{_below_thousand(count, register)} أشخاص"
