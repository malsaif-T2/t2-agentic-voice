"""A send word said alone (domain/yes_rule.py's `decide` and `judged`; D-082, the owner's third
ruling of 2026-11-10): «أرسلها», «توكل», "go ahead", "send it", alone or among fillers, are
`askable`, the lists' answer to them unchanged (asked again, so an agent that does not ask hears
them as before); for an agent that asks, the model's word decides within the rails, and the
echo rail reads only a line still heard as the speech began: the read-back's over the closing
question, and each line while its reply played or within its tail after it ended (the drop
rule's, which the session tells), or when the session cannot tell. Words that copy a line said
when none was heard are the caller's own. The ask-again lines are the library's
(domain/presets.py); the read-back is made up, its closing question "Shall I send it?" and
«أرسل الطلب؟». Adversarial (GP-08): the closing question and the ask-again line heard back as
they play or just after, judged send; a send word alone judged agreement only over the
question."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.yes_inputs import HEARD_WORDS_SEAL, HeardWords, ReadBackReceipt
from t2_agentic_voice.domain.presets import ACTION_LINES
from t2_agentic_voice.domain.yes_rule import (
    AskAgain,
    Correction,
    ModelWord,
    SaidLines,
    Yes,
    YesOutcome,
    decide,
    is_confirmed,
    judged,
)
from t2_agentic_voice.domain.yes_words import consent_words
from t2_agentic_voice.voice.session.read_back import played_receipt

ARABIC, ENGLISH = consent_words("ar"), consent_words("en")
SUMMARY_AT, QUESTION_AT = 10.0, 12.0  # the summary's last clause played, the question's
OVER_QUESTION, AFTER = 11.0, 12.5
READ_BACK = (
    "I'll book room R-204 for: the projector is broken.",
    "Shall I send it?",
    "بحجز لك الغرفة R-204.",  # baHjiz lak al-ghurfa: I'll book you the room
    "أرسل الطلب؟",  # arsil aT-Talab?: send the request?
)
# "Sorry, I didn't catch that. Shall I go ahead?"; «...asajjil at-talab?», shall I register it?
ASKED_AGAIN = (ACTION_LINES["en"]["asked_again"], ACTION_LINES["ar-SA"]["asked_again"])
# Send words alone that copy the closing question, and that copy none of the read-back's lines.
COPYING = ["send it", "أرسل"]  # arsil: send
OWN = ["go ahead", "proceed", "أرسلها", "توكل"]  # arsilha: send it; tawakkal: go ahead
SEND_ALONE = [*COPYING, *OWN]
YES_WORDS: list[ModelWord] = ["send", "yes"]
NO_WORD: list[ModelWord] = ["unclear", None]  # None: the check failed or timed out


def _heard(text: str, speech_at: float) -> HeardWords:
    values = {"turn_id": 7, "text": text, "language": "en", "at": speech_at + 1.0}
    values |= {"speech_at": speech_at, "source": "speech_to_text"}
    return HeardWords.model_validate(values, context=HEARD_WORDS_SEAL)


def _receipt(question_ended_at: float | None = QUESTION_AT) -> ReadBackReceipt:
    return played_receipt(
        action="open_request",
        draft_json='{"summary": "made up"}',
        reply_id=4,
        summary_played_at=SUMMARY_AT,
        question_ended_at=question_ended_at,
    )


def _said(*, reading: bool = False, asking: bool = False) -> SaidLines:
    """The lines, the session telling whether the speech began over the read-back's reply
    (`reading`, its tail included) and over the ask-again line (`asking`)."""
    return SaidLines(
        read_back=READ_BACK,
        asked_again=ASKED_AGAIN,
        over_read_back=reading,
        over_asked_again=asking,
    )


def _judged(
    word: ModelWord,
    text: str,
    speech_at: float,
    *,
    asking: bool = False,
    said: SaidLines | None = None,
) -> YesOutcome:
    """`judged` on `text`; `asking`, whether the speech began while the ask-again line played."""
    lines = said or _said(asking=asking)
    words = ENGLISH if text.isascii() else ARABIC
    receipt = _receipt()
    heard = _heard(text, speech_at)
    return judged(word, heard, receipt, current=receipt, words=words, env="prod", said=lines)


def _sends(outcome: YesOutcome) -> bool:
    return isinstance(outcome, Yes) and is_confirmed(outcome.confirmed)


@pytest.mark.parametrize(
    "text",
    [*SEND_ALONE, "do it", "send it please", "أرسلها لو سمحت"],  # law samaht: please
)
@pytest.mark.parametrize("speech_at", [OVER_QUESTION, AFTER])
def test_a_send_word_alone_is_askable_and_still_asked_again_by_the_lists(
    text: str, speech_at: float
) -> None:
    """An agent that does not ask takes the lists' answer, unchanged: asked again."""
    words = ENGLISH if text.isascii() else ARABIC
    outcome = decide(_heard(text, speech_at), _receipt(), words=words, env="prod")
    assert outcome == AskAgain() and isinstance(outcome, AskAgain) and outcome.askable


@pytest.mark.parametrize("text", ["send it?", "أرسلها؟", "go ahead, no"])
def test_a_send_word_with_a_question_mark_or_a_no_is_the_lists_alone(text: str) -> None:
    words = ENGLISH if text.isascii() else ARABIC
    outcome = decide(_heard(text, AFTER), _receipt(), words=words, env="prod")
    assert not isinstance(outcome, Correction | AskAgain) or not outcome.askable
    for word in ("send", "yes"):
        assert not _sends(_judged(word, text, AFTER))


@pytest.mark.parametrize("text", SEND_ALONE)
def test_once_the_question_ended_a_send_word_alone_sends_on_the_models_send_or_yes(
    text: str,
) -> None:
    for agreed in YES_WORDS:
        outcome = _judged(agreed, text, AFTER)
        assert _sends(outcome) and isinstance(outcome, Yes)
        assert (outcome.confirmed.words, outcome.confirmed.speech_at) == (text, AFTER)
    for word in NO_WORD:
        assert _judged(word, text, AFTER) == AskAgain()


@pytest.mark.parametrize("text", OWN)
def test_over_the_question_a_send_word_alone_sends_only_on_the_models_send(text: str) -> None:
    assert _sends(_judged("send", text, OVER_QUESTION))
    for word in ("yes", *NO_WORD):
        assert _judged(word, text, OVER_QUESTION) == AskAgain()


@pytest.mark.parametrize("text", COPYING)
@pytest.mark.parametrize("word", ["send", "yes"])
def test_over_the_question_a_send_word_that_copies_it_is_its_echo(
    text: str, word: ModelWord
) -> None:
    assert _judged(word, text, OVER_QUESTION) == AskAgain()


@pytest.mark.parametrize("text", ["Shall I send it", "أرسل الطلب", "the projector is broken"])
def test_the_read_back_said_once_it_ended_with_nothing_playing_is_the_models_to_judge(
    text: str,
) -> None:
    """Speech begun when no line played cannot be the agent's echo: the words are judged on
    the model's word and the other rails alone."""
    assert _sends(_judged("send", text, AFTER))
    assert _judged("send", text, OVER_QUESTION) == AskAgain()  # heard as the question played


@pytest.mark.parametrize("speech_at", [OVER_QUESTION, AFTER])
@pytest.mark.parametrize("text", ["go ahead", "Shall I go ahead", "أسجل الطلب"])
def test_the_ask_again_line_heard_back_as_it_plays_is_its_echo(text: str, speech_at: float) -> None:
    """The library's ask-again lines: "Shall I go ahead?" holds a send word; «asajjil
    at-talab?», shall I register the request, holds none, and is unplaced."""
    for word in ("send", "yes"):
        assert _judged(word, text, speech_at, asking=True) == AskAgain()
    assert _sends(_judged("send", text, AFTER))  # said once it ended


@pytest.mark.parametrize(
    ("text", "asking"),
    [
        ("the projector is broken, shall I send it", False),  # the summary's end into the question
        ("الغرفة أرسل الطلب", False),  # al-ghurfa arsil aT-Talab: the same, in Arabic
        ("shall I sent it", False),  # a word one letter off
        ("سجل الطلب", True),  # sajjil at-talab: «asajjil at-talab» with its first letter clipped
        ("سجل", True),  # sajjil: register, the same word alone
    ],
)
@pytest.mark.parametrize("word", ["send", "yes"])
def test_the_agents_words_heard_back_across_its_lines_or_one_letter_off_are_its_echo(
    text: str, asking: bool, word: ModelWord
) -> None:
    """Invariant 1: the rail reads the lines still heard as the interruption rule reads the
    clauses that played (domain/interruptions.py's `own_words`): every word heard a word of
    those lines together, or one edit from one of three letters or more, so an echo that runs
    across two lines, or that Whisper writes a letter off, confirms nothing whatever the model
    says; over the closing question, or over the ask-again line (`asking`)."""
    speech_at = AFTER if asking else OVER_QUESTION
    assert _judged(word, text, speech_at, asking=asking) == AskAgain()


@pytest.mark.parametrize("text", ["send it", "أرسلها", "توكل"])
def test_words_that_copy_no_ask_again_line_send_while_it_plays(text: str) -> None:
    assert _sends(_judged("send", text, AFTER, asking=True))


@pytest.mark.parametrize(
    ("gap", "within"),
    [(0.1, True), (0.25, True), (0.4, False)],
    ids=["0.1s", "0.25s", "0.4s"],
)
@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("send it", "read_back"),  # a run of "Shall I send it?"
        ("Shall I send it", "read_back"),
        ("أرسل", "read_back"),  # arsil: send, a run of «arsil aT-Talab?»
        ("go ahead", "asked_again"),  # a run of "... Shall I go ahead?"
        ("أسجل الطلب", "asked_again"),  # asajjil at-talab: a run of «... asajjil at-talab?»
    ],
)
def test_a_line_heard_back_within_its_replys_tail_is_its_echo(
    text: str, line: str, gap: float, within: bool
) -> None:
    """Speech begun `gap` seconds after the line ended, once the closing question ended: within
    its reply's tail (the drop rule's `DROP_AFTER_S`, 0.3 s, which the session tells) the agent's
    voice is still heard, so its words are its echo whatever the model says; past it, the
    caller's own, and the model's `send` confirms."""
    reading, asking = within and line == "read_back", within and line == "asked_again"
    ended = QUESTION_AT if line == "read_back" else AFTER
    said = _said(reading=reading, asking=asking)
    outcome = _judged("send", text, ended + gap, said=said)
    if within:
        assert outcome == AskAgain()
        assert _judged("yes", text, ended + gap, said=said) == AskAgain()
    else:
        assert _sends(outcome)


def test_lines_the_session_cannot_place_keep_the_rail() -> None:
    """`SaidLines` built with no word of when the read-back or its ask-again line played keeps
    the rail for both."""
    unplaced = SaidLines(read_back=READ_BACK, asked_again=ASKED_AGAIN)
    assert unplaced.over_read_back and unplaced.over_asked_again
    assert _judged("send", "go ahead", AFTER, said=unplaced) == AskAgain()
    assert _judged("send", "send it", AFTER, said=unplaced) == AskAgain()
