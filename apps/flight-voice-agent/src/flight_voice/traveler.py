"""Who the caller is to the mock airline: the demo traveler, carried by the call's signed join
token as its caller's `traveler_id` attribute.

The token route (the library's `access_code_router`, server.py) mints every token for the demo
traveler, as `demo_caller` builds that caller; under `env` dev the settings also name it the test
console's dev caller, so a call the console starts is the traveler's too. The runtime verifies
the token once, at join, and the call's `Caller` holds the traveler from then on, read only.
Nothing said or sent in the call can change it, so a trip is booked for, and a profile read as,
that traveler alone (docs/SECURITY.md, invariant 3). A tool reads it by
`from_caller(TRAVELER_FIELD)`, hidden from the talker; the booking by `traveler_of`.
"""

from __future__ import annotations

from typing import Final

from t2_agentic_voice import Caller

from flight_voice.airline.profile import TRAVELER

# The caller every token names: the owner, the only one who holds the access code.
SUBJECT: Final = "owner"
# The caller's attribute that holds the traveler's ID, and the field a tool binds it by.
TRAVELER_ID: Final = "traveler_id"
TRAVELER_FIELD: Final = f"attributes.{TRAVELER_ID}"


def demo_caller() -> Caller:
    """The caller of every token: the owner (`SUBJECT`) as the demo traveler."""
    return Caller(subject=SUBJECT, attributes={TRAVELER_ID: TRAVELER.id})
