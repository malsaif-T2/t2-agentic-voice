"""When a turn moves the call to the agent's other language, under `stt.live_language =
"detected"` (D-038's amendment; the owner's ruling of 2026-11-16: "any English question or
request should be enough to change the language and vice versa"). Pure: no IO, no clock.

Whisper told a language writes the turn in it, translating what was said in another, so no text
check can tell a turn was sent in the wrong language. So a turn with at least `from_s` seconds of
voiced speech also goes with no language named, for Whisper to detect it, at the same time as its
request in the call's current language (voice/stt_requests.py). `switch_to` then decides:

1. the detecting request heard a language whose name maps exactly to one of the agent's codes
   (domain/words.py's `heard_code`, TD-011), not the one the other request named; a third
   language, or none, is no switch;
2. and the turn is a question or request, not a short reply: it holds at least `FEWEST_WORDS`
   words, and neither transcript is made only of `SHORT_REPLIES`: the yes rule's yes and no
   words, the listening sounds and the courtesies of both languages, in both scripts (how
   Whisper writes «تمام» told English, "Tamam", or "okay" told Arabic, «اوكي»).

Then the turn's heard words are the detecting request's and the call's current language moves to
that code; otherwise the transcript in the current language stands and nothing moves. The lists
are a fast path, as every word list of the library's is.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.words import PRESET_WORDS, heard_code, rule_form
from t2_agentic_voice.domain.yes_words import PRESET_CONSENT, covered

# The fewest words a turn may move the call with: a turn of one word is a reply, whatever
# Whisper heard it as.
FEWEST_WORDS = 2

# The Arabic short replies, in the rule's form (domain/words.py's `rule_form`), with `\u`
# escapes as the library's tables are; each comment gives the word's sound and meaning, then
# its letters. English words Whisper writes in Arabic letters when told Arabic are among them.
_ARABIC_SHORT: tuple[str, ...] = (
    "\u0627\u064a\u0647",  # eh, yes: alef, yeh, heh
    "\u0627\u064a",  # ay, yes: alef, yeh
    "\u0627\u064a\u0648\u0647",  # aywa, yes: alef, yeh, waw, heh
    "\u0646\u0639\u0645",  # na'am, yes: noon, ain, meem
    "\u0627\u0643\u064a\u062f",  # akeed, sure: alef, kaf, yeh, dal
    "\u0635\u062d",  # sah, right: sad, hah
    "\u0644\u0627",  # la, no: lam, alef
    "\u062a\u0645\u0627\u0645",  # tamam, fine: teh, meem, alef, meem
    "\u0637\u064a\u0628",  # tayyib, okay: tah, yeh, beh
    "\u0627\u0648\u0643\u064a",  # okay: alef, waw, kaf, yeh
    "\u0627\u0648\u0643",  # ok: alef, waw, kaf
    "\u0645\u0627\u0634\u064a",  # mashi, okay: meem, alef, sheen, yeh
    "\u062e\u0644\u0627\u0635",  # khalas, that's it: khah, lam, alef, sad
    "\u0634\u0643\u0631\u0627",  # shukran, thanks: sheen, kaf, reh, alef
    "\u0645\u0634\u0643\u0648\u0631",  # mashkoor, thanks: meem, sheen, kaf, waw, reh
    # ya'teek al-afia, thank you: yeh, ain, tah, yeh, kaf; alef, lam, ain, alef, feh, yeh, heh
    "\u064a\u0639\u0637\u064a\u0643 \u0627\u0644\u0639\u0627\u0641\u064a\u0647",
    # allah ya'teek al-afia, thank you: alef, lam, lam, heh; then as above
    "\u0627\u0644\u0644\u0647 "
    "\u064a\u0639\u0637\u064a\u0643 \u0627\u0644\u0639\u0627\u0641\u064a\u0647",
    "\u0645\u0645\u062a\u0627\u0632",  # mumtaz, excellent: meem, meem, teh, alef, zain
    "\u062d\u0644\u0648",  # helw, nice: hah, lam, waw
    "\u0645\u0631\u062d\u0628\u0627",  # marhaba, hello: meem, reh, hah, beh, alef
    "\u0647\u0644\u0627",  # hala, hi: heh, lam, alef
    # as-salamu alaykum, hello: alef, lam, seen, lam, alef, meem; ain, lam, yeh, kaf, meem
    "\u0627\u0644\u0633\u0644\u0627\u0645 \u0639\u0644\u064a\u0643\u0645",
    # ma'a as-salama, goodbye: meem, ain; alef, lam, seen, lam, alef, meem, heh
    "\u0645\u0639 \u0627\u0644\u0633\u0644\u0627\u0645\u0647",
    # min fadlak, please: meem, noon; feh, dad, lam, kaf
    "\u0645\u0646 \u0641\u0636\u0644\u0643",
    # law samaht, please: lam, waw; seen, meem, hah, teh
    "\u0644\u0648 \u0633\u0645\u062d\u062a",
    "\u0639\u0641\u0648\u0627",  # afwan, you're welcome: ain, feh, waw, alef
    # in sha allah, God willing: alef, noon; sheen, alef, hamza; alef, lam, lam, heh
    "\u0627\u0646 \u0634\u0627\u0621 \u0627\u0644\u0644\u0647",
    # al-hamdu lillah, thank God: alef, lam, hah, meem, dal; lam, lam, heh
    "\u0627\u0644\u062d\u0645\u062f \u0644\u0644\u0647",
    "\u062b\u0627\u0646\u0643\u0633",  # thanks: theh, alef, noon, kaf, seen
    "\u062b\u0627\u0646\u0643 \u064a\u0648",  # thank you: theh, alef, noon, kaf; yeh, waw
    "\u064a\u0633",  # yes: yeh, seen
    "\u0646\u0648",  # no: noon, waw
    "\u0628\u0627\u064a",  # bye: beh, alef, yeh
    "\u0647\u0627\u064a",  # hi: heh, alef, yeh
)
# The English short replies, with the Arabic ones Whisper writes in Latin letters when told
# English.
_ENGLISH_SHORT: tuple[str, ...] = (
    "okay",
    "ok",
    "please",
    "alright",
    "all right",
    "thanks",
    "thank you",
    "thank you so much",
    "great",
    "good",
    "fine",
    "perfect",
    "cool",
    "nice",
    "got it",
    "i see",
    "hello",
    "hi",
    "hey",
    "bye",
    "goodbye",
    "sorry",
    "you re welcome",
    "no problem",
    "sounds good",
    "that s fine",
    "that s it",
    "mm",
    "hmm",
    "uh huh",
    "tamam",
    "khalas",
    "yalla",
    "inshallah",
    "mashallah",
    "shukran",
    "aywa",
    "ahlan",
    "marhaba",
    "salam",
    "wallahi",
)


def _short_replies() -> frozenset[str]:
    """Every short reply of both languages: the yes rule's yes and no words, the listening
    sounds, and the lists above, in the rule's form."""
    words: list[str] = [*_ARABIC_SHORT, *_ENGLISH_SHORT]
    for code in ("ar", "en"):
        consent = PRESET_CONSENT[code]
        words += [*consent.yes, *consent.no, *PRESET_WORDS[code].backchannel]
    return frozenset(form for form in map(rule_form, words) if form)


SHORT_REPLIES: frozenset[str] = _short_replies()


@dataclass(frozen=True, kw_only=True)
class DetectRule:
    """When a turn is also sent naming no language: with at least `from_s` seconds of voiced
    speech, in a call whose agent speaks `codes`, two or more."""

    from_s: float
    codes: tuple[LanguageCode, ...]

    def __post_init__(self) -> None:
        if not self.from_s > 0:
            raise ValueError("from_s is a length of voiced speech above 0 seconds")
        if len(set(self.codes)) < 2:
            raise ValueError("a call detects only between two of the agent's languages or more")

    def detects(self, voiced_s: float | None) -> bool:
        """Whether a turn of `voiced_s` seconds of voiced speech (None: not one to detect, an
        overlap's) is also sent naming no language."""
        return voiced_s is not None and voiced_s >= self.from_s


def short_reply(text: str) -> bool:
    """Whether `text` is a short reply, never moving the call: fewer than `FEWEST_WORDS` words,
    or only `SHORT_REPLIES` (the module's docstring)."""
    return len(rule_form(text).split()) < FEWEST_WORDS or covered(text, SHORT_REPLIES)


def switch_to(
    named: str | None,
    detected: str | None,
    *,
    codes: Sequence[LanguageCode],
    named_text: str | None,
    detected_text: str,
) -> LanguageCode | None:
    """The code the call moves to when its request in `named` heard `named_text` (None when it
    failed) and its detecting request heard `detected_text` in `detected` (the transcript's
    language, a code or Whisper's name of it); None when nothing moves (the module's
    docstring)."""
    code = heard_code(detected)
    if code is None or code not in codes or code == heard_code(named):
        return None
    if short_reply(detected_text) or covered(named_text or "", SHORT_REPLIES):
        return None
    return code
