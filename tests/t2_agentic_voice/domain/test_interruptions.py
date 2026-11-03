"""Whether speech over the agent's reply stops it (domain/interruptions.py): an overlap's
transcript and the rule's verdict are frozen and bounded, the verdict's kind and reason the
`Interrupted` event's, and each step of the starting rule (plan 005), in its order: no words,
a stop or wait word anywhere and the stop word as Whisper mishears it, a repeat request, the
agent's own words, listening sounds, a short output, then enough real words, a correction when
the first is a no word. Its tests are written on texts made for them, never an item's."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import get_args

import pytest
from pydantic import ValidationError
from t2_agentic_voice import Phrases
from t2_agentic_voice.core.events import Interrupted, InterruptionReason
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.interruptions import Overlap, Verdict, VerdictReason, judge
from t2_agentic_voice.domain.silence import CAPTIONS
from t2_agentic_voice.domain.words import PRESET_WORDS, Words

AT = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)

OVERLAP = Overlap(
    text="made-up words over the reply",
    no_speech_prob=0.1,
    speech_s=1.2,
    played=("a made-up clause the agent said",),
    language="en",
)

STOP = ("stop", "stop", "stop_word")
REPEAT = ("repeat", "new_words", "repeat_word")
NEW_WORDS = ("stop", "new_words", "enough_words")
CORRECTION = ("stop", "correction", "enough_words")
CLAUSE = "The archive screen opens from the main menu."  # the agent's, for its own words
ARABIC_CLAUSE = "يمكنك فتح الأرشيف من القائمة الرئيسية."


def went_on(reason: VerdictReason) -> tuple[str, str, str]:
    return ("go_on", "false", reason)


def judged(
    text: str,
    language: LanguageCode = "en",
    *,
    speech_s: float = 2.0,
    played: tuple[str, ...] = (),
    words: Words | None = None,
    no_speech_prob: float | None = None,
    no_speech_max: float | None = None,
    captions: tuple[str, ...] = (),
    min_words: int = 2,
) -> tuple[str, str, str]:
    """The rule's verdict on `text`, as (action, kind, reason), with the preset's words of
    `language` unless `words` are given, and the `interruptions` group's defaults."""
    overlap = Overlap(
        text=text,
        no_speech_prob=no_speech_prob,
        speech_s=speech_s,
        played=played,
        language=language,
    )
    found = judge(
        overlap,
        words=words or PRESET_WORDS[language],
        no_speech_max=no_speech_max,
        captions=captions,
        min_words=min_words,
        short_words=2,
        short_s=1.6,
    )
    return (found.action, found.kind, found.reason)


def test_an_overlap_and_a_verdict_are_frozen_and_bounded() -> None:
    verdict = Verdict(action="go_on", kind="false", reason="own_words")
    with pytest.raises(ValidationError):
        OVERLAP.text = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        verdict.action = "stop"  # type: ignore[misc]
    for wrong in ({"no_speech_prob": 1.5}, {"speech_s": -1.0}, {"language": "fr"}):
        with pytest.raises(ValidationError):
            Overlap.model_validate(OVERLAP.model_dump() | wrong)
    with pytest.raises(ValidationError):
        Verdict.model_validate({"action": "pause", "kind": "stop", "reason": "stop_word"})
    assert Overlap(text="", speech_s=0.0, language="ar").played == ()


def test_a_verdicts_kind_and_reason_are_what_its_event_carries() -> None:
    verdict = Verdict(action="repeat", kind="stop", reason="repeat_word")
    event = Interrupted(call_id="c-1", at=AT, kind=verdict.kind, reason=verdict.reason)
    assert (event.kind, event.reason) == ("stop", "repeat_word")
    assert get_args(VerdictReason) == get_args(InterruptionReason)  # one list for both


@pytest.mark.parametrize("text", ["", "  ", "... !", "♪", "؟"])
def test_no_words_goes_on(text: str) -> None:
    assert judged(text) == went_on("no_words")
    assert judged(text, "ar", played=(CLAUSE,)) == went_on("no_words")


def test_text_from_silence_goes_on_and_only_with_the_filter_on() -> None:
    made_up = "some made up words here"
    assert judged(made_up, no_speech_prob=0.8, no_speech_max=0.5) == went_on("no_words")
    assert judged(made_up, no_speech_prob=0.8) == NEW_WORDS  # the threshold off
    caption = "Thanks for watching!"
    assert judged(caption, captions=CAPTIONS) == went_on("no_words")
    assert judged(caption) == NEW_WORDS  # the list off


@pytest.mark.parametrize(
    ("language", "word"),
    [(code, word) for code, words in PRESET_WORDS.items() for word in (*words.stop, *words.wait)],
)
def test_every_stop_and_wait_word_stops_anywhere_in_what_was_said(
    language: LanguageCode, word: str
) -> None:
    text = f"right {word} there" if language == "en" else f"طيب {word} شوي"
    assert judged(text, language) == STOP
    assert judged(text, language, speech_s=0.4) == STOP


def test_a_stop_word_after_the_agents_own_words_still_stops() -> None:
    assert judged("the archive screen opens, stop it", played=(CLAUSE,)) == STOP
    assert judged("فتح الأرشيف من القائمة، وقف وقف", "ar", played=(ARABIC_CLAUSE,)) == STOP


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("the bus stops here", "en"),  # a longer word holds the word, not a whole word
        ("my stopwatch broke", "en"),
        ("موقف السيارات مزحوم", "ar"),
        ("waiting for an answer", "en"),
    ],
)
def test_a_word_holding_a_stop_or_wait_word_is_not_one(text: str, language: LanguageCode) -> None:
    assert judged(text, language) == NEW_WORDS


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("لقد كف", "ar"),
        ("باكف", "ar"),
        ("ولدكف", "ar"),
        ("وكف", "ar"),
        ("بودكيف", "ar"),
        ("باك يف", "ar"),  # two words, joined
        ("قدف.", "ar"),
        ("What a gift.", "en"),
        ("What gives?", "en"),
        ("Plug if, please.", "en"),
        ("okay, waqif", "en"),
    ],
)
def test_the_stop_word_as_whisper_mishears_it_stops(text: str, language: LanguageCode) -> None:
    assert judged(text, language, speech_s=0.7) == STOP


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("كيف", went_on("too_few_words")),  # how: a question word, never the sound
        ("هل كف", NEW_WORDS),  # with a question
        ("ما كف", CORRECTION),  # with a no word
        ("موقف", went_on("short_output")),  # a noun, its first letter meem
        ("متوقف", went_on("short_output")),
        ("التطبيق انكف", went_on("short_output")),  # more than six letters in all
        ("طيب انكف الحين يا", NEW_WORDS),  # more than two words
    ],
)
def test_what_only_looks_like_the_misheard_stop_word_is_not_it(
    text: str, expected: tuple[str, str, str]
) -> None:
    assert judged(text, "ar", speech_s=0.7) == expected


def test_an_english_spelling_of_the_stop_word_in_a_sentence_is_not_it() -> None:
    assert judged("what gives me this error", speech_s=0.7) == NEW_WORDS


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("ممكن تعيدها لو سمحت؟", "ar"),
        ("اعدها من فضلك", "ar"),
        ("Can you repeat that, please?", "en"),
        ("okay, could you repeat it", "en"),
        ("Come again?", "en"),
    ],
)
def test_a_repeat_request_repeats(text: str, language: LanguageCode) -> None:
    assert judged(text, language) == REPEAT
    assert judged(text, language, speech_s=0.5) == REPEAT


@pytest.mark.parametrize(
    ("language", "word"),
    [(code, word) for code, words in PRESET_WORDS.items() for word in words.repeat],
)
def test_every_repeat_word_with_a_polite_word_repeats(language: LanguageCode, word: str) -> None:
    text = f"{word}, please" if language == "en" else f"{word} لو سمحت"
    assert judged(text, language) == REPEAT


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("I need to read my mail", "en"),
        ("repeat the last step for me", "en"),
        ("عيد الفطر قريب جدا", "ar"),  # the feast, not a request
    ],
)
def test_a_repeat_word_in_a_sentence_asks_nothing(text: str, language: LanguageCode) -> None:
    assert judged(text, language) == NEW_WORDS


@pytest.mark.parametrize(
    ("text", "language", "played"),
    [
        ("the archive screen", "en", (CLAUSE,)),
        ("archiv screens opens", "en", (CLAUSE,)),  # one letter removed, added
        ("the archivo screen", "en", ("another clause", CLAUSE)),  # one changed, any clause
        ("فتح الارشيف من القائمه", "ar", (ARABIC_CLAUSE,)),  # as the normalizer folds it
        ("والارشيف من القائمة", "ar", (ARABIC_CLAUSE,)),  # a prefix written onto it
    ],
)
def test_the_agents_own_words_heard_back_go_on(
    text: str, language: LanguageCode, played: tuple[str, ...]
) -> None:
    assert judged(text, language, played=played) == went_on("own_words")


def test_own_words_are_every_word_short_ones_as_written() -> None:
    assert judged("the archive screen is broken", played=(CLAUSE,)) == NEW_WORDS
    assert judged("the archive screenshots", played=(CLAUSE,)) == NEW_WORDS
    assert judged("no no", played=("go to the menu",)) == CORRECTION  # "go" and "to" are not it
    assert judged("the archive screen") == NEW_WORDS  # nothing played
    assert judged("all right", played=("All right, the archive opens.",)) == went_on("own_words")


@pytest.mark.parametrize(
    ("language", "word"),
    [(code, word) for code, words in PRESET_WORDS.items() for word in words.backchannel],
)
def test_listening_sounds_only_go_on(language: LanguageCode, word: str) -> None:
    sounds = PRESET_WORDS[language].backchannel
    other = sounds[1] if word == sounds[0] else sounds[0]
    assert judged(f"{word}, {other}", language, speech_s=5.0) == went_on("listening")


@pytest.mark.parametrize(
    ("text", "language", "speech_s", "expected"),
    [
        ("very nice", "en", 1.0, went_on("short_output")),
        ("حلو مره", "ar", 1.5, went_on("short_output")),
        ("طيب حلو", "ar", 1.0, went_on("short_output")),  # a listening sound beside
        ("very nice", "en", 1.6, NEW_WORDS),  # not under 1.6 s
        ("very nice indeed", "en", 1.0, NEW_WORDS),  # three words
        ("very nice?", "en", 1.0, NEW_WORDS),  # a question
        ("حلو مره؟", "ar", 1.0, NEW_WORDS),
        ("where now", "en", 1.0, NEW_WORDS),  # a question word first
        ("وش السالفه", "ar", 1.0, NEW_WORDS),
        ("ووين الملف", "ar", 1.0, NEW_WORDS),  # one after waw, and
        ("where now", "ar", 1.0, went_on("short_output")),  # each language's question words
        ("no thanks", "en", 1.0, CORRECTION),  # a no word
        ("read again", "en", 1.0, NEW_WORDS),  # a repeat word, not a repeat request
    ],
)
def test_a_short_output_goes_on_unless_it_holds_a_listed_word_or_asks(
    text: str, language: LanguageCode, speech_s: float, expected: tuple[str, str, str]
) -> None:
    assert judged(text, language, speech_s=speech_s) == expected


def test_enough_real_words_stop_a_correction_when_the_first_is_a_no_word() -> None:
    assert judged("I meant the other ticket") == NEW_WORDS
    assert judged("لا مو هذا اللي ابيه", "ar") == CORRECTION
    assert judged("اها لا مو هذا", "ar") == CORRECTION  # a listening sound is no real word
    assert judged("okay fine") == went_on("too_few_words")
    assert judged("very nice", min_words=3) == went_on("too_few_words")
    assert judged("nonsense", min_words=1) == NEW_WORDS


def test_a_teams_words_are_compared_in_the_rules_form() -> None:
    """A word written with harakat and a hamza, or holding a joiner or a direction mark, still
    matches; one that says nothing in the rule's form never matches and refuses nothing."""
    joiner, mark = chr(0x200C), chr(0x200F)
    phrases = Phrases.defaults().extend(
        stop={"en": [f"ha{joiner}lt{mark}"], "ar": ["إِيقَاف"]},
        wait={"en": ["   "]},
    )
    english, arabic = phrases.words("en"), phrases.words("ar")
    assert judged("please halt now", words=english) == STOP
    assert judged("طلبت ايقاف الرد", "ar", words=arabic) == STOP
    assert judged("some made up words", words=english) == NEW_WORDS
    assert judged("", words=english) == went_on("no_words")
