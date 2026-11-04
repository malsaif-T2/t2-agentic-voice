"""Text from silence (domain/silence.py): a transcript with no word is no words whatever the
filter's settings; one whose no-speech probability is above `stt.no_speech_max`, or that is one
of the captions Whisper invents (`CAPTIONS`, the prototype's with the music caption), is text
from silence only with that part of the filter on; a caption counts whole, in the rule's form,
joined or apart."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.silence import CAPTIONS, from_silence
from t2_agentic_voice.domain.words import rule_form

WORDS = "some made up words"


def silent(
    text: str,
    no_speech_prob: float | None = None,
    *,
    no_speech_max: float | None = None,
    captions: tuple[str, ...] = (),
) -> bool:
    return from_silence(text, no_speech_prob, no_speech_max=no_speech_max, captions=captions)


@pytest.mark.parametrize("text", ["", "   ", "...", "♪ ♪", "؟!"])
def test_no_word_at_all_is_text_from_silence_whatever_the_settings(text: str) -> None:
    assert silent(text)
    assert silent(text, 0.0, no_speech_max=0.9, captions=CAPTIONS)


def test_the_threshold_counts_a_probability_above_it_and_only_when_set() -> None:
    assert silent(WORDS, 0.51, no_speech_max=0.5)
    assert not silent(WORDS, 0.5, no_speech_max=0.5)  # at it, not above
    assert not silent(WORDS, None, no_speech_max=0.5)  # the provider gave none
    assert not silent(WORDS, 0.99)  # the threshold off


@pytest.mark.parametrize(
    "text",
    [
        "اشتركوا في القناة.",
        "ولا تنسوا الاشتراك بالقناة",
        "لا تنسى اشترك في القناه",
        "، الاشتراك في القناة",
        "ترجمة نانسي قنقر",
        "شكراً لكم على المشاهدة",
        "شكرا لل مشاهدة",  # apart, as the pattern takes it
        "شكرا لمشاهدتكم",
        "المترجم للقناة",
        "Thanks for watching!",
        "Thank you for watching.",
        "Please subscribe to my channel.",
        "Subtitles by the Amara.org community",
        "[موسيقى]",
        f"{chr(0x200F)}Thanks for watching!",  # a direction mark before it
    ],
)
def test_a_caption_is_text_from_silence_with_the_list_on(text: str) -> None:
    assert silent(text, captions=CAPTIONS)
    assert not silent(text)  # the list off


@pytest.mark.parametrize(
    "text",
    [
        "اشتركوا في القناة الجديدة لو سمحت",
        "thanks for watching the demo with me",
        "music",
    ],
)
def test_a_caption_counts_only_whole(text: str) -> None:
    assert not silent(text, captions=CAPTIONS)


def test_the_captions_are_in_the_rules_form_each_once() -> None:
    assert len(CAPTIONS) == len(set(CAPTIONS)) > 100
    assert all(rule_form(caption) == caption for caption in CAPTIONS)
    assert rule_form("موسيقى") in CAPTIONS


def test_a_list_given_is_read_in_the_rules_form() -> None:
    captions = ("A Made-Up   Caption!", "  ")
    assert silent("a made up caption", captions=captions)
    assert not silent("another text", captions=captions)
