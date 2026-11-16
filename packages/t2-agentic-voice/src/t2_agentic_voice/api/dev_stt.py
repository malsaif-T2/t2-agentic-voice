"""The test console's choice of speech-to-text (api/dev_console.py; the owner, 2026-11-16): two
routes after the router's prefix, mounted with the console alone and admitted as its others are
(`env` dev, a loopback client, a loopback `Host`), each 503 `not_started` before the runtime's
start.

- `GET /dev/stt`: the menu (api/stt_choices.py's `SttMenu`): the providers this process can use,
  each with its models, the language modes and the settings' own choice. Never a key, a key's
  file or its path.
- `POST /dev/stt`: one joined call's choice, before its offer: the call's ID and offer secret
  (in the body, never a URL, as `/offer` takes it) and the provider, model and language mode, at
  most `MAX_CHOICE_BYTES`. A secret that is missing, wrong or not the call's is 403 `forbidden`;
  a call whose offer was taken is 409 `already_offered`; a choice the menu does not hold, 400
  `invalid_request` with `NOT_OFFERED`, which names no value sent. Answered 204; logged as
  `stt_chosen` with the call's ID and the choice, never the secret.

`t2v/1` carries no choice: its bodies refuse any field they do not name, so a production join
token or an app's own page cannot choose one.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from fastapi import APIRouter, Request, Response
from pydantic import JsonValue, SecretStr, ValidationError

from t2_agentic_voice.api.http_errors import Refusal, add_routes, read_body
from t2_agentic_voice.api.offers import CallRecords
from t2_agentic_voice.api.protocol import ErrorBody
from t2_agentic_voice.api.stt_calls import CallStts
from t2_agentic_voice.api.stt_choices import SttChoice
from t2_agentic_voice.core.ids import CallId
from t2_agentic_voice.core.logging import get_logger

# The most bytes `POST /dev/stt` reads: a call's ID and offer secret, and three short names.
MAX_CHOICE_BYTES: Final = 1024
NOT_OFFERED: Final = (
    "This process offers no such speech-to-text choice: GET dev/stt lists the providers, "
    "models and language modes it can use."
)

_log = get_logger(__name__)


class SttAsk(SttChoice):
    """`POST /dev/stt`'s body: the joined call and its offer secret, and its choice."""

    call_id: CallId
    offer_secret: SecretStr

    def choice(self) -> SttChoice:
        """The choice alone."""
        return SttChoice(provider=self.provider, model=self.model, live_language=self.live_language)


def mount_stt(
    router: APIRouter,
    *,
    choices: CallStts,
    records: CallRecords,
    admitted: Callable[[Request], None],
    json: Callable[[dict[str, JsonValue]], Response],
) -> None:
    """Add the two routes to `router` (the module's docstring), each first `admitted`."""

    async def menu_route(request: Request, reference: str) -> Response:
        admitted(request)
        if choices.menu is None:
            raise Refusal(503, "not_started")
        return json(choices.menu.model_dump(mode="json"))

    async def choose_route(request: Request, reference: str) -> Response:
        admitted(request)
        body = await read_body(request, MAX_CHOICE_BYTES)
        try:
            ask = SttAsk.model_validate_json(body)
        except ValidationError:
            raise Refusal(400, "invalid_request") from None
        record = records.find(ask.call_id, ask.offer_secret.get_secret_value())
        if record is None:
            raise Refusal(403, "forbidden")
        if record.offer != "none":
            raise Refusal(409, "already_offered")
        choice = ask.choice()
        if not choices.choose(record.call_id, choice):
            refused = ErrorBody(code="invalid_request", message=NOT_OFFERED, reference=reference)
            raise Refusal(400, "invalid_request", body=refused)
        _log.info("stt_chosen", call_id=record.call_id, **choice.model_dump())
        return Response(status_code=204)

    add_routes(router, ("GET", "/dev/stt", menu_route), ("POST", "/dev/stt", choose_route))
