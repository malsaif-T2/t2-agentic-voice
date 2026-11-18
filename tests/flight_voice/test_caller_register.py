"""How the flight app reads the register of a caller's Arabic (caller_register.py, settings.py's
`for_the_app`): Saudi first with the app's own Saudi forms, for either agent, each unless the
environment sets it, and the register held fixed for the whole call: Saudi (Najdi) by default,
MSA with T2V_WORDS__FIXED_REGISTER=msa (the owner, 2026-11-18). The owner's call of 2026-11-18
(05:57), whose Najdi caller the library read as MSA turn after turn, reads Saudi at every turn;
with the register unset, an MSA caller still reads MSA; and the library's defaults, Ole5's,
read that call as they did."""

from __future__ import annotations

import pytest
from flight_voice.caller_register import DIALECT, REGISTER_WORDS
from flight_voice.settings import AgentKind, for_the_app, load
from t2_agentic_voice import VoiceSettings
from t2_agentic_voice.agent.language import call_register, register_of
from t2_agentic_voice.core.settings.words import WordSettings

# What the owner's call heard of the caller, turn by turn (the dev console's events).
OWNER_TURNS = (
    "السلام عليكم. كيف الحال؟",
    "شوف يا طويل العمر، ودي أروح من الرياض إلى القاهرة.",
    "امم، شوف لي الأسبوع الجاي.",
    "خلاص، أعطني الخصم.",
    "إي نعم، لو سمحت.",
    "حجزت؟",
    "إي نعم، لو سمحت.",
    "يعطيك العافية.",
)
# An MSA caller, written for the test: a plain MSA turn, then turns that hold neither register.
MSA_TURNS = ("أودّ السفر إلى الدمام يوم الأحد", "الرحلة الصباحية", "نعم، احجزها")
# An MSA caller who says none of the brief's forms (ureed, awadd, hal, ...): a wish and
# tomorrow, then turns that hold neither register.
WISHED_TURNS = ("أرغب في السفر إلى جدة غدًا", "الرحلة الصباحية من فضلك", "نعم، احجزها")


def _words(agent: AgentKind) -> WordSettings:
    return for_the_app(VoiceSettings.model_validate({"env": "test"}), agent=agent).words


@pytest.mark.parametrize("agent", ["lean", "scripted"])
def test_the_owners_call_reads_saudi_at_every_turn(agent: AgentKind) -> None:
    words = _words(agent)
    assert (words.fixed_register, words.saudi_first, words.dialect) == ("saudi", True, DIALECT)
    for n, turn in enumerate(OWNER_TURNS):
        assert call_register(OWNER_TURNS[: n + 1], words) == "saudi", n
        assert register_of(turn, dialect=words.dialect, saudi_first=True) == "saudi", n


def test_the_library_defaults_read_the_owners_call_as_msa_as_before() -> None:
    """Ole5's reading, the setting off and no form added: what the call itself was answered by."""
    for n in range(len(OWNER_TURNS)):
        assert call_register(OWNER_TURNS[: n + 1]) == "msa", n
        assert call_register(OWNER_TURNS[: n + 1], WordSettings()) == "msa", n


def test_every_call_is_najdi_by_default_and_msa_with_the_switch(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("FLIGHT_VOICE_AGENT", "lean")
    najdi = load().voice.words
    environment.setenv("T2V_WORDS__FIXED_REGISTER", "msa")
    msa = load().voice.words
    for turns in (MSA_TURNS, WISHED_TURNS, OWNER_TURNS):
        for n in range(len(turns)):
            assert call_register(turns[: n + 1], najdi) == "saudi", (turns[0], n)
            assert call_register(turns[: n + 1], msa) == "msa", (turns[0], n)


def test_an_msa_caller_still_reads_msa_with_the_register_unset() -> None:
    words = _words("lean").model_copy(update={"fixed_register": None})
    for turns in (MSA_TURNS, WISHED_TURNS):
        for n in range(len(turns)):
            assert call_register(turns[: n + 1], words) == "msa", (turns[0], n)
    assert call_register((*MSA_TURNS, "شوف لي غيرها"), words) == "saudi"  # a Saudi form


def test_each_of_the_apps_forms_reads_saudi_in_a_plain_turn() -> None:
    words = _words("lean").model_copy(update={"fixed_register": None})
    for form in DIALECT:
        assert call_register([f"نعم {form} إلى جدة"], words) == "saudi", form
        assert call_register([f"نعم {form} إلى جدة"], WordSettings()) == "msa", form


def test_the_register_words_hold_unless_the_environment_sets_them(
    environment: pytest.MonkeyPatch,
) -> None:
    assert REGISTER_WORDS == {"fixed_register": "saudi", "saudi_first": True, "dialect": DIALECT}
    environment.setenv("FLIGHT_VOICE_AGENT", "lean")
    words = load().voice.words
    assert words.saudi_first and words.dialect == DIALECT and words.send["ar"]  # send kept
    environment.setenv("T2V_WORDS__SAUDI_FIRST", "false")
    environment.setenv("T2V_WORDS__DIALECT", '["كذاك"]')
    words = load().voice.words
    assert (words.saudi_first, words.dialect) == (False, ("كذاك",)) and words.send["ar"]
