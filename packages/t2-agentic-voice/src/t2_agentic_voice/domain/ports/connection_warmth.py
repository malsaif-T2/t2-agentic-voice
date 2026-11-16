"""Whether a provider's next request goes out on a connection already open, and the request
that opens one: two ports of their own beside the provider ports (domain/ports/chat_model.py,
speech_to_text.py), so no provider or fake of one changes (TD-089, TD-115).

- `ConnectionWarmth.warm()` says whether the next request goes out on a kept-alive connection.
  voice reads it as a call joins (voice/join_warmth.py): a chat model whose connection is warm
  is sent no warming request. A provider that does not implement it counts as cold there.
  `warm_now` reads it just before each chat request, the talker's (agent/turn_answer.py) and
  the session's own (voice/session/model_word.py), as the request's warm flag in the turn's
  metrics and log lines: None from a provider that does not say.
- `WarmUp.warm_up()` sends the provider's cheapest request that opens its connection, one
  that costs nothing (a list of its models), so the call's first real request does not pay
  the TLS handshake. It raises the provider's failure, which voice logs by its type and which
  never fails a call. A provider that does not implement it is sent none.

Both ports are runtime-checkable, for those checks.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ConnectionWarmth(Protocol):
    """Whether the next request goes out on a kept-alive connection."""

    def warm(self) -> bool:
        """True when the next request goes out on a connection already open."""


@runtime_checkable
class WarmUp(Protocol):
    """One request that opens the provider's connection and costs nothing."""

    async def warm_up(self) -> None:
        """Send it; raise the provider's failure (a ProviderError) when it fails."""


def warm_now(provider: object) -> bool | None:
    """Whether `provider`'s next request goes out on a kept-alive connection; None when it does
    not say (it does not implement `ConnectionWarmth`)."""
    return provider.warm() if isinstance(provider, ConnectionWarmth) else None
