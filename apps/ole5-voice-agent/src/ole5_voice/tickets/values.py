"""The values an Ole5 ticket is made of, in one module: its queues, its 11 types, its priorities
and its statuses, each a fixed set (docs/SECURITY.md, invariant 4).

Their exact names are the prototype's stand-in sheet's (`Ole5-chatbot/sheets/values.xlsx`, the
rows of product OLE5 and the shared ones, read on 2026-11-10), the only list of them anyone has
(plan 007, "What is known about the ticket system"). The sheet's 17 subtypes and its reasons
are left to support staff (plan 007's Q5), so they are not here.

What no sheet says is the agent's choice, for T2 to confirm when the real system comes: the
queue each type goes to (`QUEUE_OF`, plan 007's Q5, "the queue follows the type"), and that a
new ticket's status is New (the prototype sent "new" where the sheet says "New").
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Literal, get_args

Queue = Literal["Ole5 Support", "Ole5 Technical"]
TicketType = Literal[
    "Bug",
    "Infrastructure",
    "Inquiry",
    "Issue",
    "Mobile App Issue",
    "Report",
    "Request for Integration",
    "Request for Migration",
    "Request for New Feature with Change Request",
    "Request",
    "Reset Password",
]
Priority = Literal["Low", "Medium", "High", "Critical"]
Status = Literal[
    "New",
    "Open",
    "Waiting For Customer Response",
    "Waiting for Concerned Department",
    "Waiting for Service Provider",
    "Pending Reminder",
    "pending auto close+",
    "closed successful",
    "merged",
]

QUEUES: Final[tuple[Queue, ...]] = get_args(Queue)
TYPES: Final[tuple[TicketType, ...]] = get_args(TicketType)
PRIORITIES: Final[tuple[Priority, ...]] = get_args(Priority)
STATUSES: Final[tuple[Status, ...]] = get_args(Status)
# The priority the talker gives a ticket when the caller says nothing of how urgent it is (plan
# 007's Q5, amended by the owner on 2026-11-11), and the status a new ticket starts in.
DEFAULT_PRIORITY: Final[Priority] = "Medium"
NEW_STATUS: Final[Status] = "New"
# The statuses the sheet marks closed; every other one is open.
CLOSED: Final[frozenset[Status]] = frozenset({"closed successful", "merged"})
# The queue each type goes to: what breaks or needs building goes to the technical team, what
# a support person answers to support (the agent's choice; the module's docstring).
QUEUE_OF: Final[Mapping[TicketType, Queue]] = {
    "Bug": "Ole5 Technical",
    "Infrastructure": "Ole5 Technical",
    "Inquiry": "Ole5 Support",
    "Issue": "Ole5 Support",
    "Mobile App Issue": "Ole5 Technical",
    "Report": "Ole5 Support",
    "Request for Integration": "Ole5 Technical",
    "Request for Migration": "Ole5 Technical",
    "Request for New Feature with Change Request": "Ole5 Technical",
    "Request": "Ole5 Support",
    "Reset Password": "Ole5 Support",
}
