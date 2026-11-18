"""Saudi Arabia's airports, for the place directory (places.py): each city in English and
Arabic, its airport's own name, and the names callers give it (Khobar and Dhahran for Dammam,
Khamis Mushait for Abha, Buraidah for Qassim, the Najdi spellings «الطايف», «حايل», «جيزان»,
«الحسا»). Riyadh is first: it is the directory's home.

Arabic is written plainly, as the app's other word modules write it.
"""

from __future__ import annotations

from typing import Final

from flight_voice.flight_data.rows import CityRow, city, port

__all__ = ["SAUDI"]

SAUDI: Final[tuple[CityRow, ...]] = (
    city(
        "Riyadh",
        "الرياض",
        "SA",
        port("RUH", "King Khalid International", "مطار الملك خالد الدولي"),
        aliases=("رياض", "Riyad"),
    ),
    city(
        "Jeddah",
        "جدة",
        "SA",
        port("JED", "King Abdulaziz International", "مطار الملك عبدالعزيز الدولي"),
        aliases=("جده", "Jedda", "Jidda"),
    ),
    city(
        "Dammam",
        "الدمام",
        "SA",
        port("DMM", "King Fahd International", "مطار الملك فهد الدولي"),
        aliases=("دمام", "Khobar", "Al Khobar", "الخبر", "Dhahran", "الظهران"),
    ),
    city(
        "Madinah",
        "المدينة المنورة",
        "SA",
        port("MED", "Prince Mohammad bin Abdulaziz", "مطار الأمير محمد بن عبدالعزيز"),
        aliases=("Medina", "Madina", "Al Madinah", "المدينة"),
    ),
    city(
        "Abha",
        "أبها",
        "SA",
        port("AHB", "Abha International", "مطار أبها الدولي"),
        aliases=("Khamis Mushait", "Khamis Mushayt", "خميس مشيط"),
    ),
    city(
        "Taif",
        "الطائف",
        "SA",
        port("TIF", "Taif International", "مطار الطائف الدولي"),
        aliases=("الطايف", "At Taif", "Al Taif", "طائف"),
    ),
    city(
        "Tabuk",
        "تبوك",
        "SA",
        port("TUU", "Prince Sultan bin Abdulaziz", "مطار الأمير سلطان بن عبدالعزيز"),
    ),
    city(
        "Jazan",
        "جازان",
        "SA",
        port("GIZ", "King Abdullah bin Abdulaziz", "مطار الملك عبدالله بن عبدالعزيز"),
        aliases=("Jizan", "Gizan", "جيزان"),
    ),
    city(
        "Qassim",
        "القصيم",
        "SA",
        port("ELQ", "Prince Naif bin Abdulaziz International", "مطار الأمير نايف بن عبدالعزيز"),
        aliases=("Al Qassim", "Gassim", "Buraidah", "Buraydah", "بريدة", "Unaizah", "عنيزة"),
    ),
    city(
        "Al-Jouf",
        "الجوف",
        "SA",
        port("AJF", "Al-Jouf Domestic", "مطار الجوف"),
        aliases=("Jouf", "Al Jawf", "Sakaka", "سكاكا"),
    ),
    city(
        "Hail",
        "حائل",
        "SA",
        port("HAS", "Hail International", "مطار حائل الدولي"),
        aliases=("حايل", "Hayel", "Ha'il"),
    ),
    city(
        "Yanbu",
        "ينبع",
        "SA",
        port("YNB", "Prince Abdul Mohsin bin Abdulaziz", "مطار الأمير عبدالمحسن بن عبدالعزيز"),
    ),
    city(
        "Red Sea",
        "البحر الأحمر",
        "SA",
        port("RSI", "Red Sea International", "مطار البحر الأحمر الدولي"),
    ),
    city("NEOM", "نيوم", "SA", port("NUM", "NEOM Bay", "مطار خليج نيوم")),
    city(
        "AlUla",
        "العلا",
        "SA",
        port("ULH", "Prince Abdul Majeed bin Abdulaziz", "مطار الأمير عبدالمجيد بن عبدالعزيز"),
        aliases=("Al Ula", "Al-Ula"),
    ),
    city("Najran", "نجران", "SA", port("EAM", "Najran Domestic", "مطار نجران")),
    city("Bisha", "بيشة", "SA", port("BHH", "Bisha Domestic", "مطار بيشة")),
    city("Turaif", "طريف", "SA", port("TUI", "Turaif Domestic", "مطار طريف")),
    city("Arar", "عرعر", "SA", port("RAE", "Arar Domestic", "مطار عرعر")),
    city(
        "Gurayat",
        "القريات",
        "SA",
        port("URY", "Gurayat Domestic", "مطار القريات"),
        aliases=("Qurayyat", "Al Qurayyat"),
    ),
    city(
        "Wadi al-Dawasir",
        "وادي الدواسر",
        "SA",
        port("WAE", "Wadi al-Dawasir Domestic", "مطار وادي الدواسر"),
    ),
    city(
        "Al Qaisumah",
        "القيصومة",
        "SA",
        port("AQI", "Al Qaisumah Domestic", "مطار القيصومة"),
        aliases=("Qaisumah", "Hafar Al Batin", "حفر الباطن"),
    ),
    city("Dawadmi", "الدوادمي", "SA", port("DWD", "Dawadmi Domestic", "مطار الدوادمي")),
    city(
        "Al Baha",
        "الباحة",
        "SA",
        port("ABT", "Al Baha Domestic", "مطار الباحة"),
        aliases=("Baha", "Al-Baha"),
    ),
    city("Sharurah", "شرورة", "SA", port("SHW", "Sharurah Domestic", "مطار شرورة")),
    city(
        "Al-Ahsa",
        "الأحساء",
        "SA",
        port("HOF", "Al-Ahsa International", "مطار الأحساء الدولي"),
        aliases=("الحسا", "Al Hasa", "Ahsa", "Hofuf", "الهفوف"),
    ),
)
