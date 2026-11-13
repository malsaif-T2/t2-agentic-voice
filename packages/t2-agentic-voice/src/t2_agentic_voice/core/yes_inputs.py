"""The two inputs of the yes rule (docs/SECURITY.md, invariant 1): the words heard in one of the
caller's turns and the receipt of a read-back played whole. Only `voice` builds them, and
`domain`'s rule reads them, so they sit in core, below both. Each is sealed (core/seal.py) and
`[[restricted]]`, so no tool argument or model output can stand in for either.

`HeardWords.at` is when the transcript arrived and `speech_at` when the caller began speaking:
Whisper gives no partials, so a yes said over a summary arrives after the summary ended, and
only `speech_at` tells them apart. It is None when no turn opened for the words, which a rule
reads as said before anything. `source` is `speech_to_text`, or `typed`, a test's words, which
the yes rule takes only when `env` is `test`.

A `ReadBackReceipt` says one read-back's summary played whole: it holds the action, the draft
that was read back, as JSON text, and the reply, so a receipt for one draft cannot confirm
another after a correction. `summary_played_at` is when the transport reported the summary's
last clause played and `question_ended_at` the same for the closing question, None while it
plays. Both are the transport's own reports, never the browser's and with no tail after the
audio. The session builds the receipt when the yes rule is called, so a verdict or a turn that
lands after the last clause can still deny it one.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Final, Literal, final

from pydantic import Field

from t2_agentic_voice.core.events import ReplyId, TurnId
from t2_agentic_voice.core.seal import SealedModel, still_sealed

# Where heard words came from: a speech-to-text result, or text a test typed.
HeardSource = Literal["speech_to_text", "typed"]
# An action's name, and the draft read back as JSON text (kept out of a repr), as every model a
# draft passes through holds them: the read-back's plan, its receipt, the confirmed action, the
# outbox's entry and the record's completed action.
ActionName = Annotated[str, Field(min_length=1)]
DraftJson = Annotated[str, Field(min_length=2, repr=False)]
# The seals a validation of each class must be given, compared by identity; only the modules
# their `[[restricted]]` rows list name them.
HEARD_WORDS_SEAL: Final[object] = object()
READ_BACK_SEAL: Final[object] = object()


@final
class HeardWords(SealedModel):
    """The words speech-to-text heard in the caller's turn `turn_id`: `text`, with no space at
    either end; the `language` the provider heard or was told, in its code; `at`, when the
    transcript came, and `speech_at`, when the caller began speaking, on the call's clock; and
    its `source`. Built only by voice/session/heard.py's `heard_words`."""

    refusal: ClassVar[str] = (
        "Only voice builds HeardWords, from a turn's speech-to-text result; elsewhere, take the "
        "HeardWords voice hands on."
    )

    turn_id: TurnId
    text: str = Field(repr=False)
    language: str | None
    at: float
    speech_at: float | None
    source: HeardSource = "speech_to_text"

    def model_post_init(self, context: Any, /) -> None:
        self._seal_with(context, HEARD_WORDS_SEAL)


@final
class ReadBackReceipt(SealedModel):
    """One read-back's summary played whole (the module's docstring). Built only by
    voice/session/read_back.py."""

    refusal: ClassVar[str] = (
        "Only voice/session/read_back.py builds a ReadBackReceipt, from the transport's reports "
        "that a read-back's summary played whole."
    )

    action: ActionName
    draft_json: DraftJson
    reply_id: ReplyId
    summary_played_at: float
    question_ended_at: float | None = None

    def model_post_init(self, context: Any, /) -> None:
        self._seal_with(context, READ_BACK_SEAL)


def is_heard_words(value: object) -> bool:
    """Whether `value` is heard words only `voice` built, unchanged since."""
    return type(value) is HeardWords and still_sealed(value)


def is_read_back_receipt(value: object) -> bool:
    """Whether `value` is a receipt only `voice` built, unchanged since."""
    return type(value) is ReadBackReceipt and still_sealed(value)
