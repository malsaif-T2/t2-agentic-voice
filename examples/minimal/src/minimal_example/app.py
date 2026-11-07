"""The example's two agents, each in English and Saudi Arabic, whichever the caller picks:

- **The helper** (`helper`, served by `make_runtime`): the talker, which answers a caller's
  question about a branch's opening hours with the chat model and one read tool,
  `opening_hours`, a lookup in a table of its own: no knowledge base, no network.
- **The echo** (`agent`, served by `make_echo_runtime`): each turn the caller says is said back,
  after a short frame in the turn's language ("I heard: ..."), with no model: the first check of
  a call's audio, which the library's own call tests run too.

Each factory is one `serve` and `t2v` take. Their callers are `DevIdentity`'s, so they serve
`env` dev on this machine only; a team serving real callers passes
`SignedJoinTokens.from_settings(settings.join)` instead (the guide's serving.md).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from t2_agentic_voice import Language, VoiceAgent, VoiceRuntime, VoiceSettings, tool
from t2_agentic_voice.identity import DevIdentity

# Today's opening hours of each branch, by its name in lowercase English letters.
HOURS = {"olaya": "8 am to 4 pm", "malaz": "9 am to 5 pm"}


@tool(description="Today's opening hours of one branch, by the branch's name.")
async def opening_hours(
    branch: Annotated[
        str,
        Field(min_length=1, max_length=40, description="The branch's name, such as Olaya."),
    ],
) -> str:
    """The branch's hours today; the branches there are, when it names none of them."""
    hours = HOURS.get(branch.strip().casefold())
    if hours is None:
        return f"No branch has that name. The branches are {', '.join(map(str.title, HOURS))}."
    return hours


# What the helper does, for the talker: the library adds its rules for the ear and the reply's
# language around it.
INSTRUCTIONS = (
    "You tell callers today's opening hours of the branches. When the caller names a branch, "
    "look its hours up with opening_hours, its name in English letters, and say them in one "
    "short sentence. When no branch has that name, say which branches there are. For anything "
    "else, say plainly that you can only tell the branches' hours."
)

# "hala! ay far' tabi ta'rif dawamah al-yawm?": hi! Which branch's hours today do you want?
HELPER_GREETING = (
    "\u0647\u0644\u0627! \u0623\u064a \u0641\u0631\u0639 \u062a\u0628\u064a "
    "\u062a\u0639\u0631\u0641 \u062f\u0648\u0627\u0645\u0647 \u0627\u0644\u064a\u0648\u0645\u061f"
)

helper = VoiceAgent(
    name="minimal-helper",
    languages=[
        Language.english(greeting="Hi! Which branch's opening hours would you like to know?"),
        Language.saudi_arabic(greeting=HELPER_GREETING),
    ],
    instructions=INSTRUCTIONS,
    tools=[opening_hours],
)


def make_runtime(settings: VoiceSettings | None = None) -> VoiceRuntime:
    """The helper's runtime, with `settings`, or those the `T2V_*` variables give (nothing is
    read at import)."""
    return VoiceRuntime(
        helper, settings=settings or VoiceSettings.from_env(), identity=DevIdentity()
    )


# The Saudi greeting, "hala, takallam wa a'eed lak kalaamak": hi, speak and I will say your
# words back to you.
SAUDI_GREETING = (
    "\u0647\u0644\u0627\u060c \u062a\u0643\u0644\u0645 \u0648\u0623\u0639\u064a\u062f "
    "\u0644\u0643 \u0643\u0644\u0627\u0645\u0643."
)

agent = VoiceAgent(
    name="minimal-echo",
    languages=[
        Language.english(greeting="Hi! Say something, and I will say it back."),
        Language.saudi_arabic(greeting=SAUDI_GREETING),
    ],
)


def make_echo_runtime(settings: VoiceSettings | None = None) -> VoiceRuntime:
    """The echo's runtime, as `make_runtime` makes the helper's."""
    return VoiceRuntime(
        agent, settings=settings or VoiceSettings.from_env(), identity=DevIdentity()
    )
