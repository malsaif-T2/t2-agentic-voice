"""How runs K and S read Ole5's knowledge base: a passage's ID as the knowledge set names it, the
expected points' text the judge reads, and the searches a call made.

- **The points.** The knowledge base adapter names a passage `"<document name>/<chunk_id>"`
  (passages.py's `passage_id`); `PointIndex` maps it to `points.toml`'s ID (`features-002`)
  through the document's name, read with its spaces collapsed and in Unicode's NFC form, and the
  chunk's ID, `chunk_002` or the bare number a payload may hold. A passage `points.toml` does not
  hold maps to None, which retrieval counts as a miss, never as an error; the ID's form never
  makes one.
- **Their text.** The judge reads each expected point's text from a snapshot of Ole5's points
  (`--points-text`: one JSON object a line, each with a point's `payload` as Qdrant gives it),
  read only when a run is made, from the path its command line names: the text is the payload's
  `metadata.source_text`, or its `page_content` when that is missing, each point named by the
  passage ID the adapter gives the same payload, so the judge reads the text of the point found.
- **The searches.** `RecordingKnowledge` stands between the talker's tool and the knowledge base:
  it asks for at least `TOP` passages, keeps each search's query and passage IDs, and hands the
  tool as many as it asked for, so retrieval is read from the talker's own query.

`load_knowledge` reads the knowledge set as a run does (`KnowledgeData`), with the digest of every
file the run depends on, so two runs on other data are never compared.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict
from t2_agentic_voice import Caller
from t2_agentic_voice.evals import run_refused
from t2_agentic_voice.ports import KnowledgeBase, Passage

from ole5_voice.evals.files import parse_json, read_text
from ole5_voice.evals.items import GoldenSetError, read_toml
from ole5_voice.evals.judge import Evidence
from ole5_voice.evals.knowledge_set import (
    KNOWLEDGE_DIR,
    POINTS_FILE,
    KnowledgeItem,
    Points,
    load_knowledge_items,
)
from ole5_voice.evals.talker_data import Tag, TalkerDataError
from ole5_voice.passages import passage_id

TOP: Final = 5  # retrieval counts an expected point among the first five passages
# A chunk's ID: as the export wrote it (`chunk_002`), or as a bare number.
_CHUNK = re.compile(r"chunk_(?P<named>[0-9]{3})|(?P<bare>[0-9]{1,3})")


def _name(text: str) -> str:
    """A document's name as the index compares it: in NFC, each run of spaces one, none at the
    ends."""
    return " ".join(unicodedata.normalize("NFC", text).split())


class PointIndex:
    """`points.toml`'s documents by name, and every point it holds."""

    def __init__(self, points: Points) -> None:
        self._keys = {_name(document.name): document.key for document in points.documents}
        self.ids = frozenset(point.id for point in points.points)

    def point_of(self, passage_id: str) -> str | None:
        """The point a passage is, None when `points.toml` holds no such point."""
        name, slash, chunk = passage_id.rpartition("/")
        key = self._keys.get(_name(name))
        found = _CHUNK.fullmatch(chunk)
        if not slash or key is None or found is None:
            return None
        number = found["named"] or f"{int(found['bare']):03d}"
        point = f"{key}-{number}"
        return point if point in self.ids else None

    def hit(self, passages: Sequence[str], expected: Collection[str]) -> bool:
        """Whether an expected point is among the first `TOP` passages."""
        return any(self.point_of(passage) in expected for passage in passages[:TOP])


class _Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", hide_input_in_errors=True)


class _Metadata(_Snapshot):
    document_name: str
    chunk_id: str | int  # as the adapter takes it (passages.py's `Metadata`)
    source_text: str | None = None


class _Payload(_Snapshot):
    metadata: _Metadata
    page_content: str | None = None


class _Line(_Snapshot):
    payload: _Payload


def read_point_texts(path: Path, index: PointIndex) -> dict[str, str]:
    """Each point's text in the snapshot at `path`, by its ID in `points.toml`; a point
    `points.toml` does not hold is skipped. TalkerDataError naming the line and the fields when a
    line is not a point."""
    text = read_text(path)
    if text is None:
        raise TalkerDataError(f"--points-text {path.name} cannot be read as UTF-8 text")
    found: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        where = f"{path.name}, line {number}"
        payload = parse_json(_Line, line, partial(_not_a_point, where)).payload
        point = index.point_of(
            passage_id(payload.metadata.document_name, payload.metadata.chunk_id)
        )
        body = payload.metadata.source_text or payload.page_content
        if point is not None and body:
            found[point] = body
    return found


def _not_a_point(where: str, problem: str) -> TalkerDataError:
    return TalkerDataError(f"{where}: not a point ({problem})")


@dataclass(frozen=True)
class Search:
    """One search the talker's tool made: its query, the first `TOP` passages' IDs, and whether
    the knowledge base failed it."""

    query: str
    passages: tuple[str, ...] = ()
    failed: bool = False


class RecordingKnowledge:
    """`kb`, each search kept (the module's docstring); a `KnowledgeBase`."""

    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb
        self.searches: list[Search] = []

    async def search(
        self, query: str, *, language: Tag, caller: Caller, limit: int
    ) -> list[Passage]:
        try:
            found = await self.kb.search(
                query, language=language, caller=caller, limit=max(limit, TOP)
            )
        except Exception:
            self.searches.append(Search(query, failed=True))
            raise
        self.searches.append(Search(query, tuple(passage.id for passage in found[:TOP])))
        return found[:limit]


@dataclass(frozen=True)
class KnowledgeData:
    """The knowledge set as a run reads it: its items by ID, the points' index, the expected
    points' text, and the digest of every file the run depends on."""

    items: Mapping[str, KnowledgeItem]
    index: PointIndex
    texts: Mapping[str, str]
    digest: str

    def evidence(self, item: KnowledgeItem) -> Evidence:
        return Evidence(
            kind=item.kind,
            points=tuple(self.texts[point] for point in item.expected),
            key_facts=item.key_facts,
        )

    def check_texts(self, items: Sequence[KnowledgeItem]) -> None:
        """Refused when an expected point of `items` has no text for the judge."""
        if lacking := sorted({p for item in items for p in item.expected} - set(self.texts)):
            raise run_refused(
                f"--points-text holds no text for {len(lacking)} expected point(s), "
                f"such as {lacking[0]}",
                "give the snapshot of every point of the knowledge base",
            )


def load_knowledge(data: Path, points_text: Path, others: Sequence[Path] = ()) -> KnowledgeData:
    """The knowledge set under `data`, and the points' text from `points_text`; `others` are
    more files the run depends on, digested with them."""
    folder = data / KNOWLEDGE_DIR
    try:
        items = load_knowledge_items(folder)
        points = read_toml(folder / POINTS_FILE, Points)
    except GoldenSetError as error:
        raise run_refused(
            f"the knowledge set cannot be read ({error})", "fix it; `poe check`"
        ) from None
    index = PointIndex(points)
    texts = read_point_texts(points_text, index)
    files = [*sorted(folder.glob("*.toml")), *others, points_text]
    return KnowledgeData({i.id: i for i in items}, index, texts, digest(files))


def digest(files: Sequence[Path]) -> str:
    """The SHA-256 of `files`, each by its name and its bytes, in order."""
    found = hashlib.sha256()
    for path in files:
        body = path.read_bytes()
        found.update(f"{path.name}\0{len(body)}\0".encode())
        found.update(body)
    return found.hexdigest()
