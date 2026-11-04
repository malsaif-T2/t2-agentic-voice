"""Text from silence (plan 005's filter, rule F): words Whisper writes for audio that holds no
speech, which count as no words, for an overlap (domain/interruptions.py) and for a turn. A
transcript is text from silence when Whisper's probability that the audio holds no speech is
above `stt.no_speech_max` (unset: never), or when it is one of the captions Whisper invents for
silence or noise (`CAPTIONS`, used only under `stt.caption_filter`). Both are off by default
until the registered rule F sets them (GP-18); a transcript with no word at all (empty, or only
punctuation and symbols) is no words whatever they are. The scorers' own measure of text from
silence is domain/scoring.py's. Pure, with no IO.

The captions are the prototype's (its `voice/stt.py`, lines 35-54, read only: D-010), each of
its patterns written out as the texts it matches, with the caption for music that plan 002's
runs found and the prototype lacked (plan 002's Future improvements). Its patterns that take any
name (a subtitle credit, a translator's name) keep only the credits seen. A transcript matches a
caption whole, in the rule's form (domain/words.py's `rule_form`) with its spaces aside, so a
word Whisper writes joined or apart is the same caption.
"""

from __future__ import annotations

from collections.abc import Collection
from functools import lru_cache
from itertools import product

from t2_agentic_voice.domain.words import rule_form


def _forms(*parts: tuple[str, ...]) -> tuple[str, ...]:
    """Every text made of one of each of `parts`' words, in order, an empty one left out: a
    pattern of the prototype's, written out."""
    return tuple(" ".join(word for word in words if word) for words in product(*parts))


# The parts of the Arabic captions, in the rule's form; each comment gives the sound and the
# meaning, then the letters ("the same" repeats the word above it).
_AND = ("", "\u0648")  # wa, and: waw
_IN_OR_BY = ("\u0641\u064a", "\u0628")  # fi, in: feh, yeh; bi, by: beh
_CHANNEL = (
    "\u0642\u0646\u0627\u0647",  # qanah, a channel: qaf, noon, alef, heh
    "\u0627\u0644\u0642\u0646\u0627\u0647",  # al-qanah, the channel: alef, lam, the same
)
_THANKS = ("\u0634\u0643\u0631\u0627",)  # shukran, thanks: sheen, kaf, reh, alef
_TO_YOU = ("", "\u0644\u0643\u0645")  # lakum, to you: lam, kaf, meem
_SUBSCRIBING = (
    # ishtiraak, subscribing: alef, sheen, teh, reh, alef, kaf
    "\u0627\u0634\u062a\u0631\u0627\u0643",
    # al-ishtiraak, the subscribing: alef, lam, the same
    "\u0627\u0644\u0627\u0634\u062a\u0631\u0627\u0643",
)
_DO_NOT_FORGET = (
    "",
    # la tansaw, do not forget: lam, alef; teh, noon, seen, waw, alef
    "\u0644\u0627 \u062a\u0646\u0633\u0648\u0627",
    # the spellings the prototype's pattern also takes: no last alef; yeh for waw and alef; yeh
    # and alef
    "\u0644\u0627 \u062a\u0646\u0633\u0648",
    "\u0644\u0627 \u062a\u0646\u0633\u064a",
    "\u0644\u0627 \u062a\u0646\u0633\u064a\u0627",
)
_SUBSCRIBE = (
    "\u0627\u0634\u062a\u0631\u0643",  # ishtarik, subscribe: alef, sheen, teh, reh, kaf
    "\u0627\u0634\u062a\u0631\u0643\u0648\u0627",  # ishtariku (to many): the same, waw, alef
    "\u0627\u0634\u062a\u0631\u0643\u064a",  # ishtariki (to a woman): the same, yeh
)
_FOR_WATCHING = (
    "\u0639\u0644\u064a",  # 'ala, for: ain, lam, yeh
    "\u0644\u0644",  # lil, for the: lam, lam
)
_WATCHING = (
    # mushahada, watching: meem, sheen, alef, heh, dal, heh
    "\u0645\u0634\u0627\u0647\u062f\u0647",
    # al-mushahada, the watching: alef, lam, the same
    "\u0627\u0644\u0645\u0634\u0627\u0647\u062f\u0647",
)
_YOUR_WATCHING = (
    # li-mushahadatikum, for your watching: lam, meem, sheen, alef, heh, dal, teh, kaf, meem
    "\u0644\u0645\u0634\u0627\u0647\u062f\u062a\u0643\u0645",
    # li-mushahadatik, the same to one: no last meem
    "\u0644\u0645\u0634\u0627\u0647\u062f\u062a\u0643",
    # li-mushahadati, for my watching: yeh for kaf and meem
    "\u0644\u0645\u0634\u0627\u0647\u062f\u062a\u064a",
)
_TRANSLATOR = (
    "\u0645\u062a\u0631\u062c\u0645",  # mutarjim, a translator: meem, teh, reh, jeem, meem
    # al-mutarjim, the translator: alef, lam, the same
    "\u0627\u0644\u0645\u062a\u0631\u062c\u0645",
)
_TO_CHANNEL = (
    "\u0644\u0642\u0646\u0627\u0647",  # li-qanah, for a channel: lam, qaf, noon, alef, heh
    "\u0644\u0644\u0642\u0646\u0627\u0647",  # lil-qanah, for the channel: lam, the same
)
# tarjamat Nancy Qanqar, translated by Nancy Qanqar: teh, reh, jeem, meem, heh; noon, alef, noon,
# seen, yeh; qaf, noon, qaf, reh. A subtitle credit, the one plan 002's runs saw.
_CREDIT = "\u062a\u0631\u062c\u0645\u0647 \u0646\u0627\u0646\u0633\u064a \u0642\u0646\u0642\u0631"
# museeqa, music: meem, waw, seen, yeh, qaf, yeh (its alef maksura written yeh).
_MUSIC = "\u0645\u0648\u0633\u064a\u0642\u064a"

# The captions Whisper invents for silence or noise, in the rule's form, matched whole: the
# prototype's patterns in its order (subscribing to the channel, subscribe to the channel, the
# credit, thanks for watching twice, the channel's translator, then the English ones), and music.
CAPTIONS: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            *_forms(_AND, _DO_NOT_FORGET[:2], _SUBSCRIBING, _IN_OR_BY, _CHANNEL),
            *_forms(_AND, _DO_NOT_FORGET, _SUBSCRIBE, _IN_OR_BY, _CHANNEL),
            _CREDIT,
            *_forms(_THANKS, _TO_YOU, _FOR_WATCHING, _WATCHING),
            *_forms(_THANKS, _TO_YOU, _YOUR_WATCHING),
            *_forms(_TRANSLATOR, _TO_CHANNEL),
            *_forms(("thank", "thanks"), ("", "you"), ("for watching",)),
            *_forms(("", "please"), ("subscribe to",), ("the", "my", "our"), ("channel",)),
            *_forms(("subtitle", "subtitles"), ("by the amara org community",)),
            _MUSIC,
        )
    )
)


def from_silence(
    text: str,
    no_speech_prob: float | None,
    *,
    no_speech_max: float | None,
    captions: Collection[str],
) -> bool:
    """Whether `text`, with the provider's `no_speech_prob` (None when it gave none), is text
    from silence: no word at all; the probability above `no_speech_max` (None: the threshold
    is off); or the text one of `captions` (empty: the list is off), whole."""
    letters = _letters(text)
    if not letters:
        return True
    if no_speech_max is not None and no_speech_prob is not None and no_speech_prob > no_speech_max:
        return True
    return bool(captions) and letters in _caption_letters(tuple(captions))


def _letters(text: str) -> str:
    """`text` in the rule's form, its spaces aside."""
    return rule_form(text).replace(" ", "")


@lru_cache(maxsize=4)
def _caption_letters(captions: tuple[str, ...]) -> frozenset[str]:
    """Each of `captions` as `_letters` writes it, each list read once: `CAPTIONS` is the same
    tuple on every call."""
    return frozenset(filter(None, map(_letters, captions)))
