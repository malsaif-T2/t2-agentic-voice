"""The words the yes rule reads (the design's 8.3): each language's yes words, send words, no
words and fillers, by the primary code the interruption rule's lists use (`ar` for both Arabic
presets, `en`).

They are kept out of domain/words.py's five kinds so that those lists, and the interruption rule
measured on them, stay exactly as they are (D-080); the no words and the fillers start from
those lists' no words and listening sounds, read and never changed. The action's own
`send_words` and the `words` group's `yes` and `send` are added to the preset's
(`consent_words`).

The presets' words are the prototype's (its `voice/rules.py`, read only: D-010): its words for
a yes, for sending, for a no and for filling, kept to what any action can use (no ticket's
noun), with the Saudi and the Modern Standard Arabic words in the one Arabic list, as
domain/words.py's are. Each is written in the rule's form (`rule_form`), the Arabic with `\\u`
escapes, each comment giving the word's sound and meaning, then its letters. A send word is
never a yes alone: the closing question holds one, and its echo must not confirm anything.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.words import PRESET_WORDS, rule_form


class ConsentWords(BaseModel):
    """One language's lists for one read-back, each in the rule's form (domain/words.py's
    `rule_form`): `yes`, `send` (the preset's, the settings' and the action's), `no`, and the
    `fillers` a yes may stand among. A word is brought to the rule's form as the lists are
    built, each once; one that says nothing in it is dropped."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    yes: tuple[str, ...]
    send: tuple[str, ...]
    no: tuple[str, ...]
    fillers: tuple[str, ...]

    @field_validator("yes", "send", "no", "fillers")
    @classmethod
    def _in_rule_form(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(form for word in value if (form := rule_form(word))))


# The Arabic lists, both Arabic presets'.
_ARABIC_YES = (
    "نعم",  # na'am, yes: noon, ain, meem
    "ايه",  # eeh, yes (Saudi): alef, yeh, heh
    "اي",  # ay, yes (Saudi): alef, yeh
    "ايوه",  # aywa, yes (Saudi): alef, yeh, waw, heh
    "ايوا",  # aywa, yes: alef, yeh, waw, alef
    "اكيد",  # akeed, sure: alef, kaf, yeh, dal
    "موافق",  # muwaafiq, agreed: meem, waw, alef, feh, qaf
    "طبعا",  # tab'an, of course: tah, beh, ain, alef
    # bit-ta'keed, certainly (MSA): beh, alef, lam, teh, alef, kaf, yeh, dal
    "بالتاكيد",
)
_ARABIC_SEND = (
    "ارسل",  # arsil, send: alef, reh, seen, lam
    "ارسلها",  # arsilha, send it: alef, reh, seen, lam, heh, alef
    "ارسله",  # arsilah, send it: alef, reh, seen, lam, heh
    "قدمها",  # qaddimha, submit it: qaf, dal, meem, heh, alef
    "قدمه",  # qaddimah, submit it: qaf, dal, meem, heh
    # i'tamidha, approve it: alef, ain, teh, meem, dal, heh, alef; and without the alef
    "اعتمدها",
    "اعتمده",
    "نفذها",  # naffidhha, carry it out: noon, feh, thal, heh, alef
    "نفذه",  # naffidhah, carry it out: noon, feh, thal, heh
    "سجلها",  # sajjilha, register it: seen, jeem, lam, heh, alef
    "سجله",  # sajjilah, register it: seen, jeem, lam, heh
    "توكل",  # tawakkal, go ahead (Saudi): teh, waw, kaf, lam
    # tawakkal 'ala allah, go ahead (Saudi): teh, waw, kaf, lam; ain, lam, yeh; alef, lam,
    # lam, heh
    "توكل علي الله",
    # qum bi-irsaalih, send it (MSA): qaf, meem; beh, alef, reh, seen, alef, lam, heh
    "قم بارساله",
)
# Beside domain/words.py's Arabic no words.
_ARABIC_NO = (
    "كلا",  # kalla, no (MSA): kaf, lam, alef
    "ابدا",  # abadan, never: alef, beh, dal, alef
    # alghiha, cancel it (Saudi): alef, lam, ghain, yeh, heh, alef; and without the alef
    "الغيها",
    "الغيه",
    "مابي",  # maabi, I don't want (Saudi): meem, alef, beh, yeh
    "مابغي",  # maabghi, I don't want (Saudi): meem, alef, beh, ghain, yeh
    # la tirsilha, don't send it: lam, alef; teh, reh, seen, lam, heh, alef; and without alef
    "لا ترسلها",
    "لا ترسله",
)
# Beside domain/words.py's Arabic listening sounds.
_ARABIC_FILLERS = (
    "لو سمحت",  # law samaht, please: lam, waw; seen, meem, hah, teh
    "من فضلك",  # min fadlak, please: meem, noon; feh, dad, lam, kaf
    "رجاء",  # rajaa'an, please (MSA): reh, jeem, alef, hamza
    "يا",  # ya (calling someone): yeh, alef
    "الحين",  # al-heen, now (Saudi): alef, lam, hah, yeh, noon
    "الان",  # al-aan, now (MSA): alef, lam, alef, noon
    "شكرا",  # shukran, thanks: sheen, kaf, reh, alef
    "مشكور",  # mashkoor, thanks (Saudi): meem, sheen, kaf, waw, reh
    "جزيلا",  # jazeelan, (thanks) a lot: jeem, zain, yeh, lam, alef
    "لك",  # lak, to you: lam, kaf
    # ya'teek al-'aafya, bless you: yeh, ain, tah, yeh, kaf; alef, lam, ain, alef, feh, yeh, heh
    "يعطيك العافيه",
    # allah ya'aafeek, God keep you well: alef, lam, lam, heh; yeh, ain, alef, feh, yeh, kaf
    "الله يعافيك",
    # jazaak allah khair, God reward you: jeem, zain, alef, kaf; alef, lam, lam, heh; khah,
    # yeh, reh
    "جزاك الله خير",
    "يلا",  # yalla, come on: yeh, lam, alef
    "خلاص",  # khalas, that's it: khah, lam, alef, sad
    "صحيح",  # saheeh, right: sad, hah, yeh, hah
    "لي",  # li, for me: lam, yeh
    "اياها",  # iyyaaha, it: alef, yeh, alef, heh, alef
    "ابي",  # abi, I want (Saudi): alef, beh, yeh
    "ابغي",  # abghi, I want (Saudi): alef, beh, ghain, yeh
    "اريد",  # ureed, I want (MSA): alef, reh, yeh, dal
    "والله",  # wallah, truly: waw, alef, lam, lam, heh
    "و",  # wa, and: waw
    "الطلب",  # at-talab, the request: alef, lam, tah, lam, beh
    "طلبي",  # talabi, my request: tah, lam, beh, yeh
)

# The English lists, with the Latin spellings Whisper wrote for the owner's Arabic yes and send
# words in an English call (the prototype's, as above).
_ENGLISH_YES = (
    *("yes", "yeah", "yep", "yup", "sure", "of course", "correct", "that s right"),
    *("that is right", "absolutely", "definitely"),
    # na'am and aywa (yes), as Whisper wrote them in Latin letters
    *("naam", "aywa", "aiwa"),
)
_ENGLISH_SEND = (
    *("send", "send it", "submit", "submit it", "go ahead", "do it", "confirm", "proceed"),
    # arsilha (send it), as Whisper wrote it in Latin letters
    *("erselha", "irsilha", "ersilha", "arsilha", "arselha", "irselha", "ersilaha"),
    *("er silha", "ar silha", "ir silha"),
)
_ENGLISH_NO = ("nope", "nah", "never mind", "no thanks")
_ENGLISH_FILLERS = (
    *("please", "now", "right now", "just", "thanks", "thank you", "thank you very much"),
    *("thanks a lot", "it", "the", "that", "and", "you", "can", "i", "want", "to", "for me"),
    *("my", "request"),
)

# Each language preset's lists, by its primary code.
PRESET_CONSENT: Mapping[LanguageCode, ConsentWords] = {
    "ar": ConsentWords(
        yes=_ARABIC_YES,
        send=_ARABIC_SEND,
        no=(*PRESET_WORDS["ar"].no, *_ARABIC_NO),
        fillers=(*_ARABIC_FILLERS, *PRESET_WORDS["ar"].backchannel),
    ),
    "en": ConsentWords(
        yes=_ENGLISH_YES,
        send=_ENGLISH_SEND,
        no=(*PRESET_WORDS["en"].no, *_ENGLISH_NO),
        fillers=(*_ENGLISH_FILLERS, *PRESET_WORDS["en"].backchannel),
    ),
}


def consent_words(
    code: LanguageCode,
    *,
    added_yes: Sequence[str] = (),
    added_send: Sequence[str] = (),
    action_send: Sequence[str] = (),
) -> ConsentWords:
    """The lists the yes rule reads in the language `code`: the preset's, with the settings'
    additions (`words.yes`, `words.send`) and the action's own send words after them."""
    preset = PRESET_CONSENT[code]
    return ConsentWords(
        yes=(*preset.yes, *added_yes),
        send=(*preset.send, *added_send, *action_send),
        no=preset.no,
        fillers=preset.fillers,
    )
