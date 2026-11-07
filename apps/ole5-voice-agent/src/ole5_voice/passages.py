"""Ole5's points as the library's passages (plan 006, Q4): what the knowledge base adapter
(knowledge_base.py) makes of each point a search of T2's Qdrant returns, as the spike read the
payload on 2026-11-06 (`page_content`, and under `metadata` the document's name, the chunk's ID,
its section and its source text).

- **The ID** is `<document name>/<chunk ID>`: a chunk's ID repeats across documents, and a
  runner maps a passage to the knowledge set's `points.toml` through its document names.
- **The text** is the chunk's source text, or the point's `page_content` when it has none (that
  one opens with a summary the indexer wrote).
- **The title** is the chunk's section, or else the text's first heading: its first Markdown
  heading, or its first line when that is short and not a step; else the document's name.
- **The steps** are the text's numbered or bulleted lines, in order, each without its number or
  bullet and without Markdown's bold marks.
- **The score** is Qdrant's (cosine: higher is nearer), and **the source** the document's name.

A point that cannot be read (no document name or chunk ID, no text, a score that is not a
number) is left out, and only their count is logged: never a payload's text.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from t2_agentic_voice import get_logger
from t2_agentic_voice.ports import Passage

log = get_logger(__name__)

# A line that is a step: a number (Western, Arabic-Indic or Eastern Arabic-Indic digits) with a
# dot, a bracket, a hyphen or an Arabic comma after it, or a bullet (a hyphen, an asterisk, the
# bullet U+2022), then the step's words.
STEP: Final = re.compile(
    r"^\s*(?:[0-9\u0660-\u0669\u06f0-\u06f9]{1,3}[.)\-\u060c]|[-*\u2022])\s+(?P<step>\S.*?)\s*$"
)
HEADING: Final = re.compile(r"^\s*#{1,6}\s+(?P<heading>\S.*?)[\s#]*$")
# The longest first line taken as a title when the text has no heading.
TITLE_CHARS: Final = 120


class _Payload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", hide_input_in_errors=True)


class Metadata(_Payload):
    """What a point's `metadata` holds that a passage is made of."""

    document_name: str = Field(min_length=1)
    chunk_id: str | int
    section: str | None = None
    source_text: str | None = None


class Payload(_Payload):
    """A point's payload: its `page_content` and its `metadata`."""

    page_content: str | None = None
    metadata: Metadata


class ScoredPoint(_Payload):
    """One point a search found: its score and its payload."""

    score: float = Field(allow_inf_nan=False)
    payload: Payload


def passages(points: Sequence[object]) -> list[Passage]:
    """The passages `points` hold, in their order (best first, as Qdrant gives them), each point
    that cannot be read left out and counted in a warning."""
    found: list[Passage] = []
    for point in points:
        made = passage(point)
        if made is not None:
            found.append(made)
    if len(found) < len(points):
        log.warning("knowledge_points_skipped", skipped=len(points) - len(found))
    return found


def passage(point: object) -> Passage | None:
    """The passage one point holds (the module's docstring); None when it cannot be read."""
    try:
        scored = ScoredPoint.model_validate(point)
    except ValidationError:
        return None
    meta = scored.payload.metadata
    text = _said(meta.source_text) or _said(scored.payload.page_content)
    if text is None:
        return None
    try:
        return Passage(
            id=passage_id(meta.document_name, meta.chunk_id),
            title=_said(meta.section) or title_of(text) or meta.document_name,
            text=text,
            steps=steps_of(text),
            score=scored.score,
            source=meta.document_name,
        )
    except ValidationError:
        return None


def passage_id(document_name: str, chunk_id: str | int) -> str:
    """A point's passage ID (the module's docstring): its document's name, a slash, and its
    chunk's ID, as the payload holds them. Runs K and S read the snapshot of the points with this
    same function (evals/kb_points.py), so a live passage and its point's text share one ID."""
    return f"{document_name}/{chunk_id}"


def title_of(text: str) -> str | None:
    """The text's first heading: its first Markdown heading, or else its first line when that
    is short and not a step; None when it has neither."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        heading = HEADING.match(line)
        if heading:
            return _plain(heading["heading"])
    first = lines[0] if lines else ""
    if first and len(first) <= TITLE_CHARS and not STEP.match(first):
        return _plain(first)
    return None


def steps_of(text: str) -> tuple[str, ...]:
    """The text's numbered or bulleted lines, in order, each without its number or bullet and
    its bold marks."""
    steps = (STEP.match(line) for line in text.splitlines())
    return tuple(step for match in steps if match and (step := _plain(match["step"])))


def _plain(text: str) -> str:
    """`text` without Markdown's bold marks, with no space at either end."""
    return text.replace("**", "").strip()


def _said(text: str | None) -> str | None:
    """`text` with no space at either end, None when it says nothing."""
    return (text.strip() or None) if text is not None else None
