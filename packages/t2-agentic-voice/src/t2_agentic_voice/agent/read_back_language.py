"""An action's read-back said in another language (D-038's amendment; docs/SECURITY.md,
invariant 1): `read_back_in` renders a read-back again in the language the call moved to, from
the same draft, for the session to read it again (voice/session/read_back_moved.py).

The draft is the one already read back, parsed again by its action's parameters, and the new
read-back holds its `draft_json` unchanged, so a yes to it confirms exactly what was drafted;
nothing of the model is asked. It lives with the talker because the session may not import the
actions themselves (the layers: voice reaches actions only through the agent).
"""

from __future__ import annotations

from pydantic import ValidationError

from t2_agentic_voice.actions.agent_tools import actions_of
from t2_agentic_voice.actions.spoken_lines import read_back_plan
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.declaration import VoiceAgent


def read_back_in(agent: VoiceAgent, plan: ReadBackPlan, tag: LanguageTag) -> ReadBackPlan | None:
    """`plan` rendered again in `tag`, its draft and its call's id unchanged; None when the
    agent declares no such action, its draft no longer parses, or a line would say nothing in
    `tag`."""
    found = [action for action in actions_of(agent) if action.name == plan.action]
    if not found:
        return None
    action = found[0]
    try:
        draft = action.parameters.model_validate_json(plan.draft_json)
        again = read_back_plan(action, draft, tool_call_id=plan.tool_call_id, tag=tag)
    except (ValidationError, KeyError, ValueError):
        return None
    return again.model_copy(update={"draft_json": plan.draft_json})
