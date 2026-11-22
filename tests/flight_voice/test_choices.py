"""The call choices the flight page offers under Options (flight_voice/choices.py; the owner's
request of 2026-11-22): exactly the owner's list of speech-to-text, models with their efforts
and voices; held by the library's own checks as the app's server builds its router; listed by
the keys the server holds, the Groq ones always, each group's default the settings' own; and
`server.call_choices` turned on by `for_the_app` unless the environment sets it, under dev and
not, the dev caller still the demo traveler under dev."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from flight_voice import server
from flight_voice.choices import BAYAN, CALL_OPTIONS
from flight_voice.settings import for_the_app, load
from flight_voice.traveler import demo_caller
from t2_agentic_voice import TtsVoice, VoiceSettings
from t2_agentic_voice.api.choice_menu import menu_of
from t2_agentic_voice.core.settings.tts_voices import ELEVENLABS_ARABIC, ELEVENLABS_ENGLISH
from t2_agentic_voice.server import CallChoice

GROQ_KEY = "made-up-groq-key"


def test_the_options_are_the_owners_list() -> None:
    stt = [(o.id, o.provider, o.model) for o in CALL_OPTIONS.stt]
    assert stt == [("whisper", "groq", "whisper-large-v3"), ("scribe", "elevenlabs", "scribe_v3")]
    models = [(o.id, o.provider, o.model, o.reasoning_effort) for o in CALL_OPTIONS.models]
    assert models == [
        ("gpt-oss-120b", "groq", "openai/gpt-oss-120b", "medium"),
        ("gpt-5.5", "openai", "gpt-5.5", "none"),
        ("gpt-6-luna", "openai", "gpt-6-luna", "none"),
        ("gpt-5.4-mini", "openai", "gpt-5.4-mini", "none"),
    ]
    voices = {o.id: (o.provider, dict(o.languages)) for o in CALL_OPTIONS.voices}
    assert list(voices) == ["orpheus", "eleven-v4-turbo", "eleven-v4", "telnyx-bayan"]
    abdullah = TtsVoice(model="canopylabs/orpheus-arabic-saudi", voice="abdullah")
    troy = TtsVoice(model="canopylabs/orpheus-v1-english", voice="troy")
    assert voices["orpheus"] == ("groq", {"ar-SA": abdullah, "ar": abdullah, "en": troy})
    for offer, model in (("eleven-v4-turbo", "eleven_v4_turbo"), ("eleven-v4", "eleven_v4")):
        arabic = TtsVoice.model_validate({"model": model, "voice": ELEVENLABS_ARABIC})
        english = TtsVoice.model_validate({"model": model, "voice": ELEVENLABS_ENGLISH})
        assert voices[offer] == ("elevenlabs", {"ar-SA": arabic, "ar": arabic, "en": english})
    jasem, michael = TtsVoice(model=BAYAN, voice="Jasem"), TtsVoice(model=BAYAN, voice="Michael")
    assert voices["telnyx-bayan"] == ("telnyx", {"ar-SA": jasem, "ar": jasem, "en": michael})


def test_the_apps_server_builds_its_router_with_the_options(
    environment: pytest.MonkeyPatch,
) -> None:
    """The library's checks (`check_options`) run as the router is built, so an offer the
    settings could not run (a model its provider lacks, an effort it refuses, a voice of another
    provider, a missing language) would stop the app here; off, the routes are not served."""
    environment.setenv("T2V_GROQ__API_KEY", GROQ_KEY)
    loaded = load()
    assert loaded.voice.server.call_choices
    served = TestClient(server.make_app(loaded)).get("/voice/choices")
    assert served.status_code == 503  # served, its menu built as the runtime starts
    environment.setenv("T2V_SERVER__CALL_CHOICES", "false")
    assert TestClient(server.make_app(load())).get("/voice/choices").status_code == 404


def test_the_menu_lists_by_the_keys_held_the_settings_own_its_default(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("T2V_GROQ__API_KEY", GROQ_KEY)
    bare = menu_of(load().voice, CALL_OPTIONS)
    assert [o.id for o in bare.stt] == ["whisper", "scribe"]  # Scribe is the settings' own
    assert [o.id for o in bare.models] == ["gpt-oss-120b"]
    assert [o.id for o in bare.voices] == ["orpheus"]
    assert bare.default == CallChoice(stt="scribe", model="gpt-oss-120b", voice="orpheus")
    for name in ("ELEVENLABS", "OPENAI", "TELNYX"):
        environment.setenv(f"T2V_{name}__API_KEY", f"made-up-{name.lower()}-key")
    keyed = menu_of(load().voice, CALL_OPTIONS)
    assert [o.id for o in keyed.models] == [o.id for o in CALL_OPTIONS.models]
    assert [o.id for o in keyed.voices] == [o.id for o in CALL_OPTIONS.voices]
    shown = keyed.model_dump_json()
    for secret in ("made-up", GROQ_KEY, ELEVENLABS_ARABIC, "Jasem"):
        assert secret not in shown


@pytest.mark.parametrize("env", ["dev", "staging"])
def test_the_app_turns_the_call_choices_on_and_keeps_the_environments(env: str) -> None:
    assert not VoiceSettings(env="test").server.call_choices  # off in the library (GP-18)
    voice = VoiceSettings(env=env)  # type: ignore[arg-type]
    app = for_the_app(voice)
    assert app.server.call_choices
    assert app.server.dev_caller == (demo_caller() if env == "dev" else None)
    off = for_the_app(VoiceSettings.model_validate({"env": env, "server": {"call_choices": False}}))
    assert not off.server.call_choices
    assert off.server.dev_caller == (demo_caller() if env == "dev" else None)
