"""The airports abroad that Saudi routes reach, for the place directory (places.py): the cities
with several airports (Dubai, London, Paris, Istanbul, New York, Milan, Goa), searched together
under the city's name and alone under the airport's; the cities of one airport; the country
words of a country with one main airport (Bahrain, Kuwait, Qatar); and every name and alias of
the mock airline's ten (airline/airports.py), under the same code.

Arabic is written plainly, as the app's other word modules write it.
"""

from __future__ import annotations

from typing import Final

from flight_voice.flight_data.rows import CityRow, city, port

__all__ = ["WORLD"]

_SEVERAL: Final[tuple[CityRow, ...]] = (
    city(
        "Dubai",
        "دبي",
        "AE",
        port("DXB", "Dubai International", "مطار دبي الدولي"),
        port("DWC", "Al Maktoum International", "مطار آل مكتوم الدولي", "Dubai World Central"),
        aliases=("ديبي",),
    ),
    city(
        "London",
        "لندن",
        "GB",
        port("LHR", "Heathrow", "مطار هيثرو", "هيثرو"),
        port("LGW", "Gatwick", "مطار جاتويك", "جاتويك"),
        port("STN", "Stansted", "مطار ستانستد", "ستانستد"),
    ),
    city(
        "Paris",
        "باريس",
        "FR",
        port("CDG", "Charles de Gaulle", "مطار شارل ديغول"),
        port("ORY", "Orly", "مطار أورلي", "أورلي"),
        aliases=("فرنسا", "France"),
    ),
    city(
        "Istanbul",
        "إسطنبول",
        "TR",
        port("IST", "Istanbul Airport", "مطار إسطنبول"),
        port("SAW", "Sabiha Gokcen", "مطار صبيحة كوكجن", "Sabiha Gökçen", "صبيحة"),
        aliases=("اسطنبول", "تركيا", "Turkey", "Turkiye"),
    ),
    city(
        "New York",
        "نيويورك",
        "US",
        port("JFK", "John F. Kennedy", "مطار جون كينيدي", "Kennedy"),
        port("EWR", "Newark", "مطار نيوارك", "نيوارك"),
    ),
    city(
        "Milan",
        "ميلانو",
        "IT",
        port("MXP", "Malpensa", "مطار مالبينسا"),
        port("LIN", "Linate", "مطار ليناتي"),
        aliases=("Milano", "ميلان"),
    ),
    city(
        "Goa",
        "غوا",
        "IN",
        port("GOI", "Dabolim", "مطار دابوليم"),
        port("GOX", "Manohar International", "مطار مانوهار الدولي", "Mopa"),
    ),
)

_ONE: Final[tuple[CityRow, ...]] = (
    city(
        "Abu Dhabi",
        "أبوظبي",
        "AE",
        port("AUH", "Zayed International", "مطار زايد الدولي"),
        aliases=("أبو ظبي", "Abudhabi"),
    ),
    city("Sharjah", "الشارقة", "AE", port("SHJ", "Sharjah International", "مطار الشارقة الدولي")),
    city(
        "Doha",
        "الدوحة",
        "QA",
        port("DOH", "Hamad International", "مطار حمد الدولي"),
        aliases=("الدوحه", "قطر", "Qatar"),
    ),
    city(
        "Bahrain",
        "البحرين",
        "BH",
        port("BAH", "Bahrain International", "مطار البحرين الدولي"),
        aliases=("Manama", "المنامة"),
    ),
    city(
        "Kuwait",
        "الكويت",
        "KW",
        port("KWI", "Kuwait International", "مطار الكويت الدولي"),
        aliases=("Kuwait City",),
    ),
    city("Muscat", "مسقط", "OM", port("MCT", "Muscat International", "مطار مسقط الدولي")),
    city("Salalah", "صلالة", "OM", port("SLL", "Salalah International", "مطار صلالة")),
    city("Amman", "عمان", "JO", port("AMM", "Queen Alia International", "مطار الملكة علياء")),
    city(
        "Cairo",
        "القاهرة",
        "EG",
        port("CAI", "Cairo International", "مطار القاهرة الدولي"),
        aliases=("القاهره", "مصر", "Egypt"),
    ),
    city("Alexandria", "الإسكندرية", "EG", port("HBE", "Borg El Arab", "مطار برج العرب")),
    city("Beirut", "بيروت", "LB", port("BEY", "Rafic Hariri International", "مطار رفيق الحريري")),
    city("Frankfurt", "فرانكفورت", "DE", port("FRA", "Frankfurt Airport", "مطار فرانكفورت")),
    city("Munich", "ميونخ", "DE", port("MUC", "Munich Airport", "مطار ميونخ")),
    city("Amsterdam", "أمستردام", "NL", port("AMS", "Schiphol", "مطار سخيبول")),
    city("Madrid", "مدريد", "ES", port("MAD", "Barajas", "مطار باراخاس")),
    city("Barcelona", "برشلونة", "ES", port("BCN", "El Prat", "مطار برشلونة")),
    city("Rome", "روما", "IT", port("FCO", "Fiumicino", "مطار فيوميتشينو")),
    city("Geneva", "جنيف", "CH", port("GVA", "Geneva Airport", "مطار جنيف")),
    city("Zurich", "زيورخ", "CH", port("ZRH", "Zurich Airport", "مطار زيورخ")),
    city("Vienna", "فيينا", "AT", port("VIE", "Vienna International", "مطار فيينا الدولي")),
    city("Trabzon", "طرابزون", "TR", port("TZX", "Trabzon Airport", "مطار طرابزون")),
    city("Antalya", "أنطاليا", "TR", port("AYT", "Antalya Airport", "مطار أنطاليا")),
    city("Sarajevo", "سراييفو", "BA", port("SJJ", "Sarajevo International", "مطار سراييفو")),
    city("Baku", "باكو", "AZ", port("GYD", "Heydar Aliyev International", "مطار حيدر علييف")),
    city("Tbilisi", "تبليسي", "GE", port("TBS", "Tbilisi International", "مطار تبليسي")),
    city(
        "Mumbai",
        "مومباي",
        "IN",
        port("BOM", "Mumbai International", "مطار مومباي الدولي"),
        aliases=("بومباي", "الهند", "Bombay", "India"),
    ),
    city(
        "Delhi",
        "دلهي",
        "IN",
        port("DEL", "Indira Gandhi International", "مطار إنديرا غاندي"),
        aliases=("New Delhi", "نيودلهي"),
    ),
    city(
        "Bangalore",
        "بنغالور",
        "IN",
        port("BLR", "Kempegowda International", "مطار كيمبيغودا"),
        aliases=("Bengaluru",),
    ),
    city(
        "Hyderabad",
        "حيدر أباد",
        "IN",
        port("HYD", "Rajiv Gandhi International", "مطار راجيف غاندي"),
        aliases=("حيدرآباد",),
    ),
    city(
        "Kochi",
        "كوتشي",
        "IN",
        port("COK", "Cochin International", "مطار كوتشين الدولي"),
        aliases=("Cochin", "كوشين"),
    ),
    city("Karachi", "كراتشي", "PK", port("KHI", "Jinnah International", "مطار جناح الدولي")),
    city("Lahore", "لاهور", "PK", port("LHE", "Allama Iqbal International", "مطار العلامة إقبال")),
    city(
        "Islamabad",
        "إسلام آباد",
        "PK",
        port("ISB", "Islamabad International", "مطار إسلام آباد"),
        aliases=("اسلام اباد",),
    ),
    city("Dhaka", "دكا", "BD", port("DAC", "Hazrat Shahjalal International", "مطار شاه جلال")),
    city(
        "Colombo", "كولومبو", "LK", port("CMB", "Bandaranaike International", "مطار باندارانايكا")
    ),
    city("Kathmandu", "كاتماندو", "NP", port("KTM", "Tribhuvan International", "مطار تريبهوفان")),
    city(
        "Male",
        "ماليه",
        "MV",
        port("MLE", "Velana International", "مطار فيلانا الدولي"),
        aliases=("Malé", "Maldives", "المالديف", "جزر المالديف"),
    ),
    city(
        "Kuala Lumpur",
        "كوالالمبور",
        "MY",
        port("KUL", "Kuala Lumpur International", "مطار كوالالمبور"),
        aliases=("كوالا لمبور", "Malaysia", "ماليزيا"),
    ),
    city(
        "Jakarta", "جاكرتا", "ID", port("CGK", "Soekarno-Hatta International", "مطار سوكارنو هاتا")
    ),
    city(
        "Bali",
        "بالي",
        "ID",
        port("DPS", "Ngurah Rai International", "مطار نغوراه راي"),
        aliases=("Denpasar", "دنباسار"),
    ),
    city("Manila", "مانيلا", "PH", port("MNL", "Ninoy Aquino International", "مطار نينوي أكينو")),
    city(
        "Singapore",
        "سنغافورة",
        "SG",
        port("SIN", "Changi", "مطار شانغي"),
        aliases=("سنغافوره", "سنقافورة"),
    ),
    city(
        "Bangkok",
        "بانكوك",
        "TH",
        port("BKK", "Suvarnabhumi", "مطار سوفارنابومي"),
        aliases=("Thailand", "تايلاند"),
    ),
    city("Phuket", "بوكيت", "TH", port("HKT", "Phuket International", "مطار بوكيت الدولي")),
    city("Washington", "واشنطن", "US", port("IAD", "Dulles International", "مطار دالاس الدولي")),
    city(
        "Los Angeles",
        "لوس أنجلوس",
        "US",
        port("LAX", "Los Angeles International", "مطار لوس أنجلوس"),
    ),
    city("Toronto", "تورونتو", "CA", port("YYZ", "Pearson International", "مطار بيرسون الدولي")),
    city("Addis Ababa", "أديس أبابا", "ET", port("ADD", "Bole International", "مطار بولي الدولي")),
    city(
        "Nairobi", "نيروبي", "KE", port("NBO", "Jomo Kenyatta International", "مطار جومو كينياتا")
    ),
    city("Khartoum", "الخرطوم", "SD", port("KRT", "Khartoum International", "مطار الخرطوم الدولي")),
    city("Tunis", "تونس", "TN", port("TUN", "Tunis Carthage", "مطار تونس قرطاج")),
    city(
        "Casablanca",
        "الدار البيضاء",
        "MA",
        port("CMN", "Mohammed V International", "مطار محمد الخامس"),
    ),
    city("Algiers", "الجزائر", "DZ", port("ALG", "Houari Boumediene", "مطار هواري بومدين")),
)

WORLD: Final[tuple[CityRow, ...]] = (*_SEVERAL, *_ONE)
