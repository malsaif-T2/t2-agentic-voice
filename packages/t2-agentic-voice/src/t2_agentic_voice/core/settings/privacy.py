"""The `privacy` group: what is kept of a call, and which consent a caller gave."""

from __future__ import annotations

from pydantic import Field

from t2_agentic_voice.core.settings.base import Group


class PrivacySettings(Group):
    """Privacy: whether a call's audio may be recorded, and the consent version callers agree
    to (docs/SECURITY.md, invariant 8)."""

    record_audio: bool = Field(
        default=False,
        description=(
            "Whether a call's audio may be recorded under the storage folder: only when this is "
            "on and the caller's signed join token says they consented."
        ),
    )
    # A bounded string: it travels in every join token and is stamped on each call's report.
    consent_version: str | None = Field(
        default=None,
        pattern=r"^[\x21-\x7e]{1,64}$",
        description=(
            "The version of the consent text callers agree to (1 to 64 printable characters, no "
            "space); when set, a join token holding another version is refused. Unset: any."
        ),
    )
