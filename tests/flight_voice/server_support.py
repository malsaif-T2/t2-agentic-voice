"""What the flight agent's server and settings tests share: a made-up access code and join key,
the values the `environment` fixture (tests/flight_voice/conftest.py) sets; a minter that keeps
what it was asked; and the app as `build_app` builds it, over a router of the test's and a page
folder of the test's."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from fastapi import APIRouter, FastAPI
from flight_voice.airline.system import Airline
from flight_voice.server import FILES, build_app
from flight_voice.settings import AppSettings, Settings
from pydantic import SecretStr
from t2_agentic_voice import Caller, Consent, JoinSettings, VoiceSettings

from tests.flight_voice.scenario_dates import TODAY

CODE: Final = "made-up-access-code-0123"  # 24 characters
KEY: Final = "a-made-up-join-key-of-forty-bytes-0123456"
LOOPBACK: Final = ("127.0.0.1", 50000)
ELSEWHERE: Final = ("203.0.113.9", 50000)
LOCAL: Final = "http://127.0.0.1:7862"


class Minter:
    """A minter that keeps each caller and consent it was asked to mint for."""

    def __init__(self) -> None:
        self.minted: list[tuple[Caller, Consent]] = []

    def mint(self, caller: Caller, *, consent: Consent) -> str:
        self.minted.append((caller, consent))
        return "made-up-token"


def settings(**app: object) -> Settings:
    """The app's settings built in code: the made-up code, and `app`'s own."""
    voice = VoiceSettings(
        env="dev", join=JoinSettings(keys={"k1": SecretStr(KEY)}, current_kid="k1")
    )
    fields: dict[str, object] = {"access_code": SecretStr(CODE)} | app
    return Settings(app=AppSettings.model_validate(fields), voice=voice)


def web_folder(folder: Path) -> Path:
    """A page folder holding each of the page's files, each file's text its own name."""
    for name, _ in FILES.values():
        (folder / name).write_bytes(name.encode())
    return folder


def app(
    folder: Path, *, minter: Minter | None = None, airline: Airline | None = None, **given: object
) -> FastAPI:
    """The app over a router of its own, the page's files from `folder`."""
    flights = Airline(today=lambda: TODAY) if airline is None else airline
    return build_app(
        settings(**given),
        router=APIRouter(),
        minter=Minter() if minter is None else minter,
        airline=flights,
        web=web_folder(folder),
    )
