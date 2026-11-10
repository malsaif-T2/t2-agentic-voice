"""Who the caller is to Ole5's ticket system (plan 007's Q3): the customer's email, carried by
the call's signed join token as its caller's `customer_email` attribute.

The token route (token_route.py) mints every token for the one demo customer the settings name
(`OLE5_VOICE_DEMO_CUSTOMER_EMAIL`, settings.py), a default the owner may change; the runtime
verifies the token once, at join, and the call's `Caller` holds the email from then on, read
only. Nothing said or sent in the call can change it, so a ticket is created for, and read as,
that customer alone, never one a caller names (docs/SECURITY.md, invariant 3). A tool reads it
by `from_caller(CUSTOMER_FIELD)`, hidden from the talker; an action by `customer_email`. The
real mapping from the website's sign-in to a customer comes with the deployment.
"""

from __future__ import annotations

from typing import Final

from t2_agentic_voice import Caller

# The caller's attribute that holds the customer's email, and the field a tool binds it by.
CUSTOMER_EMAIL: Final = "customer_email"
CUSTOMER_FIELD: Final = f"attributes.{CUSTOMER_EMAIL}"


def customer_email(caller: Caller) -> str | None:
    """The email of the customer `caller` is, from the token that started the call; None when
    the token named none (a dev caller)."""
    return caller.attributes.get(CUSTOMER_EMAIL)
