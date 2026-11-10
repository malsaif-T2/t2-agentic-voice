"""The example's one action (plan 007): `request_callback`, a branch calling the caller back, on
the helper's languages and its read tool (app.py), in English and Saudi Arabic.

The talker collects the branch and what the call is about, and calls the action with them; the
library reads the draft back aloud, the branch said by its label, and books it only after the
caller's clear yes, heard once the summary has played whole. It then speaks a fixed line while
the write runs, and the outcome from the desk's real answer: the talker never says it is done.
The desk is made up, held in memory (`CallbackDesk`), and the action reaches it by a closure
(`callback_action`), as every backend is reached; `make_callback_helper` makes the agent at a
desk of its own, so a test gets a fresh one each time.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field
from t2_agentic_voice import (
    Action,
    ActionContext,
    Claims,
    ReadBack,
    Say,
    Spoken,
    VoiceAgent,
    action,
)

from minimal_example.app import helper, opening_hours

# The branches' names in Arabic, as a read-back says them: "al-olaya" (alef, lam, ain, lam, yeh,
# alef) and "al-malaz" (alef, lam, meem, lam, zain).
OLAYA = "العليا"
MALAZ = "الملز"


class CallbackRequest(BaseModel):
    """What the talker gives to ask a branch to call the caller back: the branch, a fixed value
    the read-back says by its label, and the reason, in a few of the caller's own words."""

    branch: Annotated[
        Literal["olaya", "malaz"],
        Spoken({"olaya": {"en": "Olaya", "ar": OLAYA}, "malaz": {"en": "Malaz", "ar": MALAZ}}),
        Field(description="The branch that calls back."),
    ]
    reason: Annotated[
        str,
        Field(min_length=1, max_length=120, description="What the call is about, briefly."),
    ]


class CallbackBooked(BaseModel):
    """What the desk gives back: the callback's number, four digits."""

    number: Annotated[str, Field(pattern=r"^[0-9]{4}$")]


class CallbackDesk:
    """The example's made-up callback desk: each callback it booked, by the request ID the
    library gives each write, so the same request reaching it twice is booked once."""

    def __init__(self) -> None:
        self.booked: dict[str, tuple[CallbackRequest, CallbackBooked]] = {}

    def book(self, request_id: str, request: CallbackRequest) -> CallbackBooked:
        """Book `request` under `request_id`, once."""
        if request_id not in self.booked:
            number = CallbackBooked(number=str(4101 + len(self.booked)))
            self.booked[request_id] = (request, number)
        return self.booked[request_id][1]

    def find(self, request_id: str) -> CallbackBooked | None:
        """The callback booked under `request_id`, None when there is none."""
        found = self.booked.get(request_id)
        return None if found is None else found[1]


# The Saudi read-back, "baTlub min far' {branch} yittaSil 'alek bikhuSuuS: {reason}. arsil
# aT-Talab?": I'll ask the {branch} branch to call you about: {reason}. Shall I send the request?
SAUDI_SUMMARY = "بطلب من فرع {branch} يتصل عليك بخصوص: {reason}."
SAUDI_QUESTION = "أرسل الطلب؟"
# "tamm, raqm Talabak {number}": done, your request's number is {number}, said digit by digit.
SAUDI_DONE = "تم، رقم طلبك {number:id}."
# The Saudi claims, "Talabt minhum yittaSluun" and "sajjalt Talab al-ittiSaal": I asked them to
# call, I booked the callback.
SAUDI_CLAIMS = [
    "طلبت منهم يتصلون",
    "سجلت طلب الاتصال",
]


def callback_action(desk: CallbackDesk) -> Action:
    """The action, booking at `desk`, which it reaches by a closure: read back aloud, booked
    only after the caller's yes, and looked up by its request ID when the desk's reply was
    lost."""

    @action(
        description=(
            "Ask a branch to call the caller back. Collect the branch and what the call is "
            "about first."
        ),
        read_back=ReadBack(
            {
                "en": (
                    "I'll ask the {branch} branch to call you back about: {reason}.",
                    "Shall I send it?",
                ),
                "ar": (SAUDI_SUMMARY, SAUDI_QUESTION),
            }
        ),
        done=Say(en="Done, your callback number is {number:id}.", ar=SAUDI_DONE),
        claims=Claims(
            {
                "en": ["callback is booked", "booked your callback", "asked the branch to call"],
                "ar": SAUDI_CLAIMS,
            }
        ),
    )
    async def request_callback(ctx: ActionContext, draft: CallbackRequest) -> CallbackBooked:
        return desk.book(ctx.request_id, draft)

    @request_callback.lookup
    async def find_callback(ctx: ActionContext, request_id: str) -> CallbackBooked | None:
        return desk.find(request_id)

    return request_callback


# What the helper with callbacks does, for the talker.
CALLBACK_INSTRUCTIONS = (
    "You tell callers today's opening hours of the branches, and have a branch call a caller "
    "back. When the caller names a branch, look its hours up with opening_hours and say them in "
    "one short sentence. When the caller wants a branch to call them back, ask what it is about "
    "if they have not said, then call request_callback with the branch and a few words on why. "
    "For anything else, say plainly that you can only tell the hours or have a branch call."
)


def make_callback_helper(desk: CallbackDesk) -> VoiceAgent:
    """The helper with its callbacks booked at `desk`: the quickstart's helper, its languages
    and its read tool, and the action."""
    return VoiceAgent(
        name="minimal-callback",
        languages=helper.languages,
        instructions=CALLBACK_INSTRUCTIONS,
        tools=[opening_hours, callback_action(desk)],
    )
