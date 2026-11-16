"""The fixed words of times, dates, durations and amounts by register (Saudi Arabic, MSA or
English), which the spoken forms are built from (domain/text/spoken_forms.py): the weekdays and
months, each register's parts of the day and its clock's hours and parts of an hour, and the
nouns a count takes (a minute, an hour, a riyal).

The parts of the day: Saudi «الفجر» from 00:00, «الصبح» from 05:00, «الظهر» from 12:00, «العصر»
from 15:00, «المغرب» from 18:00, «بالليل» from 19:00; MSA «فجرًا», «صباحًا», «ظهرًا», «عصرًا»
and from 18:00 «مساءً»; English "at night" to 04:59, "in the morning", "in the afternoon" from
12:00, "in the evening" from 18:00 and "at night" from 22:00. A Saudi clock says a quarter, a
third and a half («وربع», «وثلث», «ونص») and from 40 minutes on the hour to come («إلا ربع»).
"""

from __future__ import annotations

from datetime import time
from typing import Final, Literal

from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.text.arabic_numbers import Register

Said = Register | Literal["en"]

# By Python's weekday, Monday first: al-ithnain, ath-thulatha, al-arbi'a, al-khamis, al-jum'a,
# as-sabt, al-ahad.
WEEKDAYS_AR: Final = (
    "\u0627\u0644\u0627\u062b\u0646\u064a\u0646",
    "\u0627\u0644\u062b\u0644\u0627\u062b\u0627\u0621",
    "\u0627\u0644\u0623\u0631\u0628\u0639\u0627\u0621",
    "\u0627\u0644\u062e\u0645\u064a\u0633",
    "\u0627\u0644\u062c\u0645\u0639\u0629",
    "\u0627\u0644\u0633\u0628\u062a",
    "\u0627\u0644\u0623\u062d\u062f",
)
WEEKDAYS_EN: Final = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
# The months, as Saudi Arabia names them in both registers: yanayir to disambir.
MONTHS_AR: Final = (
    "\u064a\u0646\u0627\u064a\u0631",
    "\u0641\u0628\u0631\u0627\u064a\u0631",
    "\u0645\u0627\u0631\u0633",
    "\u0623\u0628\u0631\u064a\u0644",
    "\u0645\u0627\u064a\u0648",
    "\u064a\u0648\u0646\u064a\u0648",
    "\u064a\u0648\u0644\u064a\u0648",
    "\u0623\u063a\u0633\u0637\u0633",
    "\u0633\u0628\u062a\u0645\u0628\u0631",
    "\u0623\u0643\u062a\u0648\u0628\u0631",
    "\u0646\u0648\u0641\u0645\u0628\u0631",
    "\u062f\u064a\u0633\u0645\u0628\u0631",
)
MONTHS_EN: Final = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
# Each register's parts of the day: the hour each begins at and its words, in the day's order.
# Saudi al-fajr, as-subh, adh-dhuhr, al-asr, al-maghrib, bil-lail; MSA fajran, sabahan,
# dhuhran, asran, masa'an.
PARTS_OF_DAY: Final[dict[Said, tuple[tuple[int, str], ...]]] = {
    "saudi": tuple(
        zip(
            (0, 5, 12, 15, 18, 19),
            (
                "\u0627\u0644\u0641\u062c\u0631",
                "\u0627\u0644\u0635\u0628\u062d",
                "\u0627\u0644\u0638\u0647\u0631",
                "\u0627\u0644\u0639\u0635\u0631",
                "\u0627\u0644\u0645\u063a\u0631\u0628",
                "\u0628\u0627\u0644\u0644\u064a\u0644",
            ),
            strict=True,
        )
    ),
    "msa": tuple(
        zip(
            (0, 5, 12, 15, 18),
            (
                "\u0641\u062c\u0631\u064b\u0627",
                "\u0635\u0628\u0627\u062d\u064b\u0627",
                "\u0638\u0647\u0631\u064b\u0627",
                "\u0639\u0635\u0631\u064b\u0627",
                "\u0645\u0633\u0627\u0621\u064b",
            ),
            strict=True,
        )
    ),
    "en": (
        (0, "at night"),
        (5, "in the morning"),
        (12, "in the afternoon"),
        (18, "in the evening"),
        (22, "at night"),
    ),
}
# The hours of a clock, twelve first: Saudi ithna'ash, wahda, thintain, thalath to ihda'ash;
# MSA ath-thaniya ashra, al-wahida to al-hadiya ashra.
CLOCK_HOURS: Final[dict[Register, tuple[str, ...]]] = {
    "saudi": (
        "\u0627\u062b\u0646\u0639\u0634",
        "\u0648\u0627\u062d\u062f\u0629",
        "\u062b\u0646\u062a\u064a\u0646",
        "\u062b\u0644\u0627\u062b",
        "\u0623\u0631\u0628\u0639",
        "\u062e\u0645\u0633",
        "\u0633\u062a",
        "\u0633\u0628\u0639",
        "\u062b\u0645\u0627\u0646",
        "\u062a\u0633\u0639",
        "\u0639\u0634\u0631",
        "\u0627\u062d\u062f\u0639\u0634",
    ),
    "msa": (
        "\u0627\u0644\u062b\u0627\u0646\u064a\u0629 \u0639\u0634\u0631\u0629",
        "\u0627\u0644\u0648\u0627\u062d\u062f\u0629",
        "\u0627\u0644\u062b\u0627\u0646\u064a\u0629",
        "\u0627\u0644\u062b\u0627\u0644\u062b\u0629",
        "\u0627\u0644\u0631\u0627\u0628\u0639\u0629",
        "\u0627\u0644\u062e\u0627\u0645\u0633\u0629",
        "\u0627\u0644\u0633\u0627\u062f\u0633\u0629",
        "\u0627\u0644\u0633\u0627\u0628\u0639\u0629",
        "\u0627\u0644\u062b\u0627\u0645\u0646\u0629",
        "\u0627\u0644\u062a\u0627\u0633\u0639\u0629",
        "\u0627\u0644\u0639\u0627\u0634\u0631\u0629",
        "\u0627\u0644\u062d\u0627\u062f\u064a\u0629 \u0639\u0634\u0631\u0629",
    ),
}
# The minutes a clock says as a part of the hour; from 40 on, of the hour to come. Saudi: wa
# rub', wa thilth, wa nuss illa khams, wa nuss, wa nuss wa khams, illa thilth, illa rub', illa
# ashr, illa khams; MSA: war-rub', ath-thulth, an-nisf, illa thulthan, illa rub'an.
PARTS_OF_HOUR: Final[dict[Register, dict[int, str]]] = {
    "saudi": dict(
        zip(
            (15, 20, 25, 30, 35, 40, 45, 50, 55),
            (
                "\u0648\u0631\u0628\u0639",
                "\u0648\u062b\u0644\u062b",
                "\u0648\u0646\u0635 \u0625\u0644\u0627 \u062e\u0645\u0633",
                "\u0648\u0646\u0635",
                "\u0648\u0646\u0635 \u0648\u062e\u0645\u0633",
                "\u0625\u0644\u0627 \u062b\u0644\u062b",
                "\u0625\u0644\u0627 \u0631\u0628\u0639",
                "\u0625\u0644\u0627 \u0639\u0634\u0631",
                "\u0625\u0644\u0627 \u062e\u0645\u0633",
            ),
            strict=True,
        )
    ),
    "msa": dict(
        zip(
            (15, 20, 30, 40, 45),
            (
                "\u0648\u0627\u0644\u0631\u0628\u0639",
                "\u0648\u0627\u0644\u062b\u0644\u062b",
                "\u0648\u0627\u0644\u0646\u0635\u0641",
                "\u0625\u0644\u0627 \u062b\u0644\u062b\u064b\u0627",
                "\u0625\u0644\u0627 \u0631\u0628\u0639\u064b\u0627",
            ),
            strict=True,
        )
    ),
}
# A feminine noun counted: its one, its two, its plural after 3 to 10, and the form past 10.
# A minute: daqiqa, daqiqatain (Saudi) or daqiqatan (MSA), daqayig (Saudi) or daqa'iq (MSA),
# daqiqa. An hour: sa'a, sa'atain or sa'atan, sa'at, sa'a.
MINUTE: Final[dict[Register, tuple[str, str, str, str]]] = {
    "saudi": (
        "\u062f\u0642\u064a\u0642\u0629",
        "\u062f\u0642\u064a\u0642\u062a\u064a\u0646",
        "\u062f\u0642\u0627\u064a\u0642",
        "\u062f\u0642\u064a\u0642\u0629",
    ),
    "msa": (
        "\u062f\u0642\u064a\u0642\u0629",
        "\u062f\u0642\u064a\u0642\u062a\u0627\u0646",
        "\u062f\u0642\u0627\u0626\u0642",
        "\u062f\u0642\u064a\u0642\u0629",
    ),
}
HOUR: Final[dict[Register, tuple[str, str, str, str]]] = {
    "saudi": (
        "\u0633\u0627\u0639\u0629",
        "\u0633\u0627\u0639\u062a\u064a\u0646",
        "\u0633\u0627\u0639\u0627\u062a",
        "\u0633\u0627\u0639\u0629",
    ),
    "msa": (
        "\u0633\u0627\u0639\u0629",
        "\u0633\u0627\u0639\u062a\u0627\u0646",
        "\u0633\u0627\u0639\u0627\u062a",
        "\u0633\u0627\u0639\u0629",
    ),
}
# A riyal counted, the same way: riyal, riyalain or riyalan, riyalat, riyal (Saudi) or riyalan
# (MSA's accusative after 11 to 99); and wahid, "one", after the noun.
RIYAL: Final[dict[Register, tuple[str, str, str, str]]] = {
    "saudi": (
        "\u0631\u064a\u0627\u0644",
        "\u0631\u064a\u0627\u0644\u064a\u0646",
        "\u0631\u064a\u0627\u0644\u0627\u062a",
        "\u0631\u064a\u0627\u0644",
    ),
    "msa": (
        "\u0631\u064a\u0627\u0644",
        "\u0631\u064a\u0627\u0644\u0627\u0646",
        "\u0631\u064a\u0627\u0644\u0627\u062a",
        "\u0631\u064a\u0627\u0644\u064b\u0627",
    ),
}
ONE_AFTER = "\u0648\u0627\u062d\u062f"
OF = "\u0645\u0646"  # min, "of", between an MSA date's day and its month
EN_ORDINALS: Final = (
    "",
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
    "eleventh",
    "twelfth",
)


def said_in(language: LanguageTag, register: Register | None = None) -> Said:
    """The forms a reply in `language` takes: English for `en`, else `register`, or with none
    Saudi for `ar-SA` and MSA for `ar`."""
    if language == "en":
        return "en"
    return register or ("saudi" if language == "ar-SA" else "msa")


def part_of_day(at: time, said: Said) -> str:
    """The part of the day `at` falls in, as a time says it: «العصر», «عصرًا», "in the
    afternoon"."""
    return [words for hour, words in PARTS_OF_DAY[said] if hour <= at.hour][-1]
