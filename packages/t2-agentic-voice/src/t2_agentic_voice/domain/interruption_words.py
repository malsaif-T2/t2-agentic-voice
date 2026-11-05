"""The fixed words the interruption rule (domain/interruptions.py) reads beside a language's lists
(domain/words.py): the question words, the polite words, and the stop word as Whisper wrote it
over the agent's voice. None is a kind of `Words`: a team's lists stay the five kinds. Each is
in the rule's form (`rule_form`), the Arabic written with escapes as the library's tables are,
each comment giving the word's sound and meaning, then its letters."""

from __future__ import annotations

from collections.abc import Mapping

from t2_agentic_voice.core.settings.words import LanguageCode

# The words that make an output a question when it opens with one (or with one after waw, and),
# for each language: the prototype's (rules.py, lines 312-326).
QUESTION_WORDS: Mapping[LanguageCode, frozenset[str]] = {
    "ar": frozenset(
        {
            "كيف",  # kaif, how: kaf, yeh, feh
            "ماذا",  # matha, what: meem, alef, thal, alef
            "لماذا",  # limatha, why: lam, then as above
            "ليش",  # laish, why (Saudi): lam, yeh, sheen
            "ليه",  # laih, why: lam, yeh, heh
            "متي",  # mata, when: meem, teh, yeh
            "وين",  # wain, where (Saudi): waw, yeh, noon
            "اين",  # ain, where: alef, yeh, noon
            "فين",  # fain, where: feh, yeh, noon
            "هل",  # hal, is it: heh, lam
            "ايش",  # aish, what: alef, yeh, sheen
            "وش",  # wish, what (Saudi): waw, sheen
            "شو",  # shu, what: sheen, waw
            "شلون",  # shlon, how (Saudi): sheen, lam, waw, noon
            "كم",  # kam, how many: kaf, meem
            "مين",  # meen, who: meem, yeh, noon
            "ممكن",  # mumkin, can (you): meem, meem, kaf, noon
        }
    ),
    "en": frozenset(
        {"how", "what", "why", "where", "when", "which", "who", "can", "could", "would"}
        | {"is", "are", "do", "does", "did", "should", "will"}
    ),
}
QUESTION_MARKS = ("?", "؟")  # the question mark, and the Arabic one

# Polite words, which may stand beside a repeat request or the stop word's whole spellings
# (below) without changing it: the prototype's (rules.py, line 75), but its listening sounds,
# which the lists hold. Of both languages.
POLITE = frozenset(
    {
        # law samaht, please: lam, waw; seen, meem, hah, teh
        "لو سمحت",
        # min fadlak, please: meem, noon; feh, dad, lam, kaf
        "من فضلك",
        "يا",  # ya (calling someone): yeh, alef
        "الحين",  # al-heen, now (Saudi): alef, lam, hah, yeh, noon
        "please",
        "now",
    }
)

# The stop word as Whisper wrote it over the agent's voice in the prototype's Arabic calls (its
# rules.py, lines 49-62 and 154-168): one or two words of at most six letters, together, one of
# them ending as the word does or one of the sounds below, the first letter of none meem (a noun
# or a participle, never the verb), with no question or no word.
NOISY_ENDS = (
    "قف",  # qaf, feh
    "كف",  # kaf, feh
    "غف",  # ghain, feh
)
NOISY_SOUNDS = frozenset(
    {
        "بودكيف",  # beh, waw, dal, kaf, yeh, feh
        "باكيف",  # beh, alef, kaf, yeh, feh (also two words, joined)
        "قدف",  # qaf, dal, feh
        # waqaft, I stopped, written for the owner's wagif (plan 005's review): waw, qaf, feh, teh
        "وقفت",
    }
)
NOISY_LETTERS = 6
NOT_NOISY_START = "م"  # meem

# The spellings only Whisper writes for the stop word, a stop only as a whole short utterance:
# with polite words and listening sounds beside it, at most `NOISY_WORDS` words in all. Inside a
# sentence each is a word like any other (lighair is "for other than", wakaif "and how"; "one
# game" is English). The prototype's: in an Arabic call, its spellings of the owner's wagif (its
# VOICE_LOG.md, CP0 and CP1), with the one plan 005's run O1 heard (the registration's amendment
# (10)); in an English call, those and the full model's over the agent (its rules.py, lines 28-32
# and 54-62).
NOISY_SPELLINGS = frozenset(
    {
        "وغف",  # wagif heard as wughf: waw, ghain, feh
        "وغفو",  # wagif heard as wughfu: waw, ghain, feh, waw
        "وغفت",  # wagif heard as wughfat: waw, ghain, feh, teh
        "لغير",  # wagif heard as lighair: lam, ghain, yeh, reh
        "وكيف",  # wagif heard as wakaif (plan 005's O1): waw, kaf, yeh, feh
    }
    | {"waggir", "one gift", "what gift", "one game", "one again", "one give", "one gives"}
    | {"one get", "one gif", "what gif", "blood gif"}
    | {"what a gift", "what gives", "what give", "plug if", "waqif", "waqef"}
)
NOISY_WORDS = 3
