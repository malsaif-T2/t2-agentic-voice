"""The read-back's receipt (docs/SECURITY.md, invariant 1; core/yes_inputs.py): the only place a
`ReadBackReceipt` is built, from the transport's `ClausePlayed` reports, never the browser's
`playback` message. It stands for a summary that played whole: every clause played, none cut or
cut short, each with audio, the reply not stopped, and no overlap of it undecided.

Plan 007's Track C adds to this module what plays a read-back and routes what is heard after it.
"""

from __future__ import annotations

from t2_agentic_voice.core.events import ReplyId
from t2_agentic_voice.core.yes_inputs import READ_BACK_SEAL, ReadBackReceipt


def played_receipt(
    *,
    action: str,
    draft_json: str,
    reply_id: ReplyId,
    summary_played_at: float,
    question_ended_at: float | None,
) -> ReadBackReceipt:
    """The receipt of `action`'s read-back of `draft_json` in reply `reply_id`. The caller has
    checked everything the module's docstring says; this only builds it."""
    values = {
        "action": action,
        "draft_json": draft_json,
        "reply_id": reply_id,
        "summary_played_at": summary_played_at,
        "question_ended_at": question_ended_at,
    }
    return ReadBackReceipt.model_validate(values, context=READ_BACK_SEAL)
