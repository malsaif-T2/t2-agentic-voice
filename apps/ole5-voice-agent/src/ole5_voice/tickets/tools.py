"""Everything the talker is given over a ticket system, in one place (plan 007): the three
actions (actions.py) and the status tool (status.py), all over the same system, so a status reads
what the actions made."""

from __future__ import annotations

from t2_agentic_voice import DeclaredTool

from ole5_voice.tickets.actions import add_ticket_note, create_ticket, hand_off
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
