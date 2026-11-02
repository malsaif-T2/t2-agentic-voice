"""The `storage` group: where the library keeps its data."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from t2_agentic_voice.core.settings.base import Group


class StorageSettings(Group):
    """Storage: one folder for everything the library keeps."""

    var_dir: Path = Field(
        default=Path("var"),
        description=(
            "Local runtime data (git-ignored): databases, run outputs, caches. Every path under "
            "it comes from here, so one setting moves a whole run, a test session included."
        ),
    )
