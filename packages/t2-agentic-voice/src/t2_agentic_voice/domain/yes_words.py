"""The words the yes rule reads (the design's 8.3): each language's yes words, send words, no
words and fillers, by the primary code the interruption rule's lists use.

They are kept out of domain/words.py's five kinds so that those lists, and the interruption rule
measured on them, stay exactly as they are. The action's own `send_words` and the `words` group's
`yes` and `send` are added to the preset's. Plan 007's Track A fills the presets and
`consent_words`.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from t2_agentic_voice.core.settings.words import LanguageCode


class ConsentWords(BaseModel):
    """One language's lists for one read-back, each in the rule's form (domain/words.py's
    `rule_form`): `yes`, `send` (the preset's, the settings' and the action's), `no`, and the
    `fillers` a yes may stand among."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    yes: tuple[str, ...]
    send: tuple[str, ...]
    no: tuple[str, ...]
    fillers: tuple[str, ...]


def consent_words(
    code: LanguageCode,
    *,
    added_yes: Sequence[str] = (),
    added_send: Sequence[str] = (),
    action_send: Sequence[str] = (),
) -> ConsentWords:
    """The lists the yes rule reads in the language `code`: the preset's, with the settings'
    additions and the action's own send words."""
    raise NotImplementedError(f"plan 007's Track A fills consent_words ({code})")
