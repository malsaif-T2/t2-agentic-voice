"""Built settings cannot change (core/settings/base.py): assigning to a field, or deleting one,
raises a TypeError naming it, never the value; a map setting is read-only; a group object given
to the settings, one copied with a change included, is checked again; and a frozen group, its
maps among them, hashes."""

from __future__ import annotations

import copy
import pickle
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import SecretStr
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.base import ReadOnlyMap
from t2_agentic_voice.core.settings.join import JoinSettings
from t2_agentic_voice.core.settings.tts import TtsSettings, TtsVoice

from tests.leaks import holding, shown
from tests.t2_agentic_voice.core.settings_support import LONG_SECRET, MADE_UP_KEY, PREFIX

ENGLISH = TtsVoice(model="canopylabs/orpheus-v1-english", voice="troy")


def test_a_map_setting_cannot_change_once_loaded() -> None:
    """A group is read-only, its maps too, so no join key under 32 bytes reaches
    `resolved_keys` past the check and no call changes the voice every call shares; each map
    still dumps as the plain object it was given as."""
    loaded = VoiceSettings.model_validate(
        {"env": "test", "join": {"keys": {"k1": LONG_SECRET}, "current_kid": "k1"}}
    )
    copies = (
        loaded.model_copy(deep=True),
        copy.deepcopy(loaded),
        pickle.loads(pickle.dumps(loaded)),  # noqa: S301 - loads only bytes it dumped
    )
    for settings in (loaded, VoiceSettings(env="test"), *copies):
        keys: Any = settings.join.keys
        languages: Any = settings.tts.languages
        with pytest.raises(TypeError):
            keys["weak"] = SecretStr("short")
        with pytest.raises(TypeError):
            languages["en"] = languages["ar"]
        with pytest.raises(TypeError):
            keys._items["weak"] = SecretStr("short")
        dumped = settings.model_dump()
        assert type(dumped["join"]["keys"]) is dict and type(dumped["tts"]["languages"]) is dict
    assert all(each == loaded for each in copies)
    assert list(loaded.join.resolved_keys()) == ["k1"]
    assert loaded.model_dump(mode="json")["join"]["keys"] == {"k1": "**********"}
    assert LONG_SECRET not in repr(loaded.join.keys) and "k1" in repr(loaded.join.keys)


@pytest.mark.parametrize(
    ("group", "field"),
    [(None, "env"), ("groq", "api_key"), ("server", "turn_secret"), ("join", "keys"), (None, "x")],
)
def test_a_change_to_built_settings_names_the_setting_never_the_value(
    group: str | None, field: str
) -> None:
    """pydantic's own frozen error shows the value assigned, here a key set after load; the
    settings' names the setting, says they are read-only and how to build others, and a
    deletion fails the same way."""
    data = {"env": "dev", "server": {"turn_secret": LONG_SECRET}}
    settings = VoiceSettings.model_validate(data)
    target = settings if group is None else getattr(settings, group)
    changes: list[Callable[[], None]] = [
        lambda: setattr(target, field, MADE_UP_KEY),
        lambda: setattr(target, field, SecretStr(MADE_UP_KEY)),
        lambda: delattr(target, field),
    ]
    for change in changes:
        with pytest.raises(TypeError) as raised:
            change()
        assert str(raised.value) == (
            f"{type(target).__name__}.{field} cannot change: settings are read-only once built. "
            "FIX: build new settings that hold the value, with VoiceSettings(...) or "
            "from_env(...)."
        )
        assert holding(MADE_UP_KEY, shown(raised.value)) == []
        assert (raised.value.__cause__, raised.value.__context__) == (None, None)
    assert settings == VoiceSettings.model_validate(data)  # nothing changed


def test_a_voice_inside_a_map_and_a_private_attribute_cannot_change_either() -> None:
    """The prefix `from_env` sets is pydantic's to set, and no code's to delete."""
    settings = VoiceSettings(env="test")
    voice: Any = settings.tts.languages["en"]
    with pytest.raises(TypeError, match=r"^TtsVoice\.voice cannot change"):
        voice.voice = "another"
    with pytest.raises(TypeError, match=r"^VoiceSettings\._prefix cannot change"):
        del settings._prefix
    assert settings.prefix == PREFIX


def _copied_join() -> JoinSettings:
    """A join group copied the pydantic way with a 4-byte key, which no check saw."""
    strong = JoinSettings(keys={"k1": SecretStr(LONG_SECRET)}, current_kid="k1")
    return strong.model_copy(update={"keys": {"k1": SecretStr("weak")}})


def test_a_group_copied_with_a_change_is_checked_again_as_the_settings_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`model_copy(update=...)` skips a group's checks; given to the settings, in code or as
    `from_env`'s code value (which takes a group object whole), the group is validated again,
    so a join key under 32 bytes never loads."""
    monkeypatch.setenv(f"{PREFIX}ENV", "prod")
    copied = _copied_join()
    assert type(copied.keys) is dict  # the copy itself: no check ran
    builds: list[Callable[[], object]] = [
        lambda: VoiceSettings(env="prod", join=copied),
        lambda: VoiceSettings.model_validate({"env": "prod", "join": copied}),
        lambda: VoiceSettings.from_env(join=copied),
    ]
    for build in builds:
        with pytest.raises(ConfigurationError) as raised:
            build()
        why = f"{PREFIX}JOIN__KEYS (Value error, holds a secret shorter than 32 bytes"
        assert raised.value.message.startswith(f"These settings cannot load: {why}")
        assert (raised.value.__cause__, raised.value.__context__) == (None, None)


def test_a_group_object_given_to_the_settings_holds_read_only_maps() -> None:
    """A tts group copied with a plain map loads with a read-only one, which no call can change,
    and one copied with a tag the settings refuse does not load."""
    copied = TtsSettings(provider="groq").model_copy(update={"languages": {"en": ENGLISH}})
    languages: Any = VoiceSettings(env="test", tts=copied).tts.languages
    with pytest.raises(TypeError):
        languages["ar"] = ENGLISH
    assert type(languages) is ReadOnlyMap and dict(languages) == {"en": ENGLISH}
    unlisted = TtsSettings(provider="groq").model_copy(update={"languages": {"xx": ENGLISH}})
    with pytest.raises(ConfigurationError, match=f"cannot load: {PREFIX}TTS__LANGUAGES "):
        VoiceSettings(env="test", tts=unlisted)


def test_a_frozen_group_holding_a_map_hashes() -> None:
    """A read-only map hashes as its entries do, two equal maps alike, so the groups that hold
    one, and the settings, hash too; a map whose values do not hash does not hash either."""
    one, two = (JoinSettings(keys={"k1": SecretStr(LONG_SECRET)}) for _ in range(2))
    assert one == two and hash(one) == hash(two) and hash(one.keys) == hash(two.keys)
    assert hash(TtsSettings()) == hash(TtsSettings())
    built = {VoiceSettings(env="test"), VoiceSettings(env="test"), VoiceSettings(env="dev")}
    assert len(built) == 2
    with pytest.raises(TypeError):
        hash(ReadOnlyMap({"k": []}))
