"""An agent's tools and actions as the library runs them, and its one action runner: what the
runtime (api/providers.py, api/actions.py) and the test calls (testing/text_call.py,
testing/audio_call.py) build alike, so a call in a test runs on the parts a served call does.

- `tools_of`: the agent's tools, each a `Tool` the tool runner runs, its actions left to their
  own runner; a ConfigurationError, with a FIX line, for a tool the library cannot run.
- `actions_of`: the agent's actions, in the order it declares them.
- `action_runner`: the one `ActionRunner` of the agent's actions, against `outbox`, its cap per
  caller per day `limits.actions_per_caller_per_day`; given one call's `record` (a text call's),
  every job adds to that one.
"""

from __future__ import annotations

from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.record import ActionRecord
from t2_agentic_voice.actions.tools import Tool
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.outbox import Outbox


def tools_of(agent: VoiceAgent) -> tuple[Tool, ...]:
    """The agent's tools, each the library's `Tool` the runner runs, its actions left to their
    own runner; ConfigurationError for any other."""
    tools = tuple(tool for tool in agent.tools if isinstance(tool, Tool))
    if len(tools) + sum(isinstance(tool, Action) for tool in agent.tools) != len(agent.tools):
        raise ConfigurationError(
            "A tool the agent declares is not one the library runs. FIX: build each with @tool, "
            "Tool.from_function, knowledge_tool or @action."
        )
    return tools


def actions_of(agent: VoiceAgent) -> tuple[Action, ...]:
    """The agent's actions, in the order it declares them, each carried out by its action
    runner, never by the tool runner."""
    return tuple(tool for tool in agent.tools if isinstance(tool, Action))


def action_runner(
    agent: VoiceAgent,
    settings: VoiceSettings,
    *,
    outbox: Outbox,
    record: ActionRecord | None = None,
) -> ActionRunner:
    """The runner of the agent's actions (the module's docstring), one for every call."""
    return ActionRunner(
        actions_of(agent),
        outbox=outbox,
        record=record,
        per_caller_per_day=settings.limits.actions_per_caller_per_day,
    )
