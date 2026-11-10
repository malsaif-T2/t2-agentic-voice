"""One entry of a call's record of completed actions (docs/SECURITY.md, invariant 2): what the
output guard's claim rule accepts as proof that an action was done. Sealed (core/seal.py) and
`[[restricted]]`: it sits in `domain`, where the guard reads it, and only actions/record.py
builds one, the seal given to no other module.

`result_json` is the real result as JSON text, which the `done` line is filled from, and
`evidence` the texts of it that may hold an ID-shaped token the guard may let be said.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final, final

from pydantic import Field

from t2_agentic_voice.core.seal import SealedModel, still_sealed

# The seal a validation of a `CompletedAction` must be given.
RECORD_SEAL: Final[object] = object()


@final
class CompletedAction(SealedModel):
    """An action that was done: its name; its `request_id`, written to the outbox before the
    write; its real result (`result_json`) and `evidence`; and `at`, on the call's clock."""

    refusal: ClassVar[str] = (
        "Only actions/record.py builds a CompletedAction, once a write has really returned; "
        "elsewhere, read the call's record."
    )

    action: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    result_json: str = Field(repr=False)
    evidence: tuple[str, ...] = Field(default=(), repr=False)
    at: float

    def model_post_init(self, context: Any, /) -> None:
        self._seal_with(context, RECORD_SEAL)


def is_recorded(value: object) -> bool:
    """Whether `value` is a record entry only `actions` built, unchanged since."""
    return type(value) is CompletedAction and still_sealed(value)
