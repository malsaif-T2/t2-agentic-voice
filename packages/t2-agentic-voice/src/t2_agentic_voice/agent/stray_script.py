"""One reply's stray-script filter (domain/text/scripts.py's rule, for the scripts of every
language the agent speaks and the terms it declares): the reply (agent/turn.py) filters each
piece the model writes (`text`) and each tool call it asks for (`call`) before anything reads
them, so one filtered text feeds the output guard, the voice, the captions, the next request,
the trace, the public events and an action's draft; and it counts what went, for each model
request's `ModelReplied` (`take`).

The terms an agent declares keep their characters: the written forms of its pronunciation map,
its vocabulary's terms and the `words.vocabulary` setting's. A call's arguments are parsed as
JSON and each string value filtered, never a key (a key names a field, which the runner checks
as the model wrote it); they are written back only when a value changed, so a call with nothing
to change keeps its exact text, and arguments that are not JSON are kept as written, for the
runner to refuse as it does. With `guard.remove_stray_script` off, each gives back what it was
given and counts nothing. It never raises.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from pydantic import JsonValue

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest
from t2_agentic_voice.domain.text.scripts import MAX_LABELS, Kept, ScriptRule


def _filtered(value: JsonValue, rule: ScriptRule, found: list[Kept]) -> JsonValue:
    """`value` with each string in it filtered by `rule`, every key kept; each change kept in
    `found`."""
    if isinstance(value, str):
        kept = rule(value)
        if kept.changed:
            found.append(kept)
        return kept.text
    if isinstance(value, list):
        return [_filtered(each, rule, found) for each in value]
    if isinstance(value, dict):
        return {key: _filtered(each, rule, found) for key, each in value.items()}
    return value


class StrayScript:
    """The filter of one reply of an agent of `languages` that declares the terms `kept`, on
    unless `on` is False (the module's docstring)."""

    def __init__(
        self, *, languages: Iterable[LanguageTag], kept: Iterable[str] = (), on: bool = True
    ) -> None:
        self._rule = ScriptRule(languages, kept) if on else None
        self._count = 0
        self._labels: set[str] = set()
        self._changed = False

    @classmethod
    def of(cls, agent: VoiceAgent, settings: VoiceSettings) -> StrayScript:
        """The filter of a reply of `agent` under `settings`."""
        terms = (*agent.pronounce, *agent.vocabulary.terms, *settings.words.vocabulary)
        return cls(
            languages=[language.tag for language in agent.languages],
            kept=terms,
            on=settings.guard.remove_stray_script,
        )

    @property
    def changed(self) -> bool:
        """Whether it has taken out or rewritten a character of the reply's text (its calls'
        arguments not counted), so a clause may be left with nothing to say."""
        return self._changed

    def text(self, piece: str) -> str:
        """`piece` of what the model writes, filtered."""
        if self._rule is None:
            return piece
        kept = self._rule(piece)
        self._counted([kept])
        self._changed = self._changed or kept.changed > 0
        return kept.text

    def call(self, request: ToolCallRequest) -> ToolCallRequest:
        """`request` with each string value of its arguments filtered, its keys as written; the
        request itself when none changed or its arguments are not JSON."""
        if self._rule is None:
            return request
        found: list[Kept] = []
        try:
            value = _filtered(json.loads(request.arguments), self._rule, found)
            arguments = json.dumps(value, ensure_ascii=False) if found else request.arguments
        except (ValueError, RecursionError):  # not JSON, or nested past what Python reads
            return request
        if not found:
            return request
        self._counted(found)
        return request.model_copy(update={"arguments": arguments})

    def take(self) -> tuple[int, tuple[str, ...]]:
        """How many characters it took out or rewrote since the last take, and their labels
        (at most `MAX_LABELS`, sorted); (0, ()) when none."""
        count, labels = self._count, tuple(sorted(self._labels)[:MAX_LABELS])
        self._count, self._labels = 0, set()
        return count, labels

    def _counted(self, kept: Iterable[Kept]) -> None:
        for each in kept:
            if each.changed:
                self._count += each.changed
                self._labels.update(each.labels)
