"""Numbers, times, dates, lengths of time and amounts said by register (domain/text/
arabic_numbers.py, spoken_words.py, spoken_forms.py): Saudi Arabic, MSA and English, the
register chosen from the reply's tag or given (the call's, `call_register`). The Saudi forms
are the agent's until a native speaker checks them once (TD-058's check): these tests hold what
the library says, not that a Saudi ear has passed it."""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from t2_agentic_voice.agent.language import call_register
from t2_agentic_voice.domain.text.arabic_numbers import (
    HIGHEST,
    Register,
    arabic_number,
    msa_ordinal,
)
from t2_agentic_voice.domain.text.speaking import speak_number
from t2_agentic_voice.domain.text.spoken_forms import (
    speak_amount,
    speak_date,
    speak_duration,
    speak_time,
)
from t2_agentic_voice.domain.text.spoken_words import part_of_day, said_in
from t2_agentic_voice.languages import speak_amount as public_amount
from t2_agentic_voice.languages import speak_date as public_date
from t2_agentic_voice.languages import speak_duration as public_duration
from t2_agentic_voice.languages import speak_time as public_time

THURSDAY = date(2026, 12, 17)
SEVEN_OH_FIVE = timedelta(hours=7, minutes=5)


def test_the_facade_gives_the_same_functions() -> None:
    assert (public_time, public_date, public_duration, public_amount) == (
        speak_time,
        speak_date,
        speak_duration,
        speak_amount,
    )


@pytest.mark.parametrize(
    ("at", "saudi", "msa", "english"),
    [
        (
            time(9, 10),
            "تسع وعشر دقايق الصبح",
            "التاسعة وعشر دقائق صباحًا",
            "nine ten in the morning",
        ),
        (time(16, 0), "أربع العصر", "الرابعة عصرًا", "four in the afternoon"),
        # The English part of the day from 18:00 to 21:59 is "in the evening" by the rule of
        # the parts of the day, which the forms' table's "at night" for 21:30 disagrees with.
        (time(21, 30), "تسع ونص بالليل", "التاسعة والنصف مساءً", "nine thirty in the evening"),
    ],
)
def test_a_time_is_said_in_each_register(at: time, saudi: str, msa: str, english: str) -> None:
    assert speak_time(at, language="ar-SA", register="saudi") == saudi
    assert speak_time(at, language="ar-SA", register="msa") == msa
    assert speak_time(at, language="en") == english


def test_a_date_is_said_with_its_weekday_and_month_never_its_year() -> None:
    assert speak_date(THURSDAY, language="ar-SA") == "الخميس سبعطعش ديسمبر"
    assert speak_date(THURSDAY, language="ar") == "الخميس السابع عشر من ديسمبر"
    assert speak_date(THURSDAY, language="en") == "Thursday the seventeenth of December"


def test_a_length_of_time_is_said_in_hours_and_minutes() -> None:
    assert speak_duration(SEVEN_OH_FIVE, language="ar-SA") == "سبع ساعات وخمس دقايق"
    assert speak_duration(SEVEN_OH_FIVE, language="ar") == "سبع ساعات وخمس دقائق"
    assert speak_duration(SEVEN_OH_FIVE, language="en") == "seven hours and five minutes"


def test_an_amount_is_said_with_its_noun_in_the_form_its_number_takes() -> None:
    assert speak_amount(2450, language="ar-SA") == "ألفين وأربع مية وخمسين ريال"
    assert speak_amount(2450, language="ar") == "ألفان وأربعمئة وخمسون ريالًا"
    assert speak_amount(2450, language="en") == "two thousand four hundred fifty riyals"


@pytest.mark.parametrize(
    ("riyals", "saudi", "msa", "english"),
    [
        (1, "ريال واحد", "ريال واحد", "one riyal"),
        (2, "ريالين", "ريالان", "two riyals"),
        (5, "خمسة ريالات", "خمسة ريالات", "five riyals"),
        (15, "خمسطعش ريال", "خمسة عشر ريالًا", "fifteen riyals"),
        (300, "ثلاث مية ريال", "ثلاثمئة ريال", "three hundred riyals"),
        (5120, "خمسة آلاف ومية وعشرين ريال", "خمسة آلاف ومئة وعشرون ريالًا", None),
    ],
)
def test_an_amount_s_noun_follows_its_count(
    riyals: int, saudi: str, msa: str, english: str | None
) -> None:
    assert speak_amount(riyals, language="ar-SA") == saudi
    assert speak_amount(riyals, language="ar") == msa
    if english is not None:
        assert speak_amount(riyals, language="en") == english


def test_an_amount_outside_the_tables_range_is_refused() -> None:
    for riyals in (-1, HIGHEST + 1):
        with pytest.raises(ValueError, match="speak_amount says 0 to"):
            speak_amount(riyals, language="ar-SA")


@pytest.mark.parametrize(
    ("number", "saudi"),
    [
        (0, "صفر"),
        (1, "واحد"),
        (2, "اثنين"),
        (11, "احدعش"),
        (12, "اثنعش"),
        (13, "ثلطعش"),
        (17, "سبعطعش"),
        (19, "تسعطعش"),
        (20, "عشرين"),
        (21, "واحد وعشرين"),
        (99, "تسعة وتسعين"),
        (100, "مية"),
        (200, "ميتين"),
        (305, "ثلاث مية وخمسة"),
        (1000, "ألف"),
        (2000, "ألفين"),
        (3000, "ثلاثة آلاف"),
        (10_000, "عشرة آلاف"),
        (11_000, "احدعش ألف"),
        (2450, "ألفين وأربع مية وخمسين"),
        (40_017, "أربعين ألف وسبعطعش"),
        (99_999, "تسعة وتسعين ألف وتسع مية وتسعة وتسعين"),
    ],
)
def test_a_number_is_said_in_saudi_words(number: int, saudi: str) -> None:
    assert arabic_number(number, "saudi") == saudi
    assert speak_number(number, language="ar-SA", register="saudi") == saudi


# Every word a Saudi number from 0 to 99 999 may hold, each with its "and" or without.
_SAUDI_WORDS = frozenset(
    [
        "صفر",
        "واحد",
        "اثنين",
        "ثلاثة",
        "أربعة",
        "خمسة",
        "ستة",
        "سبعة",
        "ثمانية",
        "تسعة",
        "عشرة",
        "احدعش",
        "اثنعش",
        "ثلطعش",
        "أربعطعش",
        "خمسطعش",
        "ستطعش",
        "سبعطعش",
        "ثمنطعش",
        "تسعطعش",
        "عشرين",
        "ثلاثين",
        "أربعين",
        "خمسين",
        "ستين",
        "سبعين",
        "ثمانين",
        "تسعين",
        "مية",
        "ميتين",
        "ثلاث",
        "أربع",
        "خمس",
        "ست",
        "سبع",
        "ثمان",
        "تسع",
        "ألف",
        "ألفين",
        "آلاف",
    ]
)


def test_every_number_to_99_999_has_saudi_words_of_its_own() -> None:
    said = [arabic_number(number, "saudi") for number in range(100_000)]
    assert len(set(said)) == len(said)  # no two numbers said alike
    for words in said:
        assert words == " ".join(words.split())  # no doubled or trailing space
        for word in words.split():
            assert word in _SAUDI_WORDS or word.removeprefix("و") in _SAUDI_WORDS, words


@pytest.mark.parametrize(
    ("number", "msa"),
    [
        (2, "اثنان"),
        (200, "مئتان"),
        (2000, "ألفان"),
        (11_000, "أحد عشر ألفًا"),
        (200_000, "مئتا ألف"),
        (203_000, "مئتان وثلاثة آلاف"),
        (250_000, "مئتان وخمسون ألفًا"),
    ],
)
def test_a_number_is_said_in_msa_words_from_the_library_s_tables(number: int, msa: str) -> None:
    """num2words says 200 «مئتا» and 2000 «ألفا» (TD-058): the tables say them whole."""
    assert speak_number(number, language="ar", register="msa") == msa


def test_with_no_register_a_number_is_said_as_before() -> None:
    """The characterization of the default: num2words' MSA words for both Arabic tags."""
    assert speak_number(2450, language="ar-SA") == "ألفان وأربعمائة وخمسون"
    assert speak_number(200, language="ar") == "مئتا"


def test_a_register_outside_the_tables_range_and_for_english_keeps_num2words() -> None:
    assert speak_number(-5, language="ar-SA", register="saudi") == "سالب خمسة"
    million = speak_number(1_000_000, language="ar-SA", register="saudi")
    assert million == speak_number(1_000_000, language="ar-SA")
    assert speak_number(2450, language="en", register="saudi") == speak_number(2450, language="en")


def test_the_arabic_tables_refuse_a_number_past_their_range() -> None:
    for number in (-1, HIGHEST + 1):
        with pytest.raises(ValueError, match="arabic_number says 0 to"):
            arabic_number(number, "msa")


_MSA_ORDINALS = (
    "الأول الثاني الثالث الرابع الخامس السادس السابع الثامن التاسع العاشر",
    "الحادي_عشر الثاني_عشر الثالث_عشر الرابع_عشر الخامس_عشر السادس_عشر السابع_عشر "
    "الثامن_عشر التاسع_عشر العشرين",
    "الحادي_والعشرين الثاني_والعشرين الثالث_والعشرين الرابع_والعشرين الخامس_والعشرين "
    "السادس_والعشرين السابع_والعشرين الثامن_والعشرين التاسع_والعشرين الثلاثين الحادي_والثلاثين",
)
_EN_ORDINALS = (
    "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth "
    "thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth "
    "twenty-first twenty-second twenty-third twenty-fourth twenty-fifth twenty-sixth "
    "twenty-seventh twenty-eighth twenty-ninth thirtieth thirty-first"
)


@pytest.mark.parametrize("day", range(1, 32))
def test_every_day_of_the_month_is_said_in_each_register(day: int) -> None:
    on = date(2026, 12, day)  # December has 31 days
    weekday = speak_date(on, language="en").split()[0]
    msa = " ".join(_MSA_ORDINALS).split()[day - 1].replace("_", " ")
    assert msa_ordinal(day) == msa
    assert speak_date(on, language="ar").split(" ", 1)[1] == f"{msa} من ديسمبر"
    saudi = speak_date(on, language="ar-SA").split(" ", 1)[1]
    assert saudi == f"{arabic_number(day, 'saudi')} ديسمبر"  # a cardinal, as a Saudi says it
    english = _EN_ORDINALS.split()[day - 1]
    assert speak_date(on, language="en") == f"{weekday} the {english} of December"


def test_an_ordinal_outside_a_month_is_refused() -> None:
    for day in (0, 32):
        with pytest.raises(ValueError, match="day of the month"):
            msa_ordinal(day)


@pytest.mark.parametrize(
    ("hour", "saudi", "msa", "english"),
    [
        (0, "الفجر", "فجرًا", "at night"),
        (4, "الفجر", "فجرًا", "at night"),
        (5, "الصبح", "صباحًا", "in the morning"),
        (11, "الصبح", "صباحًا", "in the morning"),
        (12, "الظهر", "ظهرًا", "in the afternoon"),
        (14, "الظهر", "ظهرًا", "in the afternoon"),
        (15, "العصر", "عصرًا", "in the afternoon"),
        (17, "العصر", "عصرًا", "in the afternoon"),
        (18, "المغرب", "مساءً", "in the evening"),
        (19, "بالليل", "مساءً", "in the evening"),
        (21, "بالليل", "مساءً", "in the evening"),
        (22, "بالليل", "مساءً", "at night"),
        (23, "بالليل", "مساءً", "at night"),
    ],
)
def test_each_part_of_the_day_begins_at_its_hour(
    hour: int, saudi: str, msa: str, english: str
) -> None:
    for minute in (0, 59):
        at = time(hour, minute)
        assert (part_of_day(at, "saudi"), part_of_day(at, "msa")) == (saudi, msa)
        assert part_of_day(at, "en") == english


@pytest.mark.parametrize(
    ("at", "saudi", "msa"),
    [
        (time(10, 15), "عشر وربع الصبح", "العاشرة والربع صباحًا"),
        (time(10, 20), "عشر وثلث الصبح", "العاشرة والثلث صباحًا"),
        (time(10, 25), "عشر ونص إلا خمس الصبح", "العاشرة وخمس وعشرون دقيقة صباحًا"),
        (time(10, 40), "احدعش إلا ثلث الصبح", "الحادية عشرة إلا ثلثًا صباحًا"),
        (time(15, 45), "أربع إلا ربع العصر", "الرابعة إلا ربعًا عصرًا"),
        (time(11, 55), "اثنعش إلا خمس الصبح", "الحادية عشرة وخمس وخمسون دقيقة صباحًا"),
        (time(13, 1), "واحدة ودقيقة الظهر", "الواحدة ودقيقة ظهرًا"),
        (time(13, 2), "واحدة ودقيقتين الظهر", "الواحدة ودقيقتان ظهرًا"),
        (time(0, 12), "اثنعش واثنعش دقيقة الفجر", "الثانية عشرة واثنتا عشرة دقيقة فجرًا"),
    ],
)
def test_a_clock_says_its_parts_of_an_hour(at: time, saudi: str, msa: str) -> None:
    assert speak_time(at, language="ar-SA") == saudi
    assert speak_time(at, language="ar") == msa


def test_an_english_clock_says_oh_before_a_minute_under_ten_and_twelve_for_midnight() -> None:
    assert speak_time(time(0, 5), language="en") == "twelve oh five at night"
    assert speak_time(time(12, 0), language="en") == "twelve in the afternoon"


@pytest.mark.parametrize(
    ("length", "saudi", "msa", "english"),
    [
        (timedelta(minutes=1), "دقيقة", "دقيقة", "one minute"),
        (timedelta(hours=2), "ساعتين", "ساعتان", "two hours"),
        (timedelta(hours=1, minutes=2), "ساعة ودقيقتين", "ساعة ودقيقتان", None),
        (timedelta(hours=11, minutes=30), "احدعش ساعة وثلاثين دقيقة", None, None),
        (timedelta(hours=12, seconds=40), None, "اثنتا عشرة ساعة", "twelve hours"),
    ],
)
def test_a_length_of_time_counts_each_noun(
    length: timedelta, saudi: str | None, msa: str | None, english: str | None
) -> None:
    for language, said in (("ar-SA", saudi), ("ar", msa), ("en", english)):
        if said is not None:
            assert speak_duration(length, language=language) == said  # type: ignore[arg-type]


def test_a_length_under_a_minute_is_refused() -> None:
    with pytest.raises(ValueError, match="one minute or more"):
        speak_duration(timedelta(seconds=59), language="en")


def test_the_register_follows_the_reply_s_tag_unless_one_is_given() -> None:
    assert said_in("ar-SA") == "saudi"
    assert said_in("ar") == "msa"
    assert said_in("ar-SA", "msa") == "msa"
    assert said_in("ar", "saudi") == "saudi"
    assert said_in("en", "saudi") == "en"  # English has one form


@pytest.mark.parametrize(
    ("turns", "register"),
    [(["ابي احجز رحلة للندن"], "saudi"), (["أريد أن أحجز رحلة إلى لندن"], "msa")],
)
def test_the_register_chosen_from_the_caller_s_arabic_says_the_reply_s_forms(
    turns: list[str], register: Register
) -> None:
    """An `ar-SA` reply to an MSA caller is said in MSA forms, as its words are (agent/
    language.py's `wording`): the call's register is given to the spoken forms."""
    chosen = call_register(turns)
    assert chosen == register
    expected = {"saudi": "الخميس سبعطعش ديسمبر", "msa": "الخميس السابع عشر من ديسمبر"}
    assert speak_date(THURSDAY, language="ar-SA", register=chosen) == expected[register]
