"""How runs K and S read Ole5's knowledge base (kb_points.py): a passage's ID mapped to the
knowledge set's point through its document's name, a point it does not hold a miss; the points'
text read from a snapshot; and the searches the talker's tool made, kept by the recorder."""

from __future__ import annotations

import asyncio
import json
import unicodedata
from pathlib import Path

import pytest
from ole5_voice.evals.items import EVALS, read_toml
from ole5_voice.evals.kb_points import TOP, PointIndex, RecordingKnowledge, read_point_texts
from ole5_voice.evals.knowledge_set import (
    KNOWLEDGE_DIR,
    POINTS_FILE,
    Document,
    Point,
    Points,
    load_knowledge_items,
)
from ole5_voice.evals.talker_data import TalkerDataError
from ole5_voice.passages import passage as live_passage
from t2_agentic_voice import Caller

from tests.ole5_voice.evals.talker_fakes import DOCUMENT, FakeKnowledgeBase, passage
from tests.ole5_voice.evals.talker_support import write_points_text

INDEX = PointIndex(
    Points(
        documents=(Document(key="guide", name=DOCUMENT), Document(key="rules", name="A / B")),
        points=(
            Point(id="guide-001", document="guide", chunk="chunk_001"),
            Point(id="guide-002", document="guide", chunk="chunk_002"),
            Point(id="rules-003", document="rules", chunk="chunk_003"),
        ),
    )
)


@pytest.mark.parametrize(
    ("passage_id", "point"),
    [
        (f"{DOCUMENT}/chunk_001", "guide-001"),
        ("A / B/chunk_003", "rules-003"),  # a document whose name holds a slash
        (f"{DOCUMENT}/chunk_009", None),  # a chunk points.toml does not hold
        ("Another document/chunk_001", None),
        (f"{DOCUMENT}/chunk_1", None),
        ("no-slash", None),
    ],
)
def test_a_passage_maps_to_its_point_or_to_none(passage_id: str, point: str | None) -> None:
    assert INDEX.point_of(passage_id) == point


def test_a_hit_is_an_expected_point_among_the_first_five() -> None:
    ids = [f"{DOCUMENT}/chunk_00{n}" for n in (9, 8, 7, 6, 2, 1)]
    assert INDEX.hit(ids, {"guide-002"}) is True
    assert INDEX.hit(ids, {"guide-001"}) is False  # sixth
    assert INDEX.hit([], {"guide-001"}) is False


def test_the_points_text_is_read_from_the_snapshot(tmp_path: Path) -> None:
    path = write_points_text(tmp_path / "points.jsonl", points=3)
    with path.open("a", encoding="utf-8") as file:
        file.write("\n")  # a blank line is skipped
        file.write(
            '{"payload": {"metadata": {"document_name": "A / B", "chunk_id": "chunk_002"}, '
            '"page_content": "The page."}}\n'
        )
    texts = read_point_texts(path, INDEX)
    assert texts == {
        "guide-001": "The made-up text of point 1.",
        "guide-002": "The made-up text of point 2.",
    }  # point 3 is not in the index; rules' chunk 2 is not a point


def test_the_page_content_stands_in_for_a_missing_source_text(tmp_path: Path) -> None:
    path = tmp_path / "points.jsonl"
    path.write_text(
        '{"payload": {"metadata": {"document_name": "A / B", "chunk_id": "chunk_003", '
        '"source_text": null}, "page_content": "Its page."}}\n',
        encoding="utf-8",
    )
    assert read_point_texts(path, INDEX) == {"rules-003": "Its page."}


def test_a_snapshot_that_cannot_be_read_is_refused_by_its_line(tmp_path: Path) -> None:
    path = tmp_path / "points.jsonl"
    path.write_text('{"payload": {"metadata": {"chunk_id": "chunk_001"}}}\n', encoding="utf-8")
    with pytest.raises(TalkerDataError, match=r"points\.jsonl, line 1: not a point"):
        read_point_texts(path, INDEX)
    with pytest.raises(TalkerDataError, match="cannot be read"):
        read_point_texts(tmp_path / "missing.jsonl", INDEX)


def test_the_recorder_keeps_each_search_and_hands_the_tool_its_limit() -> None:
    inner = FakeKnowledgeBase()
    inner.found["q"] = [passage(n) for n in range(1, 8)]
    inner.failing.add("bad")
    recording = RecordingKnowledge(inner)
    caller = Caller(subject="x")
    found = asyncio.run(recording.search("q", language="ar-SA", caller=caller, limit=2))
    assert [p.id for p in found] == [passage(1).id, passage(2).id]
    assert inner.searches == [("q", "ar-SA", TOP)]
    with pytest.raises(Exception, match="provider"):
        asyncio.run(recording.search("bad", language="en", caller=caller, limit=8))
    first, failed = recording.searches
    assert first.query == "q" and len(first.passages) == TOP and not first.failed
    assert failed.failed and failed.passages == () and inner.searches[-1][2] == 8


def _payload(name: str, chunk: str | int, text: str) -> dict[str, object]:
    return {"metadata": {"document_name": name, "chunk_id": chunk, "source_text": text}}


def test_every_committed_point_found_live_is_the_point_the_judges_text_names(
    tmp_path: Path,
) -> None:
    """For each point of the committed `points.toml`, a payload as Qdrant gives it: the passage
    the adapter makes of it (passages.py) maps to that point, and the same payload in the
    snapshot (`--points-text`) gives that point's text, so no retrieved passage is a miss for
    its ID's form, and the judge reads the text of the point found."""
    points = read_toml(EVALS / KNOWLEDGE_DIR / POINTS_FILE, Points)
    index = PointIndex(points)
    names = {document.key: document.name for document in points.documents}
    lines = []
    for point in points.points:
        payload = _payload(names[point.document], point.chunk, f"The text of {point.id}.")
        found = live_passage({"score": 0.6, "payload": payload})
        assert found is not None and index.point_of(found.id) == point.id
        lines.append(json.dumps({"id": point.id, "payload": payload}, ensure_ascii=False))
    snapshot = tmp_path / "points.jsonl"
    snapshot.write_text("\n".join(lines) + "\n", encoding="utf-8")
    texts = read_point_texts(snapshot, index)
    assert texts == {point.id: f"The text of {point.id}." for point in points.points}
    # Every expected point of the knowledge set is one of them.
    items = load_knowledge_items(EVALS / KNOWLEDGE_DIR)
    assert {p for item in items for p in item.expected} <= set(texts)


@pytest.mark.parametrize(
    ("name", "chunk"),
    [
        (unicodedata.normalize("NFD", DOCUMENT), "chunk_002"),  # another Unicode form
        (f"  {DOCUMENT}  ", "chunk_002"),  # spaces around it
        (DOCUMENT.replace(" ", "  "), "chunk_002"),  # two spaces for one
        (DOCUMENT, 2),  # a chunk ID held as a number
        (DOCUMENT, "2"),
    ],
)
def test_a_passages_id_form_never_makes_a_miss(tmp_path: Path, name: str, chunk: str | int) -> None:
    found = live_passage({"score": 0.6, "payload": _payload(name, chunk, "Some text.")})
    assert found is not None and INDEX.point_of(found.id) == "guide-002"
    line = json.dumps({"id": 2, "payload": _payload(name, chunk, "Some text.")})
    (snapshot := tmp_path / "points.jsonl").write_text(line + "\n", encoding="utf-8")
    assert read_point_texts(snapshot, INDEX) == {"guide-002": "Some text."}
