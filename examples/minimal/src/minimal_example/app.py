"""The echo agent: each turn the caller says is said back, after a short frame in the turn's
language ("I heard: ..."), in English or in Saudi Arabic, whichever the caller picks.

`make_runtime` is the factory `serve` and `t2v` take. Its callers are `DevIdentity`'s, so it
serves `env` dev on this machine only; a team serving real callers passes
`SignedJoinTokens.from_settings(settings.join)` instead (the guide's serving.md).
"""

from __future__ import annotations

from t2_agentic_voice import Language, VoiceAgent, VoiceRuntime, VoiceSettings
from t2_agentic_voice.identity import DevIdentity

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


def make_runtime(settings: VoiceSettings | None = None) -> VoiceRuntime:
    """The echo agent's runtime, with `settings`, or those the `T2V_*` variables give (nothing
    is read at import)."""
    return VoiceRuntime(
        agent, settings=settings or VoiceSettings.from_env(), identity=DevIdentity()
    )
