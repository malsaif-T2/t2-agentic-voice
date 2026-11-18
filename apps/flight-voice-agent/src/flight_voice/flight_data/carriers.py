"""The airlines the real network names: each one's code, its names in English and Arabic, and
the other names a caller may give it; the four Saudi carriers first, then the foreign ones that
fly Saudi routes.

- `carrier(code, provider_name)` is the directory's entry for a flight number's prefix, or a
  carrier named as the provider names it when the directory lacks it.
- `by_name(text)` finds a carrier by one of its names (SerpApi's `plane_and_crew_by`).
- `named(said)` is the airline filter: the carriers whose names hold what the caller said, the
  generic words ("air", «طيران», "airlines" ...) dropped. An exact match wins; several matches
  are all given, so the tool asks which.
- `pronounced()` says the four Saudi codes, for when the model reads a flight's code out. The
  foreign codes are not mapped: a whole-word map of "AI", "ME" or "PC" would hit other words,
  and the instructions say a flight number with its airline's name ("Saudia 1020").

Arabic is written plainly, as the app's other word modules write it.
"""

from __future__ import annotations

from typing import Final

from t2_agentic_voice.languages import normalize_arabic

from flight_voice.flight_data.model import Carrier

__all__ = ["CARRIERS", "by_name", "carrier", "named", "pronounced"]


def _c(code: str, en: str, ar: str, *aliases: str) -> Carrier:
    return Carrier(code=code, name_en=en, name_ar=ar, aliases=aliases)


CARRIERS: Final[dict[str, Carrier]] = {
    c.code: c
    for c in (
        _c("SV", "Saudia", "السعودية", "Saudi Airlines", "الخطوط السعودية", "السعودي"),
        _c("XY", "flynas", "طيران ناس", "فلاي ناس", "ناس", "fly nas"),
        _c("F3", "flyadeal", "طيران أديل", "فلاي أديل", "أديل", "fly adeal", "flyadil"),
        _c("RX", "Riyadh Air", "طيران الرياض", "الرياض للطيران"),
        _c("EK", "Emirates", "طيران الإمارات", "الإماراتية"),
        _c("QR", "Qatar Airways", "الخطوط الجوية القطرية", "القطرية"),
        _c("EY", "Etihad Airways", "الاتحاد للطيران", "الاتحاد", "Etihad"),
        _c("GF", "Gulf Air", "طيران الخليج"),
        _c("KU", "Kuwait Airways", "الخطوط الجوية الكويتية", "الكويتية"),
        _c("MS", "EgyptAir", "مصر للطيران", "Egypt Air"),
        _c("TK", "Turkish Airlines", "الخطوط الجوية التركية", "التركية"),
        _c("WY", "Oman Air", "الطيران العماني", "العماني"),
        _c("RJ", "Royal Jordanian", "الملكية الأردنية", "الأردنية"),
        _c("ME", "Middle East Airlines", "طيران الشرق الأوسط", "MEA"),
        _c("PC", "Pegasus", "بيغاسوس", "Pegasus Airlines"),
        _c("BA", "British Airways", "الخطوط الجوية البريطانية", "البريطانية"),
        _c("AF", "Air France", "إير فرانس"),
        _c("LH", "Lufthansa", "لوفتهانزا"),
        _c("KL", "KLM", "كي إل إم", "KLM Royal Dutch Airlines"),
        _c("AI", "Air India", "طيران الهند", "India"),
        _c("IX", "Air India Express", "طيران الهند إكسبريس", "India Express"),
        _c("6E", "IndiGo", "إنديغو", "Indigo"),
        _c("PK", "PIA", "الخطوط الجوية الباكستانية", "Pakistan International Airlines"),
        _c("FZ", "flydubai", "فلاي دبي", "fly dubai"),
        _c("G9", "Air Arabia", "العربية للطيران", "Arabia"),
        _c("J9", "Jazeera Airways", "طيران الجزيرة", "الجزيرة", "Jazeera"),
        _c("ET", "Ethiopian Airlines", "الخطوط الجوية الإثيوبية", "الإثيوبية", "Ethiopian"),
        _c("MH", "Malaysia Airlines", "الخطوط الجوية الماليزية", "الماليزية"),
        _c("SQ", "Singapore Airlines", "الخطوط الجوية السنغافورية", "السنغافورية"),
        _c("UL", "SriLankan Airlines", "الخطوط السريلانكية", "Sri Lankan"),
        _c("BG", "Biman Bangladesh Airlines", "بيمان بنغلاديش", "Biman"),
        _c("TU", "Tunisair", "الخطوط التونسية", "التونسية"),
        _c("AT", "Royal Air Maroc", "الخطوط الملكية المغربية", "المغربية"),
        _c("AH", "Air Algérie", "الخطوط الجوية الجزائرية", "Air Algerie", "الجزائرية"),
        _c("GA", "Garuda Indonesia", "جارودا الإندونيسية", "Garuda"),
        _c("PR", "Philippine Airlines", "الخطوط الجوية الفلبينية", "الفلبينية"),
        _c("TG", "Thai Airways", "الخطوط الجوية التايلاندية", "Thai", "التايلاندية"),
        _c("KQ", "Kenya Airways", "الخطوط الجوية الكينية", "الكينية"),
        _c("OV", "SalamAir", "طيران السلام", "Salam Air"),
        _c("SM", "Air Cairo", "إير كايرو"),
        _c("NP", "Nile Air", "طيران النيل"),
        _c("NE", "Nesma Airlines", "طيران ناسما", "Nesma"),
        _c("VF", "AJet", "أجيت"),
        _c("3L", "Air Arabia Abu Dhabi", "العربية للطيران أبوظبي"),
        _c("9P", "Fly Jinnah", "فلاي جناح", "Jinnah"),
        _c("PA", "Airblue", "إير بلو", "Air Blue"),
        _c("SG", "SpiceJet", "سبايس جت", "Spice Jet"),
        _c("QP", "Akasa Air", "أكاسا إير", "Akasa"),
        _c("BS", "US-Bangla Airlines", "يو إس بنغلا", "US Bangla"),
    )
}

# Words that say "an airline" rather than which: dropped before a name is matched.
_GENERIC: Final = frozenset(
    normalize_arabic(w)
    for w in (
        "air",
        "airline",
        "airlines",
        "airways",
        "flight",
        "fly",
        "طيران",
        "الطيران",
        "للطيران",
        "الخطوط",
        "خطوط",
        "الجوية",
        "فلاي",
    )
)
# How the four Saudi codes are said, when the model reads a flight's code out.
_SAID: Final[dict[str, dict[str, str]]] = {
    "SV": {"en": "ess vee", "ar": "إس في"},
    "XY": {"en": "ex why", "ar": "إكس واي"},
    "F3": {"en": "eff three", "ar": "إف ثري"},
    "RX": {"en": "ar ex", "ar": "آر إكس"},
}
_MIN_LETTERS: Final = 3


def _words(text: str) -> tuple[str, ...]:
    """`text` normalized, as words, with the generic words dropped."""
    return tuple(w for w in normalize_arabic(text).split() if w not in _GENERIC)


def _names(c: Carrier) -> tuple[tuple[str, ...], ...]:
    """Each of a carrier's names, as words with the generic ones dropped; empty ones left out."""
    found = (_words(n) for n in (c.name_en, c.name_ar, *c.aliases))
    return tuple(dict.fromkeys(n for n in found if n))


_EXACT: Final[dict[str, tuple[tuple[str, ...], ...]]] = {c: _names(v) for c, v in CARRIERS.items()}
_PLAIN: Final[dict[str, str]] = {
    normalize_arabic(n): code
    for code, c in CARRIERS.items()
    for n in (c.name_en, c.name_ar, *c.aliases)
}


def carrier(code: str, provider_name: str | None = None) -> Carrier:
    """The carrier of a flight number's prefix: the directory's, or one named as the provider
    names it (its code when it gives no name) when the directory lacks it."""
    known = CARRIERS.get(code)
    if known is not None:
        return known
    name = (provider_name or "").strip() or code
    return Carrier(code=code, name_en=name, name_ar=name)


def by_name(text: str) -> Carrier | None:
    """The carrier one of whose names `text` is (any case, either script), or None. A text such
    as "Horizon Air as Alaska Horizon" is read by its part before " as " too."""
    for part in (text, text.split(" as ")[0]):
        code = _PLAIN.get(normalize_arabic(part))
        if code is not None:
            return CARRIERS[code]
    return None


def named(said: str) -> tuple[Carrier, ...]:
    """The carriers `said` names, for the airline filter: an exact match of a name (the generic
    words dropped) or a code wins; otherwise each carrier one of whose names holds a word of
    `said` of at least three letters, all of them, in the directory's order. None for a said
    that is only generic words («طيران», "air")."""
    words = _words(said)
    if not words:
        return ()
    exact = tuple(
        c for code, c in CARRIERS.items() if words in _EXACT[code] or words == (code.lower(),)
    )
    if exact:
        return exact
    codes = {w for w in words if w.upper() in CARRIERS}
    long = {w for w in words if len(w) >= _MIN_LETTERS}
    found = []
    for code, c in CARRIERS.items():
        held = {w for name in _EXACT[code] for w in name}
        if code.lower() in codes or long & held:
            found.append(c)
    return tuple(found)


def pronounced() -> dict[str, dict[str, str]]:
    """How the four Saudi codes are said in each language ("ess vee", «إس في»)."""
    return {code: dict(said) for code, said in _SAID.items()}
