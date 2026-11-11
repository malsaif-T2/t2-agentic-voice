"""A chat model's `no` and `change` on an answer to a read-back (domain/yes_rule.py's `judged`;
D-082 as amended by the owner's answer of 2026-11-11): a question, about the action or anything
else, or a request for something else, said in answer to the read-back, holds words on none of
the lists, so an agent that asks puts it to the model, whose instruction calls it a no. The
model's `no` is declined: the turn goes to the talker, which answers in its own words.

One rail keeps the agent's echo from cancelling a read-back: a model's `no` or `change` on words
that are the agent's own lines heard back, begun while those lines were still heard (over the
closing question, within the read-back's tail, or over the ask-again line), is asked again, as
its `yes` is. The same words begun once the lines and their tail ended are the caller's own: the
model's `no` is declined and its `change` a correction. The ask-again lines are the library's
(domain/presets.py); the read-back is made up. Every word and time here is made up for the
test."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.yes_inputs import HEARD_WORDS_SEAL, HeardWords, ReadBackReceipt
from t2_agentic_voice.domain.presets import ACTION_LINES
from t2_agentic_voice.domain.yes_rule import (
    AskAgain,
    Correction,
    Declined,
    ModelWord,
    SaidLines,
    YesOutcome,
    decide,
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
# "Sorry, I didn't catch that. Shall I go ahead?"; Saudi «...asajjil at-talab?» and MSA «...hal
# usajjil at-talab?», shall I register the request?
ASKED_AGAIN = (
    ACTION_LINES["en"]["asked_again"],
    ACTION_LINES["ar-SA"]["asked_again"],
    ACTION_LINES["ar"]["asked_again"],
)
QUESTIONS = [
    "How do I reset my password?",
    # Tayyib, kaif aghayyir kalimat al-muroor?: OK, how do I change the password? (Saudi)
    "طيب كيف أغير كلمة المرور؟",
    # kaifa yumkinunii taghyeer kalimat al-muroor?: how can I change the password? (MSA)
    "كيف يمكنني تغيير كلمة المرور؟",
]
SOMETHING_ELSE = [
    "No thanks, I want to open another ticket.",
    "Can I talk to a person?",
    # alghiha, abi aftaH tadhkara thaanya: cancel it, I want to open another ticket (Saudi)
    "الغيها، أبي أفتح تذكرة ثانية",
    # ureed at-taHadduth ilaa muwaZZaf: I want to talk to an employee (MSA)
    "أريد التحدث إلى موظف",
]
# The agent's own lines heard back: the closing question (a question itself) and a piece of the
# summary, in each language.
READ_BACK_ECHOES = ["Shall I send it?", "the projector is broken", "أرسل الطلب"]
TURNING_AWAY: list[ModelWord] = ["no", "change"]


def _heard(text: str, speech_at: float) -> HeardWords:
    values = {"turn_id": 7, "text": text, "language": "en", "at": speech_at + 1.0}
    values |= {"speech_at": speech_at, "source": "speech_to_text"}
    return HeardWords.model_validate(values, context=HEARD_WORDS_SEAL)


def _receipt() -> ReadBackReceipt:
    return played_receipt(
        action="open_request",
        draft_json='{"summary": "made up"}',
        reply_id=4,
        summary_played_at=SUMMARY_AT,
        question_ended_at=QUESTION_AT,
    )


def _judged(
    word: ModelWord, text: str, speech_at: float, *, reading: bool = False, asking: bool = False
) -> YesOutcome:
    """`judged` on `text`, the session telling whether the speech began while the read-back's
    reply, its tail included, was still heard (`reading`), and the ask-again line (`asking`)."""
    said = SaidLines(
        read_back=READ_BACK,
        asked_again=ASKED_AGAIN,
        over_read_back=reading,
        over_asked_again=asking,
    )
    words = ENGLISH if text.isascii() else ARABIC
    receipt = _receipt()
    heard = _heard(text, speech_at)
    return judged(word, heard, receipt, current=receipt, words=words, env="prod", said=said)


def _turned_away(word: ModelWord, text: str) -> YesOutcome:
    """What the model's `no` or `change` on the caller's own words is: declined, or a
    correction."""
    return Declined(words=text) if word == "no" else Correction(words=text)


@pytest.mark.parametrize("text", [*QUESTIONS, *SOMETHING_ELSE, *READ_BACK_ECHOES, *ASKED_AGAIN])
@pytest.mark.parametrize("speech_at", [OVER_QUESTION, AFTER])
def test_a_question_a_request_for_something_else_and_the_agents_lines_are_askable(
    text: str, speech_at: float
) -> None:
    """The lists cannot place them: an agent that does not ask takes their answer as is."""
    words = ENGLISH if text.isascii() else ARABIC
    outcome = decide(_heard(text, speech_at), _receipt(), words=words, env="prod")
    assert isinstance(outcome, Correction | AskAgain) and outcome.askable


@pytest.mark.parametrize("text", [*QUESTIONS, *SOMETHING_ELSE])
@pytest.mark.parametrize("speech_at", [OVER_QUESTION, AFTER])
def test_a_models_no_on_a_question_or_a_request_for_something_else_is_declined(
    text: str, speech_at: float
) -> None:
    """The owner's answer of 2026-11-11: the read-back is dropped and the turn goes to the
    talker, its words whole, so it answers the question or proposes the new action."""
    assert _judged("no", text, speech_at) == Declined(words=text)


@pytest.mark.parametrize("text", READ_BACK_ECHOES)
@pytest.mark.parametrize("word", TURNING_AWAY)
def test_a_models_no_or_change_on_the_read_back_heard_back_as_it_plays_is_asked_again(
    text: str, word: ModelWord
) -> None:
    """Over the closing question, or within the read-back's tail, its own lines are its echo,
    never the caller's answer, even when they are a question."""
    assert _judged(word, text, OVER_QUESTION) == AskAgain()
    assert _judged(word, text, AFTER, reading=True) == AskAgain()


@pytest.mark.parametrize("text", [*ASKED_AGAIN, "shall I go ahead"])
@pytest.mark.parametrize("speech_at", [OVER_QUESTION, AFTER])
@pytest.mark.parametrize("word", TURNING_AWAY)
def test_a_models_no_or_change_on_the_ask_again_line_heard_back_as_it_plays_is_asked_again(
    text: str, speech_at: float, word: ModelWord
) -> None:
    assert _judged(word, text, speech_at, asking=True) == AskAgain()


@pytest.mark.parametrize("text", [*READ_BACK_ECHOES, *ASKED_AGAIN])
@pytest.mark.parametrize("word", TURNING_AWAY)
def test_the_same_words_begun_after_the_lines_and_their_tail_are_the_callers_own(
    text: str, word: ModelWord
) -> None:
    """Speech begun when none of the lines was heard cannot be the agent's echo: the model's
    `no` is declined, its `change` a correction."""
    assert _judged(word, text, AFTER) == _turned_away(word, text)
