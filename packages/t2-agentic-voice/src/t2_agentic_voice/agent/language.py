"""The reply language of each turn (plan 006, "What voice-first means here", item 8): the reply
follows the language the caller's turn was heard in, not the call's alone, so one call may hold
Saudi, MSA and English turns, each answered in its own.

- **Heard.** The language the turn's transcript names (a code, "ar" or "en", or the provider's
  name of it, "Arabic"); a call tells speech-to-text its language (D-066), so this is most often
  the call's.
- **Written.** The script of the turn's words overrules it when it plainly says otherwise:
  `SWITCH_WORDS` words or more in the other script, more than twice the words in the heard
  one's (the prototype switched only on three words in the other script, its D27). So an
  English question Whisper writes in Latin letters in an Arabic call is answered in English,
  while an Arabic sentence with English product terms in it ("VPN" and "Outlook" in a Saudi
  question) stays Arabic.
- **The tag.** That language is the agent's tag for it: the call's own when its language is
  the same (an `ar-SA` call stays `ar-SA`), else the first of the agent's tags in it, else the
  call's.
- **The register** of the caller's Arabic (`register_of`, a turn's; `call_register`, the call's).
  Saudi Arabic and MSA share a code, so the tag does not tell them apart; the caller's words do,
  by a small explicit list of Saudi and Gulf dialect forms: a turn whose Arabic holds one is
  Saudi, one that holds none is MSA (and a turn with no Arabic word keeps the Saudi default). A
  reply follows the call's: Saudi once any heard turn of the caller's held a form, so a short
  plain turn after a Saudi one (tamam, okay; kammil, go on) stays Saudi, and MSA while none of
  them has. A team adds its own Saudi forms (`words.dialect`, a phrase of several words heard as
  those words in a row). Under `words.saudi_first` (off by default, GP-18; D-123), a turn with no
  Saudi form is MSA only when it plainly speaks MSA, by a short list of forms only MSA says
  (`MSA_WORDS`: ureed, awadd, hal, matha and the like); one with neither (a greeting, «إي نعم», a
  city) is no evidence, so the call is Saudi until an MSA turn is heard, MSA from then on until a
  Saudi form is. `words.fixed_register` set, every call is held in that one. An `ar-SA` reply's
  language section and its line after a tool result then ask for that register (agent/prompt.py);
  an agent's Arabic tag that is not Saudi (`ar`) keeps its section as it was. Run K's first dev
  round: 8 of 10 MSA callers were answered in Saudi when the model alone told them apart.
- **The wording** of an action's lines (`wording`): an `ar-SA` reply to an MSA caller reads an
  action's texts in `ar`, its MSA ones (domain/action_declaration.py's `read_in`), and the
  library's own lines in MSA, the owner's ruling of 2026-11-10; it is still spoken in `ar-SA`,
  the agent's voice. Any other reply reads its own tag.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Sequence
from functools import lru_cache

from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import LanguageCode, WordSettings, primary_code
from t2_agentic_voice.domain.text.arabic_numbers import Register as Register  # re-exported
from t2_agentic_voice.domain.words import heard_code, rule_form

# The fewest words in the other script that can switch a turn's language.
SWITCH_WORDS = 3
# An Arabic letter: hamza to ghain, feh to yeh (the tatweel left out), alef wasla to yeh barree.
_ARABIC_LETTER = re.compile("[\u0621-\u063a\u0641-\u064a\u0671-\u06d3]")
_LATIN_LETTER = re.compile("[A-Za-z]")


def _written(words: str, heard: LanguageCode | None) -> LanguageCode | None:
    """The language the script of `words` plainly says, when it is not `heard`."""
    arabic = latin = 0
    for word in words.split():
        if _ARABIC_LETTER.search(word):
            arabic += 1
        elif _LATIN_LETTER.search(word):
            latin += 1
    if heard != "en" and latin >= SWITCH_WORDS and latin > 2 * arabic:
        return "en"
    if heard != "ar" and arabic >= SWITCH_WORDS and arabic > 2 * latin:
        return "ar"
    return None


def reply_language(
    turn: TalkerTurn, *, call: LanguageTag, spoken: Sequence[LanguageTag]
) -> LanguageTag:
    """The tag the reply to `turn` is in, in a call held in `call` by an agent that speaks
    `spoken` (the module's docstring); the language the turn asked the call to move to, when it
    asked for one the agent speaks (`TalkerTurn.asked`)."""
    asked = next((tag for tag in spoken if tag == turn.asked), None)
    if asked is not None:
        return asked
    heard = heard_code(turn.language)
    return tag_of(_written(turn.words, heard) or heard, call=call, spoken=spoken)


def tag_of(
    language: str | None, *, call: LanguageTag, spoken: Sequence[LanguageTag]
) -> LanguageTag:
    """The agent's tag of `language` (a code, or a provider's name of it): the call's own when
    its language is the same, else the first of `spoken` in it, else the call's. The call
    report names a turn's language so (D-086)."""
    code = heard_code(language) or primary_code(call)
    if primary_code(call) == code:
        return call
    return next((tag for tag in spoken if primary_code(tag) == code), call)


# The Saudi and Gulf dialect forms the caller's Arabic is read by (`register_of`), each a whole
# word, in the interruption rule's form (domain/words.py's `rule_form`: teh marbuta written heh,
# alef maksura yeh, every alef bare), with `\u` escapes as the library's tables are; each
# comment gives the word's sound and meaning, then its letters. MSA writes none of them as a
# word of its own in a caller's question, but for a few that it seldom says: `marra` (once),
# `rah` (went), `tigdar` and `agdar` (you and I esteem).
DIALECT_WORDS: frozenset[str] = frozenset(
    {
        "\u0627\u0628\u0634\u0631",  # abshir, at your service: alef, beh, sheen, reh
        "\u062a\u0642\u062f\u0631",  # tigdar, you can: teh, qaf, dal, reh
        "\u0627\u0642\u062f\u0631",  # agdar, I can: alef, qaf, dal, reh
        "\u062a\u0628\u064a",  # tabi, you want: teh, beh, yeh
        "\u0627\u0628\u064a",  # abi, I want: alef, beh, yeh
        "\u0627\u0628\u063a\u064a",  # abgha, I want: alef, beh, ghain, yeh
        "\u0627\u0644\u0644\u064a",  # illi, who or which: alef, lam, lam, yeh
        "\u0648\u0634",  # wish, what: waw, sheen
        "\u0627\u064a\u0634",  # aish, what: alef, yeh, sheen
        "\u0644\u064a\u0634",  # laish, why: lam, yeh, sheen
        "\u0648\u064a\u0646",  # wain, where: waw, yeh, noon
        "\u0645\u064a\u0646",  # meen, who: meem, yeh, noon
        "\u0634\u0644\u0648\u0646",  # shlon, how: sheen, lam, waw, noon
        "\u0627\u0644\u062d\u064a\u0646",  # al-heen, now: alef, lam, hah, yeh, noon
        "\u0644\u0627\u0632\u0645",  # lazim, must: lam, alef, zain, meem
        "\u0628\u0633",  # bas, only or but: beh, seen
        "\u0645\u0648",  # mu, not: meem, waw
        "\u0631\u0627\u062d",  # rah, will (the future): reh, alef, hah
        "\u062c\u0631\u0628",  # jarrib, try: jeem, reh, beh
        "\u062a\u0634\u0648\u0641",  # tshoof, you see: teh, sheen, waw, feh
        "\u064a\u0628\u0627\u0646",  # yiban, it shows: yeh, beh, alef, noon
        "\u0645\u0639\u0644\u064a\u0634",  # ma'alaish, never mind: meem, ain, lam, yeh, sheen
        "\u0639\u0634\u0627\u0646",  # ashan, so that: ain, sheen, alef, noon
        "\u0643\u0630\u0627",  # kitha, like this: kaf, thal, alef
        "\u0632\u064a\u0646",  # zain, good: zain, yeh, noon
        "\u0645\u0631\u0647",  # marra, very: meem, reh, heh
        "\u0627\u0633\u0648\u064a",  # asawwi, I do: alef, seen, waw, yeh
        "\u062a\u0633\u0648\u064a",  # tsawwi, you do: teh, seen, waw, yeh
        "\u064a\u0633\u0648\u064a",  # ysawwi, he does: yeh, seen, waw, yeh
        "\u0646\u0633\u0648\u064a",  # nsawwi, we do: noon, seen, waw, yeh
        "\u064a\u0646\u0641\u0639",  # yinfa', it works or may I: yeh, noon, feh, ain
        "\u062e\u0631\u0628\u0627\u0646",  # kharban, broken: khah, reh, beh, alef, noon
    }
)
# The forms only MSA says, by which a turn plainly speaks MSA under `words.saudi_first`, each a
# whole word in the rule's form, with or without wa before it (but `_NOT_WA`); a Saudi caller
# says each otherwise (abi, wain, al-heen, fih, mu, bukra, al-jay, indi, tayyib, illi).
MSA_WORDS: frozenset[str] = frozenset(
    {
        "\u0627\u0631\u064a\u062f",  # ureed, I want: alef, reh, yeh, dal
        "\u0646\u0631\u064a\u062f",  # nureed, we want: noon, reh, yeh, dal
        "\u0627\u0648\u062f",  # awadd, I would like: alef, waw, dal
        "\u0647\u0644",  # hal, the question's opener: heh, lam
        "\u0645\u0627\u0630\u0627",  # matha, what: meem, alef, thal, alef
        "\u0644\u0645\u0627\u0630\u0627",  # limatha, why: lam, meem, alef, thal, alef
        "\u0627\u064a\u0646",  # ayna, where: alef, yeh, noon
        "\u0627\u0644\u0627\u0646",  # al-aan, now: alef, lam, alef, noon
        "\u0633\u0648\u0641",  # sawfa, will: seen, waw, feh
        "\u0644\u0646",  # lan, will not: lam, noon
        "\u0644\u064a\u0633",  # laysa, is not: lam, yeh, seen
        "\u064a\u0648\u062c\u062f",  # yujad, there is: yeh, waw, jeem, dal
        "\u062a\u0648\u062c\u062f",  # tujad, there is (feminine): teh, waw, jeem, dal
        "\u0627\u0631\u063a\u0628",  # arghab, I wish: alef, reh, ghain, beh
        "\u0646\u0631\u063a\u0628",  # narghab, we wish: noon, reh, ghain, beh
        "\u063a\u062f\u0627",  # ghadan, tomorrow: ghain, dal, alef
        "\u063a\u062f",  # ghad, tomorrow (ba'da ghad, the day after): ghain, dal
        "\u0627\u0644\u0642\u0627\u062f\u0645",  # al-qadim, next: alef, lam, qaf, alef, dal, meem
        "\u0627\u0644\u0642\u0627\u062f\u0645\u0647",  # al-qadima, next (feminine): ... heh
        "\u0644\u062f\u064a",  # ladayya, I have (and lada, at): lam, dal, yeh
        "\u0644\u062f\u064a\u0646\u0627",  # ladayna, we have: lam, dal, yeh, noon, alef
        "\u062d\u0633\u0646\u0627",  # hasanan, all right: hah, seen, noon, alef
        "\u0627\u0644\u0630\u064a",  # allathi, who or which: alef, lam, thal, yeh
        "\u0627\u0644\u062a\u064a",  # allati, who or which (feminine): alef, lam, teh, yeh
    }
)
# A word of its own, not wa and a form of `MSA_WORDS`: waladi, my son: waw, lam, dal, yeh.
_NOT_WA: frozenset[str] = frozenset({"\u0648\u0644\u062f\u064a"})
# A dialect form only as the turn's first word: fih, there is (is there?): feh, yeh, heh. MSA
# writes it after what it is in, never to open a question.
DIALECT_OPENERS: frozenset[str] = frozenset({"\u0641\u064a\u0647"})
# ma, not, before a verb: Saudi's negation (MSA's is la or lam): meem, alef. MSA's ma asks
# "what" before a noun, which a verb's shape (`_verb`) mostly tells apart.
NEGATION = "\u0645\u0627"
# The words after ma in MSA that have a verb's shape: the verbs it says "what" before, and the
# nouns its questions ask of.
NOT_NEGATED: frozenset[str] = frozenset(
    {
        "\u064a\u062c\u0628",  # yajib, must: yeh, jeem, beh
        "\u064a\u0645\u0643\u0646",  # yumkin, can: yeh, meem, kaf, noon
        "\u064a\u0646\u0628\u063a\u064a",  # yanbaghi, should: yeh, noon, beh, ghain, yeh
        "\u064a\u0644\u0632\u0645",  # yalzam, is needed: yeh, lam, zain, meem
        "\u064a\u0644\u064a",  # yali, follows: yeh, lam, yeh
        "\u064a\u0648\u0645",  # yawm, day: yeh, waw, meem
        "\u0648\u0642\u062a",  # waqt, time: waw, qaf, teh
        "\u062a\u0627\u0631\u064a\u062e",  # tareekh, date: teh, alef, reh, yeh, khah
        "\u062a\u0643\u0644\u0641\u0647",  # taklifa, cost: teh, kaf, lam, feh, heh
        "\u062a\u0641\u0627\u0635\u064a\u0644",  # tafaseel, details: teh, feh, alef, sad, yeh, lam
        "\u0627\u0633\u0628\u0627\u0628",  # asbab, causes: alef, seen, beh, alef, beh
        "\u0627\u0641\u0636\u0644",  # afdal, best: alef, feh, dad, lam
        "\u0627\u0646\u0648\u0627\u0639",  # anwa', kinds: alef, noon, waw, alef, ain
    }
)
# A verb's shape after ma: an imperfect's first letter (alef, teh, noon, yeh), or a perfect's
# ending (teh; teh, noon, yeh; waw, alef), never the article (alef, lam) nor a plural's ending
# (alef, teh).
_IMPERFECT = "\u0627\u062a\u0646\u064a"
_SHORT = "\u062a\u064a"  # the imperfect's first letters a word of three letters may have: teh, yeh
_ARTICLE = "\u0627\u0644"
_PERFECT = ("\u062a", "\u062a\u0646\u064a", "\u0648\u0627")
_PLURAL = "\u0627\u062a"
_AND = "\u0648"  # wa, and, written as a word's first letter: waw


def _verb(word: str) -> bool:
    """Whether `word`, after ma, has a verb's shape: three letters or more, an imperfect's first
    letter (four letters with an alef or a noon, so ism, name, and naw', kind, are not) or a
    perfect's ending; never one of `NOT_NEGATED`."""
    if word in NOT_NEGATED or word.startswith(_ARTICLE) or len(word) < 3:
        return False
    if word[0] in _IMPERFECT and (len(word) >= 4 or word[0] in _SHORT):
        return True
    return word.endswith(_PERFECT) and not word.endswith(_PLURAL)


def _dialect(word: str) -> bool:
    return word in DIALECT_WORDS or (word.startswith(_AND) and word[1:] in DIALECT_WORDS)


def _msa(word: str) -> bool:
    joined = word.startswith(_AND) and word not in _NOT_WA
    return word in MSA_WORDS or (joined and word[1:] in MSA_WORDS)


@lru_cache(maxsize=64)
def _forms(dialect: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """A team's Saudi forms (`words.dialect`), each as its words in the rule's form."""
    return tuple(tuple(words) for form in dialect if (words := rule_form(form).split()))


def _added(heard: Sequence[str], dialect: tuple[str, ...]) -> bool:
    """Whether `heard` holds one of the `dialect` forms as words in a row, its first with or
    without wa before it."""
    for form in _forms(dialect):
        for at in range(len(heard) - len(form) + 1):
            first, rest = heard[at], heard[at + 1 : at + len(form)]
            if first in (form[0], _AND + form[0]) and tuple(rest) == form[1:]:
                return True
    return False


def _saudi(heard: Sequence[str], dialect: tuple[str, ...]) -> bool:
    """Whether the words `heard`, in the rule's form, hold a Saudi form (`register_of`)."""
    opener = bool(heard) and heard[0] in DIALECT_OPENERS
    if opener or any(_dialect(word) for word in heard):
        return True
    negated = (NEGATION, _AND + NEGATION)
    pairs = itertools.pairwise(heard)
    return any(ma in negated and _verb(after) for ma, after in pairs) or _added(heard, dialect)


def _arabic(words: str) -> bool:
    return any(map(_ARABIC_LETTER.search, words.split()))


def _read(words: str, dialect: tuple[str, ...]) -> Register | None:
    """What an Arabic turn's `words` plainly hold: saudi for a Saudi form, msa for a form only
    MSA says and no Saudi one (`MSA_WORDS`), None for neither."""
    heard = rule_form(words).split()
    if _saudi(heard, dialect):
        return "saudi"
    return "msa" if any(_msa(word) for word in heard) else None


def register_of(words: str, *, dialect: Sequence[str] = (), saudi_first: bool = False) -> Register:
    """The register of the caller's Arabic in `words` (the module's docstring): Saudi when it
    holds a dialect form (`DIALECT_WORDS`, a word of `DIALECT_OPENERS` first, ma before a
    verb, each word with or without wa before it, or one of a team's `dialect` forms), or holds
    no Arabic word; else MSA, or under `saudi_first` MSA only when it holds a form only MSA says
    (`MSA_WORDS`) and Saudi when it holds neither."""
    if not _arabic(words):
        return "saudi"
    return _read(words, tuple(dialect)) or ("saudi" if saudi_first else "msa")


def call_register(turns: Sequence[str], settings: WordSettings | None = None) -> Register:
    """The register of the caller's Arabic over the call so far, from each heard turn of
    `turns` read on its own (`register_of`): `settings.fixed_register` when set, for the whole call;
    else Saudi once a turn held a dialect form (`settings.dialect` too) or while none held
    Arabic; MSA while every Arabic turn held none, or under `saudi_first` once one plainly
    spoke MSA."""
    if settings is not None and settings.fixed_register is not None:
        return settings.fixed_register
    dialect = () if settings is None else settings.dialect
    read = {_read(words, dialect) for words in turns if _arabic(words)}
    if not read or "saudi" in read:
        return "saudi"
    first = settings is not None and settings.saudi_first
    return "msa" if "msa" in read or not first else "saudi"


def wording(tag: LanguageTag, register: Register) -> LanguageTag:
    """The tag an action's lines are read in, for a reply in `tag` to a caller whose Arabic is
    in `register` (`call_register`): `ar`, MSA, for an `ar-SA` reply to an MSA caller, else
    `tag` itself (the module's docstring)."""
    return "ar" if tag == "ar-SA" and register == "msa" else tag
