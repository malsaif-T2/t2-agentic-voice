"""Whole numbers in Arabic words by register, Saudi or MSA, from the library's own tables: what
a Saudi caller hears from 0 to 999 999 («ألفين وأربع مية وخمسين», «سبعطعش», «مية», «ميتين»),
and the formal forms an MSA caller hears («ألفان وأربعمئة وخمسون», «مئتا ألف», «أحد عشر
ألفًا»). num2words' Arabic is MSA alone, and says 200 and 2000 wrong (TD-058), so the spoken
forms by register (domain/text/spoken_forms.py) read these tables, never num2words.

Also here: a count of a feminine noun (a minute, an hour), whose 3 to 10 take their short
forms («خمس دقايق», «سبع ساعات»), and the MSA ordinal of a day of the month («السابع عشر»).
The Saudi forms are the agent's until a native speaker checks them once (TD-058's check).
"""

from __future__ import annotations

from typing import Final, Literal

# The register of a caller's Arabic, and of the reply to them (agent/language.py): Saudi
# Arabic or Modern Standard Arabic.
Register = Literal["saudi", "msa"]
# The highest number the tables say.
HIGHEST: Final = 999_999


# 0 to 9: sifr, wahid, ithnain (Saudi) or ithnan (MSA), thalatha, arba'a, khamsa, sitta, sab'a,
# thamanya, tis'a.
_UNITS: Final[dict[Register, tuple[str, ...]]] = {
    "saudi": (
        "\u0635\u0641\u0631",
        "\u0648\u0627\u062d\u062f",
        "\u0627\u062b\u0646\u064a\u0646",
        "\u062b\u0644\u0627\u062b\u0629",
        "\u0623\u0631\u0628\u0639\u0629",
        "\u062e\u0645\u0633\u0629",
        "\u0633\u062a\u0629",
        "\u0633\u0628\u0639\u0629",
        "\u062b\u0645\u0627\u0646\u064a\u0629",
        "\u062a\u0633\u0639\u0629",
    ),
    "msa": (
        "\u0635\u0641\u0631",
        "\u0648\u0627\u062d\u062f",
        "\u0627\u062b\u0646\u0627\u0646",
        "\u062b\u0644\u0627\u062b\u0629",
        "\u0623\u0631\u0628\u0639\u0629",
        "\u062e\u0645\u0633\u0629",
        "\u0633\u062a\u0629",
        "\u0633\u0628\u0639\u0629",
        "\u062b\u0645\u0627\u0646\u064a\u0629",
        "\u062a\u0633\u0639\u0629",
    ),
}
# 10 to 19: Saudi ashara, ihda'ash, ithna'ash, thalatta'ash, arba'ta'ash, khamsta'ash,
# sitta'ash, saba'ta'ash, thamanta'ash, tis'ta'ash; MSA ashara, ahada ashar, ithna ashar, and
# each unit then ashar.
_TEENS: Final[dict[Register, tuple[str, ...]]] = {
    "saudi": (
        "\u0639\u0634\u0631\u0629",
        "\u0627\u062d\u062f\u0639\u0634",
        "\u0627\u062b\u0646\u0639\u0634",
        "\u062b\u0644\u0637\u0639\u0634",
        "\u0623\u0631\u0628\u0639\u0637\u0639\u0634",
        "\u062e\u0645\u0633\u0637\u0639\u0634",
        "\u0633\u062a\u0637\u0639\u0634",
        "\u0633\u0628\u0639\u0637\u0639\u0634",
        "\u062b\u0645\u0646\u0637\u0639\u0634",
        "\u062a\u0633\u0639\u0637\u0639\u0634",
    ),
    "msa": (
        "\u0639\u0634\u0631\u0629",
        "\u0623\u062d\u062f \u0639\u0634\u0631",
        "\u0627\u062b\u0646\u0627 \u0639\u0634\u0631",
        "\u062b\u0644\u0627\u062b\u0629 \u0639\u0634\u0631",
        "\u0623\u0631\u0628\u0639\u0629 \u0639\u0634\u0631",
        "\u062e\u0645\u0633\u0629 \u0639\u0634\u0631",
        "\u0633\u062a\u0629 \u0639\u0634\u0631",
        "\u0633\u0628\u0639\u0629 \u0639\u0634\u0631",
        "\u062b\u0645\u0627\u0646\u064a\u0629 \u0639\u0634\u0631",
        "\u062a\u0633\u0639\u0629 \u0639\u0634\u0631",
    ),
}
# 20 to 90: Saudi ishrin to tis'in; MSA ishrun to tis'un.
_TENS: Final[dict[Register, tuple[str, ...]]] = {
    "saudi": (
        "",
        "",
        "\u0639\u0634\u0631\u064a\u0646",
        "\u062b\u0644\u0627\u062b\u064a\u0646",
        "\u0623\u0631\u0628\u0639\u064a\u0646",
        "\u062e\u0645\u0633\u064a\u0646",
        "\u0633\u062a\u064a\u0646",
        "\u0633\u0628\u0639\u064a\u0646",
        "\u062b\u0645\u0627\u0646\u064a\u0646",
        "\u062a\u0633\u0639\u064a\u0646",
    ),
    "msa": (
        "",
        "",
        "\u0639\u0634\u0631\u0648\u0646",
        "\u062b\u0644\u0627\u062b\u0648\u0646",
        "\u0623\u0631\u0628\u0639\u0648\u0646",
        "\u062e\u0645\u0633\u0648\u0646",
        "\u0633\u062a\u0648\u0646",
        "\u0633\u0628\u0639\u0648\u0646",
        "\u062b\u0645\u0627\u0646\u0648\u0646",
        "\u062a\u0633\u0639\u0648\u0646",
    ),
}
# 100 to 900: Saudi miya, mitain, thalath miya to tis' miya; MSA mi'a, mi'atan, thalathumi'a
# to tis'umi'a.
_HUNDREDS: Final[dict[Register, tuple[str, ...]]] = {
    "saudi": (
        "",
        "\u0645\u064a\u0629",
        "\u0645\u064a\u062a\u064a\u0646",
        "\u062b\u0644\u0627\u062b \u0645\u064a\u0629",
        "\u0623\u0631\u0628\u0639 \u0645\u064a\u0629",
        "\u062e\u0645\u0633 \u0645\u064a\u0629",
        "\u0633\u062a \u0645\u064a\u0629",
        "\u0633\u0628\u0639 \u0645\u064a\u0629",
        "\u062b\u0645\u0627\u0646 \u0645\u064a\u0629",
        "\u062a\u0633\u0639 \u0645\u064a\u0629",
    ),
    "msa": (
        "",
        "\u0645\u0626\u0629",
        "\u0645\u0626\u062a\u0627\u0646",
        "\u062b\u0644\u0627\u062b\u0645\u0626\u0629",
        "\u0623\u0631\u0628\u0639\u0645\u0626\u0629",
        "\u062e\u0645\u0633\u0645\u0626\u0629",
        "\u0633\u062a\u0645\u0626\u0629",
        "\u0633\u0628\u0639\u0645\u0626\u0629",
        "\u062b\u0645\u0627\u0646\u0645\u0626\u0629",
        "\u062a\u0633\u0639\u0645\u0626\u0629",
    ),
}
# A count of a feminine noun, 0 to 10: 3 to 10 in their short forms (thalath, arba', khams,
# sitt, sab', thaman, tis', ashr), and MSA's 1 and 2 (ihda, ithnatan) and 8 (thamani).
_FEMININE: Final[dict[Register, tuple[str, ...]]] = {
    "saudi": (
        "",
        "",
        "\u062b\u0646\u062a\u064a\u0646",
        "\u062b\u0644\u0627\u062b",
        "\u0623\u0631\u0628\u0639",
        "\u062e\u0645\u0633",
        "\u0633\u062a",
        "\u0633\u0628\u0639",
        "\u062b\u0645\u0627\u0646",
        "\u062a\u0633\u0639",
        "\u0639\u0634\u0631",
    ),
    "msa": (
        "",
        "\u0625\u062d\u062f\u0649",
        "\u0627\u062b\u0646\u062a\u0627\u0646",
        "\u062b\u0644\u0627\u062b",
        "\u0623\u0631\u0628\u0639",
        "\u062e\u0645\u0633",
        "\u0633\u062a",
        "\u0633\u0628\u0639",
        "\u062b\u0645\u0627\u0646\u064a",
        "\u062a\u0633\u0639",
        "\u0639\u0634\u0631",
    ),
}
# A thousand (alf), two thousand (Saudi alfain, MSA alfan), and the plural after 3 to 10
# (alaf); MSA's two hundred thousand (mi'ata alf) and the accusative after 11 to 99 (alfan).
_THOUSAND = "\u0623\u0644\u0641"
_TWO_THOUSAND: Final[dict[Register, str]] = {
    "saudi": "\u0623\u0644\u0641\u064a\u0646",
    "msa": "\u0623\u0644\u0641\u0627\u0646",
}
_THOUSANDS = "\u0622\u0644\u0627\u0641"
_MSA_TWO_HUNDRED_THOUSAND = "\u0645\u0626\u062a\u0627 \u0623\u0644\u0641"
_MSA_THOUSAND_COUNTED = "\u0623\u0644\u0641\u064b\u0627"
# The ordinals 1 to 10 with the article (al-awwal to al-ashir), and al-hadi, the 1 of 11 and
# of 21 and 31.
_MSA_ORDINALS: Final = (
    "",
    "\u0627\u0644\u0623\u0648\u0644",
    "\u0627\u0644\u062b\u0627\u0646\u064a",
    "\u0627\u0644\u062b\u0627\u0644\u062b",
    "\u0627\u0644\u0631\u0627\u0628\u0639",
    "\u0627\u0644\u062e\u0627\u0645\u0633",
    "\u0627\u0644\u0633\u0627\u062f\u0633",
    "\u0627\u0644\u0633\u0627\u0628\u0639",
    "\u0627\u0644\u062b\u0627\u0645\u0646",
    "\u0627\u0644\u062a\u0627\u0633\u0639",
    "\u0627\u0644\u0639\u0627\u0634\u0631",
)
_MSA_ORDINAL_ONE = "\u0627\u0644\u062d\u0627\u062f\u064a"
# wa, "and", written onto the word after it; al, the article; ashar, the ten of 11 to 19.
AND = "\u0648"
_THE = "\u0627\u0644"
_TEN = "\u0639\u0634\u0631"
# ithnata and ashra, the 2 and the ten of 12 when it counts a feminine noun.
_MSA_TWO_OF_TEN = "\u0627\u062b\u0646\u062a\u0627"
_TEN_FEMININE = "\u0639\u0634\u0631\u0629"


def _joined(*parts: str) -> str:
    """The parts said, each but the first after "and" (wa, written onto it)."""
    return f" {AND}".join(part for part in parts if part)


def _below_thousand(number: int, register: Register) -> str:
    """0 < `number` < 1000 in words."""
    hundreds = _HUNDREDS[register][number // 100]
    rest = number % 100
    if 10 <= rest < 20:
        return _joined(hundreds, _TEENS[register][rest - 10])
    unit = _UNITS[register][rest % 10] if rest % 10 else ""
    return _joined(hundreds, unit, _TENS[register][rest // 10])


def _thousands(count: int, register: Register) -> str:
    """`count` thousand (1 <= `count` <= 999) in words, its noun in the form the count takes."""
    if count == 1:
        return _THOUSAND
    if count == 2:
        return _TWO_THOUSAND[register]
    said = _below_thousand(count, register)
    if 3 <= count % 100 <= 10:  # a plural noun after 3 to 10
        return f"{said} {_THOUSANDS}"
    if register == "msa" and count == 200:
        return _MSA_TWO_HUNDRED_THOUSAND
    if register == "msa" and count % 100 >= 11:
        return f"{said} {_MSA_THOUSAND_COUNTED}"
    return f"{said} {_THOUSAND}"


def arabic_number(number: int, register: Register) -> str:
    """`number`, 0 to `HIGHEST`, in words in `register`: «ألفين وأربع مية وخمسين» in Saudi,
    «ألفان وأربعمئة وخمسون» in MSA. ValueError outside that range."""
    if not 0 <= number <= HIGHEST:
        raise ValueError(f"arabic_number says 0 to {HIGHEST}")
    if number == 0:
        return _UNITS[register][0]
    thousands = _thousands(number // 1000, register) if number >= 1000 else ""
    rest = _below_thousand(number % 1000, register) if number % 1000 else ""
    return _joined(thousands, rest)


def feminine_count(count: int, register: Register) -> str:
    """`count` (3 or more) as it counts a feminine noun: «خمس», «سبع» from 3 to 10; in MSA
    «إحدى عشرة», «اثنتا عشرة», «خمس وعشرون» past 10, in Saudi the plain number past 10."""
    if count <= 10:
        return _FEMININE[register][count]
    if register == "saudi" or count >= 100:
        return arabic_number(count, register)
    unit, ten = count % 10, count // 10
    if ten == 1:
        first = _MSA_TWO_OF_TEN if unit == 2 else _FEMININE["msa"][unit]
        return f"{first} {_TEN_FEMININE}"
    return _joined(_FEMININE["msa"][unit] if unit else "", _TENS["msa"][ten])


def msa_ordinal(day: int) -> str:
    """`day`, 1 to 31, as MSA's ordinal of a day of the month: «الأول», «الحادي عشر», «السابع
    عشر», «الحادي والعشرين»; its tens in the form a date says them («العشرين من ديسمبر»)."""
    if not 1 <= day <= 31:
        raise ValueError("msa_ordinal says a day of the month, 1 to 31")
    if day <= 10:
        return _MSA_ORDINALS[day]
    unit, ten = day % 10, day // 10
    first = _MSA_ORDINAL_ONE if unit == 1 else _MSA_ORDINALS[unit]
    if ten == 1:
        return f"{first} {_TEN}"
    tens = f"{_THE}{_TENS['saudi'][ten]}"
    return _joined(first, tens) if unit else tens
