"""An app's call options and their menu (api/call_options.py, api/choice_menu.py;
`server.call_choices`, the owner, 2026-11-22): the offers are refused when two share an id, an
id is not one, or none is given; each is held to the settings when the runtime builds its
router; the menu lists only the offers whose provider's key is set, Groq's always, and never a
key, a key's file or a voice's ID; each group's default is the settings' own; a choice's
settings differ from the runtime's in `stt`, `llm` and `tts` alone; and the guide's sample
(docs/guide/browser-client.md) builds its router."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from t2_agentic_voice.api.call_options import (
    CallChoice,
    CallOptions,
    ModelOffer,
    SttOffer,
    VoiceOffer,
)
from t2_agentic_voice.api.choice_menu import check_options, menu_of, settings_of
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.logging import FIELDS
from t2_agentic_voice.core.settings.llm import LlmSettings
from t2_agentic_voice.core.settings.provider_keys import TelnyxSettings
from t2_agentic_voice.core.settings.server import ServerSettings
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.core.settings.tts_voices import TtsVoice, default_voices

from tests.leaks import holding, shown
from tests.t2_agentic_voice.api.choice_support import (
    BAYAN,
    ELEVEN_KEY,
    GROQ_KEY,
    KEY_FILE,
    OPENAI_KEY,
    OPTIONS,
    TELNYX_KEY,
    VOICE_IDS,
    choice_settings,
)
from tests.t2_agentic_voice.api.runtime_support import AGENT, FakeIdentity, Harness

pytestmark = pytest.mark.usefixtures("patched_stores")

WHISPER = SttOffer(id="whisper", provider="groq", model="whisper-large-v3")


@pytest.mark.parametrize(
    "given",
    [
        {"stt": (WHISPER, WHISPER)},
        {"stt": ({"id": "Whisper!", "provider": "groq", "model": "whisper-large-v3"},)},
        {"stt": ({"id": "x" * 41, "provider": "groq", "model": "whisper-large-v3"},)},
        {},
        {"stt": ({"id": "w", "provider": "klingon", "model": "whisper-large-v3"},)},
    ],
    ids=["shared-id", "not-an-id", "long-id", "none", "no-such-provider"],
)
def test_options_that_are_not_offers_are_refused(given: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CallOptions.model_validate(given)


@pytest.mark.parametrize(
    ("options", "group", "offer"),
    [
        (CallOptions(stt=(SttOffer(id="odd", provider="groq", model="scribe_v3"),)), "stt", "odd"),
        (
            CallOptions(models=(ModelOffer(id="gpt", model="gpt-5.5", reasoning_effort="medium"),)),
            "models",
            "gpt",
        ),
        (
            CallOptions(
                voices=(
                    VoiceOffer(id="mixed", provider="groq", languages=default_voices("telnyx")),
                )
            ),
            "voices",
            "mixed",
        ),
        (
            CallOptions(
                voices=(VoiceOffer(id="english", provider="telnyx", languages={"en": BAYAN["en"]}),)
            ),
            "voices",
            "english",
        ),
    ],
    ids=["stt-model", "effort", "voice-of-another", "missing-tag"],
)
def test_an_offer_that_does_not_fit_the_settings_stops_the_router(
    options: CallOptions, group: str, offer: str, tmp_path: Path
) -> None:
    settings = choice_settings(tmp_path)
    with pytest.raises(ConfigurationError) as raised:
        check_options(settings, options)
    assert raised.value.details == {"group": group, "offer": offer}
    assert group in str(raised.value) and "FIX:" in str(raised.value)
    harness = Harness(settings, call_options=options)
    with pytest.raises(ConfigurationError):
        harness.runtime.router()


def test_the_guides_sample_builds_its_router_and_the_bare_tts_voices_do_not(
    tmp_path: Path,
) -> None:
    """docs/guide/browser-client.md's sample, as written: Orpheus offered with Groq's own voices
    fits, so the router is built; the bare `TtsSettings()` holds ElevenLabs' voices, which a
    Groq offer does not take."""
    agent, settings, tokens = AGENT, choice_settings(tmp_path), FakeIdentity()
    from t2_agentic_voice import TtsSettings, VoiceRuntime
    from t2_agentic_voice.server import CallOptions, ModelOffer, SttOffer, VoiceOffer

    orpheus = TtsSettings(provider="groq").languages
    options = CallOptions(
        stt=(
            SttOffer(id="whisper", provider="groq", model="whisper-large-v3"),
            SttOffer(id="scribe", provider="elevenlabs", model="scribe_v3"),
        ),
        models=(ModelOffer(id="gpt-5.5", model="gpt-5.5", reasoning_effort="none"),),
        voices=(VoiceOffer(id="orpheus", provider="groq", languages=orpheus),),
    )
    runtime = VoiceRuntime(agent, settings=settings, identity=tokens, call_options=options)
    runtime.router()
    bare = VoiceOffer(id="orpheus", provider="groq", languages=TtsSettings().languages)
    with pytest.raises(ConfigurationError) as raised:
        check_options(settings, CallOptions(voices=(bare,)))
    assert raised.value.details == {"group": "voices", "offer": "orpheus"}


def test_the_setting_on_with_no_options_names_the_setting_to_turn_off(tmp_path: Path) -> None:
    harness = Harness(choice_settings(tmp_path))
    with pytest.raises(ConfigurationError) as raised:
        harness.runtime.router()
    assert "T2V_SERVER__CALL_CHOICES=false" in str(raised.value)
    assert "call_options=CallOptions" in str(raised.value)


def test_options_with_the_setting_off_are_ignored_and_said_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    harness = Harness(choice_settings(tmp_path, on=False), call_options=OPTIONS)
    harness.runtime.router()
    assert harness.runtime._choices is None
    assert [r.getMessage() for r in caplog.records].count("call_choices_off") == 1
    assert harness.runtime.call_choice("c-1") is None


def test_the_menu_lists_each_offer_whose_key_is_set_and_groqs_always(tmp_path: Path) -> None:
    keyed = menu_of(choice_settings(tmp_path), OPTIONS)
    assert [o.id for o in keyed.stt] == ["whisper", "scribe"]
    assert [o.id for o in keyed.models] == ["gpt-oss-120b", "gpt-5.5"]
    assert [o.id for o in keyed.voices] == ["orpheus", "eleven", "bayan"]
    assert keyed.models[1].provider == "openai" and keyed.models[1].reasoning_effort == "none"
    assert keyed.voices[2].models == ("Telnyx.Bayan",)
    bare = menu_of(choice_settings(tmp_path / "bare", keys=False), OPTIONS)
    assert ([o.id for o in bare.stt], [o.id for o in bare.models]) == (
        ["whisper"],
        ["gpt-oss-120b"],
    )
    assert [o.id for o in bare.voices] == ["orpheus"]


def test_a_key_file_that_cannot_be_read_leaves_its_provider_out_unnamed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    missing = tmp_path / "nowhere" / KEY_FILE
    settings = choice_settings(tmp_path, telnyx=TelnyxSettings(api_key_file=missing))
    caplog.set_level(logging.DEBUG)
    menu = menu_of(settings, OPTIONS)
    assert [o.id for o in menu.voices] == ["orpheus", "eleven"]
    (line,) = [r for r in caplog.records if r.getMessage() == "call_choice_unavailable"]
    assert getattr(line, FIELDS) == {"provider": "telnyx", "failure": "ConfigurationError"}
    assert holding(str(missing), shown(caplog=caplog)) == []
    assert holding(KEY_FILE, shown(caplog=caplog)) == []


def test_the_menu_holds_no_key_no_key_file_and_no_voice_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    menu = menu_of(choice_settings(tmp_path), OPTIONS)
    surfaces = {"menu": menu.model_dump_json(), **shown(caplog=caplog)}
    secrets = (GROQ_KEY, ELEVEN_KEY, OPENAI_KEY, TELNYX_KEY, KEY_FILE, str(tmp_path))
    for value in (*secrets, *VOICE_IDS):
        assert holding(value, surfaces) == [], value


def test_each_groups_default_is_the_settings_own_or_none(tmp_path: Path) -> None:
    menu = menu_of(choice_settings(tmp_path), OPTIONS)
    assert menu.default == CallChoice(stt="whisper", model="gpt-oss-120b", voice="orpheus")
    scribe = choice_settings(
        tmp_path / "s",
        stt=SttSettings(provider="elevenlabs"),
        llm=LlmSettings(reasoning_effort="high"),
    )
    other = menu_of(scribe, OPTIONS)
    assert other.default == CallChoice(stt="scribe", model=None, voice="orpheus")
    assert other.normalized(CallChoice(stt="scribe", voice="bayan")) == CallChoice(voice="bayan")
    assert other.allows(CallChoice(model="gpt-5.5"))
    assert not other.allows(CallChoice(model="scribe")) and not other.allows(CallChoice(stt="x"))


def test_a_choices_settings_differ_in_stt_llm_and_tts_alone(tmp_path: Path) -> None:
    settings = choice_settings(tmp_path, server=ServerSettings(call_choices=True, dev_page=True))
    before = settings.model_dump()
    chosen = settings_of(
        settings, OPTIONS, CallChoice(stt="scribe", model="gpt-5.5", voice="bayan")
    )
    groups = {"stt", "llm", "tts"}
    assert chosen.model_dump(exclude=groups) == settings.model_dump(exclude=groups)
    assert (chosen.stt.provider, chosen.stt.live_language) == ("elevenlabs", "session")
    assert (chosen.llm.provider, chosen.llm.model, chosen.llm.reasoning_effort) == (
        "openai",
        "gpt-5.5",
        "none",
    )
    assert chosen.llm.timeout_s == settings.llm.timeout_s
    assert chosen.tts.provider == "telnyx" and dict(chosen.tts.languages) == BAYAN
    assert chosen.tts.cache_clauses == settings.tts.cache_clauses
    assert chosen.prefix == settings.prefix and settings.model_dump() == before
    assert settings_of(settings, OPTIONS, CallChoice()) is settings
    english = TtsVoice(model="Telnyx.Bayan", voice="Michael")
    assert chosen.tts.languages["en"] == english
