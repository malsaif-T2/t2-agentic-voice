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
escapes, each comment giving the word's sound and meaning, then its letters. To the lists a send
word is never a yes alone: the closing question holds one, and its echo must not confirm
anything; for an agent that asks, a chat model judges it within the yes rule's rails (D-082).

The change markers (`change`, D-082) are read only of a chat model's yes (domain/yes_rule.py's
`judged`): words that say a yes comes with a change ("yes, but ..."), so a model's yes beside
one is a correction, never a yes. They are the owner's ruling's examples of a change, and the
verbs with the object pronoun on them, as the send words are listed.

With each turn's language from a classifier (D-086), an answer in another language
than the read-back's is routine, and the read-back's lists hold none of its no words or change
markers. So `rails_for` gives `judged`'s rails, for words heard in another language (or in none
named), the no words and the change markers of every language the agent speaks beside the
read-back's own, the lists that place a yes staying the read-back's: a rail only asks again or
corrects, so this never confirms what the read-back's lists refuse.

`covered` says whether a text is only words of given lists, as a read-back reads what is said
over its summary (voice/session/read_back.py's `ignored`).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.text.words import phrase_tokens
from t2_agentic_voice.domain.words import PRESET_WORDS, heard_code, rule_form


class ConsentWords(BaseModel):
    """One language's lists for one read-back, each in the rule's form (domain/words.py's
    `rule_form`): `yes`, `send` (the preset's, the settings' and the action's), `no`, and the
    `fillers` a yes may stand among; and `change`, the markers of a change that a chat model's
    yes may not stand beside (D-082), none unless given. A word is brought to the rule's form as
    the lists are built, each once; one that says nothing in it is dropped."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    yes: tuple[str, ...]
    send: tuple[str, ...]
    no: tuple[str, ...]
    fillers: tuple[str, ...]
    change: tuple[str, ...] = ()

    @field_validator("yes", "send", "no", "fillers", "change")
    @classmethod
    def _in_rule_form(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(form for word in value if (form := rule_form(word))))


# The Arabic lists, both Arabic presets'.
_ARABIC_YES = (
    "\u0646\u0639\u0645",  # na'am, yes: noon, ain, meem
    "\u0627\u064a\u0647",  # eeh, yes (Saudi): alef, yeh, heh
    "\u0627\u064a",  # ay, yes (Saudi): alef, yeh
    "\u0627\u064a\u0648\u0647",  # aywa, yes (Saudi): alef, yeh, waw, heh
    "\u0627\u064a\u0648\u0627",  # aywa, yes: alef, yeh, waw, alef
    "\u0627\u0643\u064a\u062f",  # akeed, sure: alef, kaf, yeh, dal
    "\u0645\u0648\u0627\u0641\u0642",  # muwaafiq, agreed: meem, waw, alef, feh, qaf
    "\u0637\u0628\u0639\u0627",  # tab'an, of course: tah, beh, ain, alef
    # bit-ta'keed, certainly (MSA): beh, alef, lam, teh, alef, kaf, yeh, dal
    "\u0628\u0627\u0644\u062a\u0627\u0643\u064a\u062f",
)
_ARABIC_SEND = (
    "\u0627\u0631\u0633\u0644",  # arsil, send: alef, reh, seen, lam
    "\u0627\u0631\u0633\u0644\u0647\u0627",  # arsilha, send it: alef, reh, seen, lam, heh, alef
    "\u0627\u0631\u0633\u0644\u0647",  # arsilah, send it: alef, reh, seen, lam, heh
    "\u0642\u062f\u0645\u0647\u0627",  # qaddimha, submit it: qaf, dal, meem, heh, alef
    "\u0642\u062f\u0645\u0647",  # qaddimah, submit it: qaf, dal, meem, heh
    # i'tamidha, approve it: alef, ain, teh, meem, dal, heh, alef; and without the alef
    "\u0627\u0639\u062a\u0645\u062f\u0647\u0627",
    "\u0627\u0639\u062a\u0645\u062f\u0647",
    "\u0646\u0641\u0630\u0647\u0627",  # naffidhha, carry it out: noon, feh, thal, heh, alef
    "\u0646\u0641\u0630\u0647",  # naffidhah, carry it out: noon, feh, thal, heh
    "\u0633\u062c\u0644\u0647\u0627",  # sajjilha, register it: seen, jeem, lam, heh, alef
    "\u0633\u062c\u0644\u0647",  # sajjilah, register it: seen, jeem, lam, heh
    "\u062a\u0648\u0643\u0644",  # tawakkal, go ahead (Saudi): teh, waw, kaf, lam
    # tawakkal 'ala allah, go ahead (Saudi): teh, waw, kaf, lam; ain, lam, yeh; alef, lam,
    # lam, heh
    "\u062a\u0648\u0643\u0644 \u0639\u0644\u064a \u0627\u0644\u0644\u0647",
    # qum bi-irsaalih, send it (MSA): qaf, meem; beh, alef, reh, seen, alef, lam, heh
    "\u0642\u0645 \u0628\u0627\u0631\u0633\u0627\u0644\u0647",
)
# Beside domain/words.py's Arabic no words.
_ARABIC_NO = (
    "\u0643\u0644\u0627",  # kalla, no (MSA): kaf, lam, alef
    "\u0627\u0628\u062f\u0627",  # abadan, never: alef, beh, dal, alef
    # alghiha, cancel it (Saudi): alef, lam, ghain, yeh, heh, alef; and without the alef
    "\u0627\u0644\u063a\u064a\u0647\u0627",
    "\u0627\u0644\u063a\u064a\u0647",
    "\u0645\u0627\u0628\u064a",  # maabi, I don't want (Saudi): meem, alef, beh, yeh
    "\u0645\u0627\u0628\u063a\u064a",  # maabghi, I don't want (Saudi): meem, alef, beh, ghain, yeh
    # la tirsilha, don't send it: lam, alef; teh, reh, seen, lam, heh, alef; and without alef
    "\u0644\u0627 \u062a\u0631\u0633\u0644\u0647\u0627",
    "\u0644\u0627 \u062a\u0631\u0633\u0644\u0647",
)
# Beside domain/words.py's Arabic listening sounds.
_ARABIC_FILLERS = (
    # ummm, a hesitation as Whisper writes it: alef, meem, meem, meem; beside the listening
    # sounds' umm and mmm, but kept here, so no agent without actions hears it otherwise
    "\u0627\u0645\u0645\u0645",
    "\u0644\u0648 \u0633\u0645\u062d\u062a",  # law samaht, please: lam, waw; seen, meem, hah, teh
    "\u0645\u0646 \u0641\u0636\u0644\u0643",  # min fadlak, please: meem, noon; feh, dad, lam, kaf
    "\u0631\u062c\u0627\u0621",  # rajaa'an, please (MSA): reh, jeem, alef, hamza
    "\u064a\u0627",  # ya (calling someone): yeh, alef
    "\u0627\u0644\u062d\u064a\u0646",  # al-heen, now (Saudi): alef, lam, hah, yeh, noon
    "\u0627\u0644\u0627\u0646",  # al-aan, now (MSA): alef, lam, alef, noon
    "\u0634\u0643\u0631\u0627",  # shukran, thanks: sheen, kaf, reh, alef
    "\u0645\u0634\u0643\u0648\u0631",  # mashkoor, thanks (Saudi): meem, sheen, kaf, waw, reh
    "\u062c\u0632\u064a\u0644\u0627",  # jazeelan, (thanks) a lot: jeem, zain, yeh, lam, alef
    "\u0644\u0643",  # lak, to you: lam, kaf
    # ya'teek al-'aafya, bless you: yeh, ain, tah, yeh, kaf; alef, lam, ain, alef, feh, yeh, heh
    "\u064a\u0639\u0637\u064a\u0643 \u0627\u0644\u0639\u0627\u0641\u064a\u0647",
    # allah ya'aafeek, God keep you well: alef, lam, lam, heh; yeh, ain, alef, feh, yeh, kaf
    "\u0627\u0644\u0644\u0647 \u064a\u0639\u0627\u0641\u064a\u0643",
    # jazaak allah khair, God reward you: jeem, zain, alef, kaf; alef, lam, lam, heh; khah,
    # yeh, reh
    "\u062c\u0632\u0627\u0643 \u0627\u0644\u0644\u0647 \u062e\u064a\u0631",
    "\u064a\u0644\u0627",  # yalla, come on: yeh, lam, alef
    "\u062e\u0644\u0627\u0635",  # khalas, that's it: khah, lam, alef, sad
    "\u0635\u062d\u064a\u062d",  # saheeh, right: sad, hah, yeh, hah
    "\u0644\u064a",  # li, for me: lam, yeh
    "\u0627\u064a\u0627\u0647\u0627",  # iyyaaha, it: alef, yeh, alef, heh, alef
    "\u0627\u0628\u064a",  # abi, I want (Saudi): alef, beh, yeh
    "\u0627\u0628\u063a\u064a",  # abghi, I want (Saudi): alef, beh, ghain, yeh
    "\u0627\u0631\u064a\u062f",  # ureed, I want (MSA): alef, reh, yeh, dal
    "\u0648\u0627\u0644\u0644\u0647",  # wallah, truly: waw, alef, lam, lam, heh
    "\u0648",  # wa, and: waw
    "\u0627\u0644\u0637\u0644\u0628",  # at-talab, the request: alef, lam, tah, lam, beh
    "\u0637\u0644\u0628\u064a",  # talabi, my request: tah, lam, beh, yeh
)
# The Arabic change markers (D-082); ghayyir and 'addil written with their shadda come to the
# words below in the rule's form, which drops it.
_ARABIC_CHANGE = (
    "\u0628\u0633",  # bas, but: beh, seen
    "\u0644\u0643\u0646",  # laakin, but: lam, kaf, noon
    "\u063a\u064a\u0631",  # ghayyir, change (ghair, other than): ghain, yeh, reh
    "\u063a\u064a\u0631\u0647\u0627",  # ghayyirha, change it: ghain, yeh, reh, heh, alef
    "\u063a\u064a\u0631\u0647",  # ghayyirah, change it: ghain, yeh, reh, heh
    "\u0639\u062f\u0644",  # 'addil, edit: ain, dal, lam
    "\u0639\u062f\u0644\u0647\u0627",  # 'addilha, edit it: ain, dal, lam, heh, alef
    "\u0639\u062f\u0644\u0647",  # 'addilah, edit it: ain, dal, lam, heh
    "\u0628\u062f\u0644",  # baddil, swap (badal, instead of): beh, dal, lam
    "\u0628\u062f\u0644\u0647\u0627",  # baddilha, swap it: beh, dal, lam, heh, alef
    "\u0628\u062f\u0644\u0647",  # baddilah, swap it: beh, dal, lam, heh
    "\u0628\u062f\u0627\u0644",  # badaal, instead of (Saudi): beh, dal, alef, lam
    "\u062e\u0644\u0647\u0627",  # khalliha, make it: khah, lam, heh, alef
    "\u062e\u0644\u0647",  # khalleh, make it: khah, lam, heh
    "\u062e\u0644\u064a\u0647\u0627",  # khalliiha, make it: khah, lam, yeh, heh, alef
    "\u062e\u0644\u064a\u0647",  # khalliih, make it: khah, lam, yeh, heh
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
    *("my", "request", "do", "i m", "i am", "that s it"),
)
# The English change markers (D-082).
_ENGLISH_CHANGE = ("but", "change", "instead", "except", "actually", "rather")

# Each language preset's lists, by its primary code.
PRESET_CONSENT: Mapping[LanguageCode, ConsentWords] = {
    "ar": ConsentWords(
        yes=_ARABIC_YES,
        send=_ARABIC_SEND,
        no=(*PRESET_WORDS["ar"].no, *_ARABIC_NO),
        fillers=(*_ARABIC_FILLERS, *PRESET_WORDS["ar"].backchannel),
        change=_ARABIC_CHANGE,
    ),
    "en": ConsentWords(
        yes=_ENGLISH_YES,
        send=_ENGLISH_SEND,
        no=(*PRESET_WORDS["en"].no, *_ENGLISH_NO),
        fillers=(*_ENGLISH_FILLERS, *PRESET_WORDS["en"].backchannel),
        change=_ENGLISH_CHANGE,
    ),
}


def covered(text: str, phrases: Collection[str]) -> bool:
    """Whether every word of `text` belongs to one of `phrases`, both in the rule's form
    (domain/words.py's `rule_form`), each phrase whole words, the longest first; False for a
    text with no word. How a read-back reads what is said over its summary (voice/session/
    read_back.py's `ignored`)."""
    heard = rule_form(text).split()
    forms = {form for form in (rule_form(phrase) for phrase in phrases) if form}
    if not heard or not forms:
        return False
    return all(token in forms for token in phrase_tokens(heard, forms))


def consent_words(
    code: LanguageCode,
    *,
    added_yes: Sequence[str] = (),
    added_send: Sequence[str] = (),
    action_send: Sequence[str] = (),
) -> ConsentWords:
    """The lists the yes rule reads in the language `code`: the preset's, with the settings'
    additions (`words.yes`, `words.send`) and the action's own send words after them, and the
    preset's change markers."""
    preset = PRESET_CONSENT[code]
    return ConsentWords(
        yes=(*preset.yes, *added_yes),
        send=(*preset.send, *added_send, *action_send),
        no=preset.no,
        fillers=preset.fillers,
        change=preset.change,
    )


def rails_for(
    words: ConsentWords, *, heard: str | None, read_back: LanguageCode, spoken: Sequence[str]
) -> ConsentWords:
    """The lists `judged`'s rails read (the module's docstring): `words`, the read-back's in its
    language `read_back`, when the words were `heard` in it; else `words` with the no words and
    the change markers of every language of `spoken` (the agent's primary codes) beside its
    own."""
    if heard_code(heard) == read_back:
        return words
    others = [each for code, each in PRESET_CONSENT.items() if code in spoken]
    return ConsentWords(
        yes=words.yes,
        send=words.send,
        no=(*words.no, *(word for each in others for word in each.no)),
        fillers=words.fillers,
        change=(*words.change, *(word for each in others for word in each.change)),
    )
