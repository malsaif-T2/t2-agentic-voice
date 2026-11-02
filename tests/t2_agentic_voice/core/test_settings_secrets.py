"""The settings' secrets (the design's 7.5; docs/SECURITY.md, invariant 5): each a `SecretStr`
with a `_file` form whose file holds the value; a join key and the TURN secret at least 32 bytes,
a shorter one refused with a FIX line that makes one; and none in any repr, log line or error."""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import get_args

import pytest
from pydantic import SecretStr
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.logging import configure_logging, get_logger
from t2_agentic_voice.core.settings.base import GENERATOR, MIN_SECRET_BYTES
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.join import JoinSettings
from t2_agentic_voice.core.settings.server import ServerSettings

from tests.leaks import holding, shown
from tests.t2_agentic_voice.core.settings_support import LONG_SECRET, MADE_UP_KEY, PREFIX, fields

SECRET_NAME = re.compile(r"(^|_)(key|keys|secret|token|password)$")
SHORT = "made-up-31-bytes-secret-0123456"  # one byte short
SECRETS = [("groq", "api_key"), ("server", "turn_secret"), ("join", "keys")]


def test_every_secret_setting_is_a_secret_str_with_a_file_form() -> None:
    found = dict(fields())
    named = [location for location in found if SECRET_NAME.search(location[-1])]
    assert named == SECRETS
    assert get_args(found[("join", "keys")])[1] is SecretStr  # each key of the map
    assert all(found[loc] == SecretStr | None for loc in named if loc[-1] != "keys")
    assert all((*loc[:-1], f"{loc[-1]}_file") in found for loc in named)


def test_a_secret_shorter_than_32_bytes_is_refused_as_the_settings_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RFC 7518, 3.2 for an HS256 key; the TURN secret is held to the same. The FIX line gives
    a command that makes one, and the error never shows the secret."""
    assert (len(SHORT.encode()), len(LONG_SECRET.encode())) == (MIN_SECRET_BYTES - 1, 40)
    monkeypatch.setenv(f"{PREFIX}ENV", "test")
    for name, value in (("JOIN__KEYS", f'{{"k1": "{SHORT}"}}'), ("SERVER__TURN_SECRET", SHORT)):
        monkeypatch.setenv(f"{PREFIX}{name}", value)
        with pytest.raises(ConfigurationError) as raised:
            VoiceSettings.from_env()
        monkeypatch.delenv(f"{PREFIX}{name}")
        error = raised.value
        assert error.message.startswith(f"{PREFIX}{name} holds a secret shorter than 32 bytes")
        assert error.message.endswith(f"FIX: make a new one with {GENERATOR}")
        assert error.details == {"setting": f"{PREFIX}{name}"}
        assert holding(SHORT, shown(error)) == []
        assert (error.__cause__, error.__context__) == (None, None)
    with pytest.raises(ConfigurationError, match=f"{PREFIX}SERVER__TURN_SECRET holds a secret"):
        ServerSettings(turn_secret=SecretStr(SHORT))  # built in code too


def test_the_generator_makes_a_secret_long_enough() -> None:
    made = secrets.token_urlsafe(48)
    assert JoinSettings(keys={"k1": SecretStr(made)}).resolved_keys()["k1"].get_secret_value()
    assert GENERATOR == 'python -c "import secrets; print(secrets.token_urlsafe(48))"'


@pytest.mark.parametrize("value", [f"{LONG_SECRET} x", f"{LONG_SECRET}\nx", f"{LONG_SECRET}é"])
def test_a_secret_with_a_character_no_key_holds_is_refused(value: str) -> None:
    with pytest.raises(ConfigurationError, match="holds a character no API key holds"):
        ServerSettings(turn_secret=SecretStr(value))
    with pytest.raises(ConfigurationError, match=f"{PREFIX}JOIN__KEYS holds a character"):
        JoinSettings(keys={"k1": SecretStr(value)})


def test_the_turn_secret_comes_from_the_setting_or_its_file(tmp_path: Path) -> None:
    path = tmp_path / "turn.secret"
    path.write_bytes(b"\xef\xbb\xbf" + LONG_SECRET.encode() + b"\r\n")  # a BOM, a line end
    assert ServerSettings(turn_secret_file=path).resolved_turn_secret() == SecretStr(LONG_SECRET)
    inline = ServerSettings(turn_secret=SecretStr(f" {LONG_SECRET} "), turn_secret_file=path)
    assert inline.resolved_turn_secret() == SecretStr(LONG_SECRET)
    assert ServerSettings(turn_secret=SecretStr("  ")).turn_secret is None  # blank: unset
    assert ServerSettings().resolved_turn_secret() is None
    path.write_text(SHORT, encoding="utf-8")
    with pytest.raises(ConfigurationError, match=f"{PREFIX}SERVER__TURN_SECRET_FILE holds a"):
        ServerSettings(turn_secret_file=path).resolved_turn_secret()
    path.write_text("\n", encoding="utf-8")
    assert ServerSettings(turn_secret_file=path).resolved_turn_secret() is None


def test_the_join_keys_come_from_the_setting_or_its_file(tmp_path: Path) -> None:
    """The file holds the same JSON object as the setting: key ID to secret."""
    path = tmp_path / "join.keys"
    path.write_text(f'{{"2026-11": "{LONG_SECRET}", "old": "{LONG_SECRET}"}}\n', "utf-8")
    from_file = JoinSettings(keys_file=path, current_kid="2026-11").resolved_keys()
    assert from_file == {"2026-11": SecretStr(LONG_SECRET), "old": SecretStr(LONG_SECRET)}
    inline = JoinSettings(keys={"k1": SecretStr(LONG_SECRET)}, keys_file=path)
    assert list(inline.resolved_keys()) == ["k1"]
    assert JoinSettings().resolved_keys() == {}
    path.write_text("  ", encoding="utf-8")
    assert JoinSettings(keys_file=path).resolved_keys() == {}


@pytest.mark.parametrize(
    ("contents", "why"),
    [
        (f'{{"k1": "{SHORT}"}}', "holds a secret shorter than 32 bytes"),
        (f'{{"k 1": "{LONG_SECRET}"}}', "does not hold one JSON object"),  # no key ID
        (f'["{LONG_SECRET}"]', "does not hold one JSON object"),
        (f'{{"k1": "{LONG_SECRET}"', "does not hold one JSON object"),  # cut short
        (f"k1={LONG_SECRET}", "does not hold one JSON object"),
        (f'{{"k1": "{LONG_SECRET}"}}', "names no key"),  # current_kid is "k2"
    ],
)
def test_a_join_key_file_is_refused_never_showing_its_contents(
    tmp_path: Path, contents: str, why: str
) -> None:
    path = tmp_path / "join.keys"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ConfigurationError, match=why) as raised:
        JoinSettings(keys_file=path, current_kid="k2").resolved_keys()
    for each in (SHORT, LONG_SECRET, str(path)):
        assert holding(each, shown(raised.value)) == []
    assert (raised.value.__cause__, raised.value.__context__) == (None, None)


@pytest.mark.parametrize("kind", ["a folder", "a missing file", "an undecodable file"])
def test_an_unreadable_secret_file_names_the_setting_never_its_contents(
    tmp_path: Path, kind: str
) -> None:
    path = {"a folder": tmp_path, "a missing file": tmp_path / "nope.key"}.get(
        kind, tmp_path / "bad.key"
    )
    if kind == "an undecodable file":
        path.write_bytes(b"\xff" + MADE_UP_KEY.encode())
    checks: list[tuple[Callable[[], object], str]] = [
        (lambda: GroqSettings(api_key_file=path).resolved_api_key(), "GROQ__API_KEY_FILE"),
        (lambda: JoinSettings(keys_file=path).resolved_keys(), "JOIN__KEYS_FILE"),
        (lambda: ServerSettings(turn_secret_file=path).resolved_turn_secret(), "SERVER__TURN_"),
    ]
    for resolve, setting in checks:
        with pytest.raises(ConfigurationError) as raised:
            resolve()
        assert f"{PREFIX}{setting}" in raised.value.message
        assert holding(MADE_UP_KEY, shown(raised.value)) == []
        assert holding(str(path), shown(raised.value)) == []
        # Not even out of sight: a decode error holds the file's bytes, the key with them.
        assert (raised.value.__cause__, raised.value.__context__) == (None, None)


def test_a_current_kid_the_inline_map_does_not_list_is_refused_as_the_settings_load() -> None:
    with pytest.raises(ConfigurationError, match=f"{PREFIX}JOIN__CURRENT_KID names no key"):
        JoinSettings(keys={"k1": SecretStr(LONG_SECRET)}, current_kid="k2")
    assert JoinSettings(keys={"k1": SecretStr(LONG_SECRET)}, current_kid="k1").current_kid == "k1"


def test_a_secret_file_error_names_the_setting_under_its_prefix(tmp_path: Path) -> None:
    path = tmp_path / "turn.secret"
    path.write_text(SHORT, encoding="utf-8")
    with pytest.raises(ConfigurationError, match=r"^HELPDESK_VOICE_SERVER__TURN_SECRET_FILE"):
        ServerSettings(turn_secret_file=path).resolved_turn_secret("HELPDESK_VOICE_")


def test_the_groq_key_comes_from_the_setting_or_its_file(tmp_path: Path) -> None:
    key_file = tmp_path / "groq.key"
    key_file.write_text(f"  {MADE_UP_KEY}\n", encoding="utf-8")
    empty = tmp_path / "empty.key"
    empty.write_text("\n", encoding="utf-8")
    assert GroqSettings(api_key=SecretStr(f" {MADE_UP_KEY} ")).resolved_api_key() == SecretStr(
        MADE_UP_KEY
    )
    from_file = GroqSettings(api_key=SecretStr("  "), api_key_file=key_file)
    assert from_file.resolved_api_key() == SecretStr(MADE_UP_KEY)
    assert GroqSettings(api_key_file=empty).resolved_api_key() is None
    assert GroqSettings().resolved_api_key() is None


def test_a_key_file_saved_with_a_byte_order_mark_gives_the_bare_key(tmp_path: Path) -> None:
    """Notepad's "UTF-8 with BOM", or Windows PowerShell 5.1's `Set-Content -Encoding UTF8`."""
    key_file = tmp_path / "groq.key"
    key_file.write_bytes(b"\xef\xbb\xbf" + MADE_UP_KEY.encode() + b"\r\n")
    assert GroqSettings(api_key_file=key_file).resolved_api_key() == SecretStr(MADE_UP_KEY)


@pytest.mark.parametrize(
    "contents",
    [
        f"{MADE_UP_KEY}\n# the eval key\n",  # a second line: a comment
        f"{MADE_UP_KEY}\r\n# the eval key\r\n",
        f"gsk_made up {MADE_UP_KEY}",  # a space inside
        f"gsk_made\t{MADE_UP_KEY}",
        f"{MADE_UP_KEY}​",  # a zero-width space, pasted with it
    ],
)
def test_a_key_file_holding_more_than_the_key_is_refused(tmp_path: Path, contents: str) -> None:
    """Such a key fails in the HTTP client, whose error holds the whole header, and reads as a
    lost connection that is asked again; so it is refused as it is read."""
    key_file = tmp_path / "groq.key"
    key_file.write_text(contents, encoding="utf-8", newline="")
    with pytest.raises(ConfigurationError) as raised:
        GroqSettings(api_key_file=key_file).resolved_api_key()
    assert raised.value.details == {"setting": f"{PREFIX}GROQ__API_KEY_FILE"}
    assert holding(MADE_UP_KEY, shown(raised.value)) == []


@pytest.mark.parametrize(
    "key", [f"{MADE_UP_KEY}\rx", f"{MADE_UP_KEY}\nx", f"{MADE_UP_KEY}\x00x", f"​{MADE_UP_KEY}"]
)
def test_a_key_with_a_character_no_key_holds_is_refused(key: str) -> None:
    with pytest.raises(ConfigurationError) as raised:
        GroqSettings(api_key=SecretStr(key)).resolved_api_key()
    assert raised.value.details == {"setting": f"{PREFIX}GROQ__API_KEY"}
    assert holding(MADE_UP_KEY, shown(raised.value)) == []


def test_no_secret_appears_in_a_repr_or_a_log_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """Invariant 5, for every secret and its file form, as built in code and as loaded."""
    (key_file := tmp_path / "groq.key").write_text(MADE_UP_KEY, encoding="utf-8")
    (turn_file := tmp_path / "turn.secret").write_text(LONG_SECRET, encoding="utf-8")
    (keys_file := tmp_path / "join.keys").write_text(f'{{"k1": "{LONG_SECRET}"}}', "utf-8")
    inline = VoiceSettings.model_validate(
        {
            "env": "test",
            "groq": {"api_key": MADE_UP_KEY},
            "server": {"turn_secret": LONG_SECRET},
            "join": {"keys": {"k1": LONG_SECRET}, "current_kid": "k1"},
        }
    )
    files = VoiceSettings.model_validate(
        {
            "env": "test",
            "groq": {"api_key_file": key_file},
            "server": {"turn_secret_file": turn_file},
            "join": {"keys_file": keys_file},
        }
    )
    configure_logging("DEBUG", "json")  # tests/conftest.py puts the defaults back
    log = get_logger("tests.settings")
    caplog.set_level(logging.DEBUG)
    resolved = []
    for each in (inline, files):
        found = (
            each.groq.resolved_api_key(),
            each.server.resolved_turn_secret(),
            each.join.resolved_keys(),
        )
        resolved.append(found)
        log.info("settings_read", settings=each, groups=(each.groq, each.server, each.join))
        log.info("secrets_read", secrets=found)
        logging.getLogger("some.library").warning("settings %s %r", each, each.join)
    surfaces = shown(caplog=caplog, capsys=capsys)
    for index, each in enumerate((inline, files)):
        texts = [repr(each), str(each), each.model_dump_json(), repr(each.model_dump())]
        surfaces[f"settings {index}"] = "\n".join([*texts, repr(resolved[index])])
    assert surfaces["stdout"].count("settings_read") == 2
    assert holding(MADE_UP_KEY, surfaces) == [] and holding(LONG_SECRET, surfaces) == []
    assert resolved[0][2]["k1"].get_secret_value() == LONG_SECRET  # but they are there


def test_from_env_notes_that_groq_api_key_is_set_never_its_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The design's 7.3: the library reads only its own names; `from_env` notes the other's
    name, so the Groq adapter's error can say which one to set (its test: test_groq_stt.py)."""
    monkeypatch.setenv(f"{PREFIX}ENV", "test")
    assert not VoiceSettings.from_env().saw("GROQ_API_KEY")
    monkeypatch.setenv("GROQ_API_KEY", MADE_UP_KEY)
    settings = VoiceSettings.from_env()
    assert settings.saw("GROQ_API_KEY") and settings.groq.resolved_api_key() is None
    assert settings.model_copy().saw("GROQ_API_KEY")  # a copy keeps it
    assert not VoiceSettings(env="test").saw("GROQ_API_KEY")  # built in code: nothing read
    assert MADE_UP_KEY not in repr(settings) + str(vars(settings))
