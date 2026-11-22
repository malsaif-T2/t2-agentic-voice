"""The reply language of a turn (agent/language.py; plan 006, item 8): the heard language,
overruled by the turn's script only when it plainly says otherwise, mapped to the agent's tag,
the call's own first. Held (`words.hold_reply_language`, in a call whose language never moves,
set on the turn by the session), a short turn takes the caller's last plain language: under
`session` a switched caller's "Yes please" was answered as the call's Arabic, with the Saudi
voice. A longer turn that mixes the two scripts is answered as it was heard."""

from __future__ import annotations

import pytest
from t2_agentic_voice.agent.events import SpokenClause
from t2_agentic_voice.agent.language import reply_language
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import Conversation, PastTurn, TalkerTurn, TurnFate
from t2_agentic_voice.core.settings.stt import LiveLanguage, SttSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import WordSettings

from tests.t2_agentic_voice.agent.chat_support import (
    ENGLISH,
    INSTRUCTIONS,
    SAUDI,
    FakeChat,
    agent,
    reply,
    said,
    talker,
)

SPOKEN: list[LanguageTag] = ["ar-SA", "ar", "en"]


def _language(words: str, heard: str | None, call: LanguageTag = "ar-SA") -> LanguageTag:
    turn = TalkerTurn(turn_id=0, words=words, language=heard)
    return reply_language(turn, call=call, spoken=SPOKEN)


@pytest.mark.parametrize(
    ("words", "heard", "call", "expected"),
    [
        ("ابي اغير كلمة السر", "ar", "ar-SA", "ar-SA"),
        ("أريد تغيير كلمة المرور", "ar", "ar-SA", "ar-SA"),  # MSA: the tag stays, the prompt asks
        ("ابي اغير كلمة السر", "ar", "ar", "ar"),  # the call's own Arabic tag
        ("How do I change my password?", "en", "ar-SA", "en"),
        ("How do I change my password?", "ar", "ar-SA", "en"),  # Latin letters in an Arabic call
        ("VPN Outlook Teams ما يشتغل", "ar", "ar-SA", "ar-SA"),  # product terms stay Arabic
        ("Outlook ما يفتح", "ar", "ar-SA", "ar-SA"),
        ("ابي اغير كلمة السر لو سمحت", "en", "en", "ar-SA"),  # Arabic letters in an English call
        ("hello", None, "en", "en"),
        ("hello", "Arabic", "en", "ar-SA"),  # a provider's name of the language
        ("مرحبا", "fr", "ar", "ar"),  # a language the agent has no tag for: the call's
    ],
)
def test_the_reply_follows_the_turns_language(
    words: str, heard: str | None, call: LanguageTag, expected: LanguageTag
) -> None:
    assert _language(words, heard, call) == expected


def test_an_agent_with_no_tag_in_the_language_keeps_the_calls() -> None:
    turn = TalkerTurn(turn_id=0, words="How do I change my password?", language="en")
    assert reply_language(turn, call="ar-SA", spoken=["ar-SA"]) == "ar-SA"


def test_a_turn_that_asked_for_a_language_is_answered_in_it() -> None:
    """A spoken switch request heard in Arabic (`TalkerTurn.asked`) is answered in English; a
    language the agent does not speak is not followed."""
    asked = TalkerTurn(turn_id=0, words="بالانجليزي لو سمحت", language="ar", asked="en")
    assert reply_language(asked, call="ar-SA", spoken=SPOKEN) == "en"
    other = TalkerTurn(turn_id=0, words="ابي اغير كلمة السر", language="ar", asked="fr")
    assert reply_language(other, call="ar-SA", spoken=SPOKEN) == "ar-SA"


ENGLISH_ASKED = "How do I change my password?"
SAUDI_ASKED = "ابي اغير كلمة السر"  # abi aghayyir kalimat assir, I want to change my password


def _held(
    words: str,
    *before: str,
    held: bool = True,
    asked: str | None = None,
    fate: TurnFate = "answered",
) -> LanguageTag:
    """The tag of the reply to `words`, heard in Arabic as under `session`, in an ar-SA call
    whose caller said `before` first, each turn's fate `fate`; `held`, the session's
    `TalkerTurn.hold_language`."""
    past = tuple(PastTurn(turn_id=n, words=w, fate=fate) for n, w in enumerate(before))
    turn = TalkerTurn(
        turn_id=len(before),
        words=words,
        language="ar",
        asked=asked,
        hold_language=held,
        conversation=Conversation(turns=past),
    )
    return reply_language(turn, call="ar-SA", spoken=SPOKEN)


@pytest.mark.parametrize(
    ("words", "before", "expected"),
    [
        ("Yes please", (ENGLISH_ASKED,), "en"),  # the switch holds through the short reply
        ("okay", (), "ar-SA"),  # no plain earlier turn: the call's
        ("okay", ("hello", "تمام"), "ar-SA"),  # none of them plain either
        ("OK", (ENGLISH_ASKED, SAUDI_ASKED), "ar-SA"),  # the newest plain one, Arabic
        ("Yes please", (ENGLISH_ASKED, "okay"), "en"),  # past a short one
        ("تمام", (SAUDI_ASKED,), "ar-SA"),  # tamam, fine: an Arabic caller's short turn
        (SAUDI_ASKED, (ENGLISH_ASKED,), "ar-SA"),  # a plain turn decides by its own words
        (ENGLISH_ASKED, (SAUDI_ASKED,), "en"),
    ],
)
def test_held_a_short_turn_keeps_the_callers_last_plain_language(
    words: str, before: tuple[str, ...], expected: LanguageTag
) -> None:
    assert _held(words, *before) == expected


@pytest.mark.parametrize(
    "words",
    [
        "ابي احجز business class على Saudia",  # abi ahjiz ... ala: three words of each script
        "ابي اغير الحجز الى economy class",  # abi aghayyir al-hajz ila: four Arabic, two Latin
    ],
)
def test_held_a_longer_turn_that_mixes_the_two_is_answered_as_it_was_heard(words: str) -> None:
    """No short reply: a returning Saudi caller's sentence with English terms in it, after an
    English turn, stays Arabic, as with the rule off; only a turn under `SWITCH_WORDS` words in
    each script is held."""
    assert _held(words, ENGLISH_ASKED) == "ar-SA"
    assert _held(words, ENGLISH_ASKED, held=False) == "ar-SA"
    assert _held("okay تمام", ENGLISH_ASKED) == "en"  # short, though it mixes them: held


def test_not_held_a_short_turn_is_answered_as_it_was_heard() -> None:
    assert _held("Yes please", ENGLISH_ASKED, held=False) == "ar-SA"
    assert _held(ENGLISH_ASKED, SAUDI_ASKED, held=False) == "en"


def test_held_a_turn_that_asked_still_wins_and_a_dropped_turn_says_nothing() -> None:
    assert _held("okay", ENGLISH_ASKED, asked="ar-SA") == "ar-SA"
    assert _held("okay", SAUDI_ASKED, asked="en") == "en"
    assert _held("Yes please", ENGLISH_ASKED, fate="dropped") == "ar-SA"  # the agent's own voice


@pytest.mark.parametrize(
    ("live", "hold", "turn_holds", "expected"),
    [
        ("session", True, True, "en"),
        ("session", False, False, "ar-SA"),  # the library's default, as it was
        ("detected", True, True, "en"),  # the call's settings, not the talker's, decide
        ("session", True, False, "ar-SA"),
    ],
)
def test_the_talker_holds_a_short_turn_as_the_session_set_it_on_the_turn(
    live: LiveLanguage, hold: bool, turn_holds: bool, expected: LanguageTag
) -> None:
    """The talker's prompt and its clauses' tag (agent/turn.py) follow the turn's
    `hold_language`, which the session sets from the call's settings (voice/session/talking.py),
    whatever the talker's own: a call whose speech-to-text the dev console picked runs on
    settings of its own, its talker on the runtime's."""
    settings = VoiceSettings(
        env="test",
        stt=SttSettings(live_language=live),
        words=WordSettings(hold_reply_language=hold),
    )
    model = FakeChat(said("Sure."))
    chat = talker(
        model, language="ar-SA", settings=settings, declared=agent(languages=(SAUDI, ENGLISH))
    )
    past = (PastTurn(turn_id=0, words=ENGLISH_ASKED, fate="answered"),)
    turn = TalkerTurn(
        turn_id=1,
        words="Yes please",
        language="ar",
        hold_language=turn_holds,
        conversation=Conversation(turns=past),
    )
    [clause] = [e for e in reply(chat, turn) if isinstance(e, SpokenClause)]
    assert clause.language == expected
    assert INSTRUCTIONS[expected] in model.requests[0].messages[0].content
