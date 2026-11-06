"""Ole5's points as the library's passages (ole5_voice/passages.py): the ID that maps to the
knowledge set's points, the title, the text, the steps, the score and the source, and a point
that cannot be read left out. Every payload here is made up."""

from __future__ import annotations

from typing import Any

import pytest
from ole5_voice.passages import passage, passages, steps_of, title_of
from t2_agentic_voice.ports import Passage

DOCUMENT = "دليل مختلق — الإجراءات"


def _point(**metadata: Any) -> dict[str, Any]:
    meta = {"document_name": DOCUMENT, "chunk_id": "chunk_004"} | metadata
    return {
        "id": 7,
        "score": 0.62,
        "payload": {"page_content": "ملخص.\n\nنص الصفحة", "metadata": meta},
    }


def test_a_point_is_a_passage_named_by_its_document_and_chunk() -> None:
    text = "أرشفة مراسلة مختلقة\n1. افتح المراسلة.\n2. اضغط **أرشفة**."
    made = passage(_point(section="الأرشفة", source_text=f"  {text}\n"))
    assert made == Passage(
        id=f"{DOCUMENT}/chunk_004",
        title="الأرشفة",
        text=text,
        steps=("افتح المراسلة.", "اضغط أرشفة."),
        score=0.62,
        source=DOCUMENT,
    )


def test_the_text_is_the_page_content_when_the_source_text_is_missing() -> None:
    made = passage(_point(source_text="   "))
    assert made is not None and made.text == "ملخص.\n\nنص الصفحة"
    made = passage(_point(chunk_id=12))
    assert made is not None and made.id == f"{DOCUMENT}/12"


@pytest.mark.parametrize(
    ("text", "title"),
    [
        ("## سياسات التصعيد\n- أولاً", "سياسات التصعيد"),
        ("مقدمة قصيرة\n# **العنوان** #\nنص", "العنوان"),
        ("إنشاء المراسلة وإرسالها\n- يمكن إنشاء مراسلة", "إنشاء المراسلة وإرسالها"),
        ("1. خطوة أولى\n2. خطوة ثانية", None),
        ("كلمة " * 40, None),
        ("", None),
    ],
)
def test_the_title_is_the_texts_first_heading(text: str, title: str | None) -> None:
    assert title_of(text) == title


def test_the_title_falls_back_to_the_section_then_the_document() -> None:
    made = passage(_point(section="  ", source_text="1. خطوة أولى\n2. خطوة ثانية"))
    assert made is not None and made.title == DOCUMENT
    made = passage(_point(section="قسم", source_text="## عنوان\nنص"))
    assert made is not None and made.title == "قسم"


def test_the_steps_are_the_numbered_and_bulleted_lines_in_order() -> None:
    text = "\n".join(
        [
            "الخطوات:",
            "1. **إلى** — الإدارة.",
            "2) من",
            "١. خطوة بأرقام عربية",
            "۳- خطوة بأرقام فارسية",
            "- نقطة",
            "* نجمة",
            "• رمز",
            "-بلا مسافة",
            "10.5 ليست خطوة",
            "- ",
            "- **  **",
        ]
    )
    assert steps_of(text) == (
        "إلى — الإدارة.",
        "من",
        "خطوة بأرقام عربية",
        "خطوة بأرقام فارسية",
        "نقطة",
        "نجمة",
        "رمز",
    )
    assert steps_of("نص بلا خطوات") == ()


@pytest.mark.parametrize(
    "point",
    [
        {"score": 0.5, "payload": {"metadata": {"chunk_id": "chunk_001"}}},  # no document
        {"score": 0.5, "payload": {"metadata": {"document_name": DOCUMENT}}},  # no chunk
        {"score": "high", "payload": {"metadata": {"document_name": DOCUMENT, "chunk_id": "c"}}},
        {"score": 0.5},  # no payload
        {"payload": {"metadata": {"document_name": DOCUMENT, "chunk_id": "c"}}},  # no score
        _point(source_text=" ")
        | {"payload": {"metadata": {"document_name": DOCUMENT, "chunk_id": "c"}}},
        _point(document_name="x" * 300),  # an ID too long for a passage
        "not a point",
    ],
)
def test_a_point_that_cannot_be_read_is_none(point: object) -> None:
    assert passage(point) is None


def test_the_passages_keep_the_points_order(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING")
    first, second = _point(chunk_id="chunk_009"), _point(chunk_id="chunk_002")
    found = passages([first, "not a point", second])
    assert [p.id for p in found] == [f"{DOCUMENT}/chunk_009", f"{DOCUMENT}/chunk_002"]
    [skipped] = [r for r in caplog.records if r.getMessage() == "knowledge_points_skipped"]
    assert vars(skipped)["fields"] == {"skipped": 1}
    assert passages([]) == []
