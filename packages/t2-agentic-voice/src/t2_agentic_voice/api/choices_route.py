"""An app's page's choice of a call's speech-to-text, chat model and voice (`server.call_choices`;
the owner, 2026-11-22): two routes after the router's prefix, an opt-in extension an app turns
on for its own page, each 503 `not_started` before the runtime's start. `t2v/1` still carries no
choice: its bodies refuse any field they do not name.

- `GET /choices`: the menu (api/choice_menu.py's `ChoiceMenu`): the app's offers this server
  can use, by their ids, with their providers and models, and each group's default. Never a
  key, a key's file, a path or a voice's ID. It needs no token, and is not logged: a page reads
  it each time it loads.
- `POST /choices`: one joined call's choice, before its offer: the call's ID and offer secret
  (in the body, never a URL, as `/offer` takes it) and the ids chosen, at most
  `MAX_CHOICE_BYTES`, parsed strictly. A secret that is wrong or not the call's is 403
  `forbidden`; a call whose offer was taken is 409 `already_offered`, before the choice and
  again once its voice opened (an offer sent while it opened runs on the server's own, and
  nothing is kept); an id the menu does not list in its group, 400 `invalid_request` with
  `NOT_OFFERED`, and a voice that cannot be opened 400 with `VOICE_UNAVAILABLE`, neither naming
  a value sent. Answered 204; logged as
  `call_choice_made` with the call's ID and the ids kept (the menu's), or `call_choice_refused`
  with the reason alone; never the secret.

No dev page, no `env` and no loopback rule: a call is proven by its ID and offer secret, which
only its join gave, so whoever holds an access code that mints a token may choose among the
app's offers (the owner, 2026-11-22).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Final

from fastapi import APIRouter, Request, Response
from pydantic import SecretStr, ValidationError

from t2_agentic_voice.api.call_options import CallChoice
from t2_agentic_voice.api.choice_calls import CallChoices
from t2_agentic_voice.api.http_errors import Refusal, add_routes, read_body
from t2_agentic_voice.api.offers import CallRecords
from t2_agentic_voice.api.protocol import ErrorBody
from t2_agentic_voice.core.ids import CallId
from t2_agentic_voice.core.logging import get_logger

# The most bytes `POST /choices` reads: a call's ID and offer secret, and three short ids.
MAX_CHOICE_BYTES: Final = 1024
NOT_OFFERED: Final = (
    "This server offers no such choice: GET choices lists the speech-to-text, models and "
    "voices it can use."
)
VOICE_UNAVAILABLE: Final = (
    "That voice could not be opened just now: start the call again, or choose another."
)
_HEADERS: Final = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}

_log = get_logger(__name__)


class ChoiceAsk(CallChoice):
    """`POST /choices`' body: the joined call and its offer secret, and its choice."""

    call_id: CallId
    offer_secret: SecretStr

    def choice(self) -> CallChoice:
        """The choice alone."""
        return CallChoice(stt=self.stt, model=self.model, voice=self.voice)


def mount_choices(
    router: APIRouter,
    *,
    choices: CallChoices,
    records: CallRecords,
    running: Callable[[], object | None],
) -> None:
    """Add the two routes to `router` (the module's docstring)."""

    async def menu_route(request: Request, reference: str) -> Response:
        if running() is None or choices.menu is None:
            raise Refusal(503, "not_started")
        text = json.dumps(choices.menu.model_dump(mode="json"), separators=(",", ":"))
        return Response(text, media_type="application/json", headers=_HEADERS)

    async def choose_route(request: Request, reference: str) -> Response:
        if running() is None:
            raise Refusal(503, "not_started")
        body = await read_body(request, MAX_CHOICE_BYTES)
        try:
            ask = ChoiceAsk.model_validate_json(body)
        except ValidationError:
            raise Refusal(400, "invalid_request") from None
        record = records.find(ask.call_id, ask.offer_secret.get_secret_value())
        if record is None:
            raise Refusal(403, "forbidden")
        if record.offer != "none":
            raise Refusal(409, "already_offered")
        chosen = await choices.choose(
            record.call_id, ask.choice(), unoffered=lambda: record.offer == "none"
        )
        if chosen == "already_offered":
            raise Refusal(409, "already_offered")
        if chosen != "kept":
            _log.info("call_choice_refused", call_id=record.call_id, reason=chosen)
            message = NOT_OFFERED if chosen == "not_offered" else VOICE_UNAVAILABLE
            refused = ErrorBody(code="invalid_request", message=message, reference=reference)
            raise Refusal(400, "invalid_request", body=refused)
        kept = choices.menu.normalized(ask.choice()) if choices.menu else ask.choice()
        _log.info("call_choice_made", call_id=record.call_id, **kept.model_dump())
        return Response(status_code=204)

    add_routes(router, ("GET", "/choices", menu_route), ("POST", "/choices", choose_route))
