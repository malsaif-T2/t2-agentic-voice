"""Everything the talker is given over a ticket system, in one place (plan 007): the three actions
(actions.py) and the status tool (status.py), all over the same system, so a status reads what the
actions made; and the settings it runs under, whose guard reads a number said as the caller's
ticket number as a claim of any of the three (lines.py's `NUMBER_CLAIMS`; the owner's ruling of
2026-11-10).
"""

from __future__ import annotations

from t2_agentic_voice import DeclaredTool, GuardSettings, VoiceSettings

from ole5_voice.tickets.actions import add_ticket_note, create_ticket, hand_off
from ole5_voice.tickets.lines import NUMBER_CLAIMS
from ole5_voice.tickets.status import ticket_status
from ole5_voice.tickets.system import TicketSystem


def ticket_tools(system: TicketSystem) -> tuple[DeclaredTool, ...]:
    """`create_ticket`, `add_ticket_note`, `hand_off` and `ticket_status`, each over `system`."""
    return (
        create_ticket(system),
        add_ticket_note(system),
        hand_off(system),
        ticket_status(system),
    )


def with_ticket_claims(settings: VoiceSettings) -> VoiceSettings:
    """`settings` with `NUMBER_CLAIMS` added to the guard's phrases that claim any action
    (`guard.claims`), after those the settings hold, each once, every other setting as it was:
    what the talker given `ticket_tools` runs under, in the server and in run A."""
    claims: dict[str, list[str]] = {
        code: list(held) for code, held in settings.guard.claims.items()
    }
    for code, phrases in NUMBER_CLAIMS.items():
        claims[code] = list(dict.fromkeys((*claims.get(code, ()), *phrases)))
    guard = GuardSettings.model_validate(settings.guard.model_dump() | {"claims": claims})
    return settings.model_copy(update={"guard": guard})
