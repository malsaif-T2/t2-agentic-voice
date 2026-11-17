"""What the booking says, in Saudi Arabic (`ar-SA`), in MSA (`ar`), which an `ar-SA` reply says
to a caller who speaks MSA, and in English: the read-back, a summary and a closing question;
`done`, filled from the airline's real reply; `sending`, said while the write runs, which never
says it is done; the `failed`, `unknown` and `declined` lines; and the phrases that would claim
a booking (`CLAIMS`), which the output guard blocks unless this call's record holds one.

- **The read-back states every value booked**, in words the app renders (booking/draft.py), and
  always the trip's kind, «رايح جاي» / «رايح بس», "round trip" / "one way", so a wrong one way is
  heard either way. It is the one summary of the trip: the caller hears it and its total once,
  and says yes once. It says no word that holds no value: no lead verb ("I'll book"), the
  return's city and month not said again, "Total" for "The total is".
- **Its closing question and its ask-again line hold the action's own send word**
  (`SEND_WORDS`: book it, and the confirm verbs «أكد», «أكدها», «أكد الحجز», «احجز», "confirm"),
  so «إي احجزها», "yes, book it" over it counts, and the library's own ask-again line (which
  fits any action) is never said for a booking; no other line holds a stop, wait, repeat,
  listening, yes or send word, so no line's echo is heard as one: no line says «أي» (any),
  which the yes rule's form reads as «إي» (yes).
- **`done` never says the reference**: the caller hears it only when they ask, from a result
  that holds it. `unknown` says no number (invariant 6).
- **A claim** is only a phrase that cannot sit in a negative, since the guard reads negation in
  Arabic alone: no bare "is booked" or "has been booked", which the talker's honest "nothing is
  booked" holds. No reference phrase is a claim: rule B already lets a reference be said only
  when a result of this call holds it.

Saudi lines are short, plain and Saudi; MSA's as short, with no dialect form. Arabic is written
plainly, as the app's other word modules write it.
"""

from __future__ import annotations

from typing import Final

from t2_agentic_voice import Claims, ReadBack, Say

# The send words the closing question and the ask-again hold, and the confirm verbs a caller
# says for a booking, the same in both Arabic wordings, by primary code: aHjizha (book it),
# akkid (confirm), akkidha (confirm it), akkid al-Hajz (confirm the booking), iHjiz (book).
SEND_WORDS: Final = {
    "ar": ["احجزها", "أحجزها", "أكد", "أكدها", "أكد الحجز", "احجز"],
    "en": ["book it", "confirm", "confirm it"],
}

READ_BACK: Final = ReadBack(
    {
        # ... 'ala ...: (for) ... in ..., the trip's kind: the route, the legs. The total ...;
        # tabeeni aHjizha: do you want me to book it?
        "ar-SA": (
            "{party_ar_sa} على {cabin}، {trip_kind_ar_sa}: {route_ar_sa}، "
            "{outbound_ar_sa}{return_ar_sa}. المجموع {total_ar_sa}.",
            "تبيني أحجزها؟",
        ),
        # ... fi ...: (for) ... in ...; hal aHjizuha laka: shall I book it?
        "ar": (
            "{party_ar} في {cabin}، {trip_kind_ar}: {route_ar}، {outbound_ar}{return_ar}. "
            "المجموع {total_ar}.",
            "هل أحجزها لك؟",
        ),
        "en": (
            "For {party_en} in {cabin}, {trip_kind_en}: {route_en}, "
            "{outbound_en}{return_en}. Total {total_en}.",
            "Shall I book it?",
        ),
    },
    send_words=SEND_WORDS,
    asked_again=Say(
        {
            # al-ma'dhira, ma waDaH li raddak. tabeeni aHjizha: sorry, your answer wasn't clear
            # to me. Do you want me to book it?
            "ar-SA": "المعذرة، ما وضح لي ردك. تبيني أحجزها؟",
            # 'udhran, lam yattaDiH li radduk. hal aHjizuha laka: the same, in MSA
            "ar": "عذرًا، لم يتضح لي ردك. هل أحجزها لك؟",
            "en": "Sorry, I didn't catch that. Shall I book it?",
        }
    ),
)
DONE: Final = Say(
    {
        # tamm, riHlatak ... jaahza: done, your trip ... is ready.
        "ar-SA": "تم، رحلتك {city_ar_sa} {when_ar_sa} جاهزة.",
        "ar": "تم، رحلتك {city_ar} {when_ar} جاهزة.",
        "en": "Done. Your trip {city_en}, {when_en}, is all set.",
    }
)
SENDING: Final = Say(
    {
        "ar-SA": "جاري الحجز الحين.",  # jaari al-Hajz al-Heen: making the booking now
        "ar": "جارٍ الحجز الآن.",  # jaarin al-Hajzu al-aan: the same, in MSA
        "en": "Making the booking now.",
    }
)
FAILED: Final = Say(
    {
        # Sadly the booking system turned the request down, so the booking was not made.
        "ar-SA": "للأسف نظام الحجز رفض الطلب، فما صار الحجز.",
        # lil-asaf rafaDa niDHaamu al-Hajzi aT-Talab, fa-lam yujra al-Hajz: the same, in MSA
        "ar": "للأسف رفض نظام الحجز الطلب، فلم يُجرَ الحجز.",
        "en": "Unfortunately the booking system turned it down, so no booking was made.",
    }
)
UNKNOWN: Final = Say(
    {
        # I could not make sure the booking went through, so don't count on it now.
        "ar-SA": "ما قدرت أتأكد إذا الحجز وصل، فلا تعتمد عليه الحين.",
        # lam atamakkan min at-ta'akkud min wuSuul al-Hajz, fa-la ta'tamid 'alayhi al-aan
        "ar": "لم أتمكن من التأكد من وصول الحجز، فلا تعتمد عليه الآن.",
        "en": "I can't tell whether the booking went through, so please don't count on it yet.",
    }
)
DECLINED: Final = Say(
    {
        # I did not make the booking. If you want to come back to it, tell me.
        "ar-SA": "ما سويت الحجز. إذا تبي ترجع له، قل لي.",
        # lam ujri al-Hajz. in aradta al-'awdata ilayhi fa-akhbirni: the same, in MSA
        "ar": "لم أُجرِ الحجز. إن أردت العودة إليه فأخبرني.",
        "en": "No booking was made. Tell me if you'd like to come back to it.",
    }
)
CLAIMS: Final = Claims(
    {
        "ar-SA": [
            "حجزت لك",  # Hajazt lak: I booked for you
            "حجزتها لك",  # I booked it for you
            "تم الحجز",  # the booking is done
            "تم حجز",  # ... was booked
            "انحجزت",  # it got booked
            "أكدت لك الحجز",  # I confirmed the booking for you
            "حجزك مؤكد",  # your booking is confirmed
        ],
        "ar": [
            "حجزت لك",  # Hajaztu laka: I booked for you
            "تم الحجز",  # the booking is done
            "تم تأكيد الحجز",  # the booking was confirmed
        ],
        "en": [
            "I've booked",
            "I have booked",
            "I booked",
            "you're booked",
            "you are booked",
            "your trip is booked",
            "your flight is booked",
            "your trip has been booked",
            "your booking is confirmed",
            "booking confirmed",
            "reservation is confirmed",
        ],
    }
)
