"""A card's option rows (domain/cards.py): data only, each text bounded, a mark from a closed
set, at most eight to a card, none by default, and every text of a row read with the card's own
by the output guard (`texts`)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from t2_agentic_voice import Card, CardRow
from t2_agentic_voice.domain.cards import CARD_MARKS, MAX_ROWS

LEAK = "zx-made-up-row-42"  # a value no refusal may repeat


def test_a_card_has_no_rows_by_default_and_its_texts_are_as_they_were() -> None:
    card = Card(title="Reset", steps=("Open Settings",), source="a.pdf")
    assert card.rows == ()
    assert card.texts() == ("Reset", "Open Settings", "a.pdf")


def test_a_rows_texts_are_read_with_the_cards_in_order() -> None:
    rows = (
        CardRow(title="09:10 to 16:15", detail="flight T2 401 on a 787-9", value="2,450 SAR"),
        CardRow(title="14:40 to 21:45", mark="unavailable"),
    )
    card = Card(title="Riyadh to London", steps=("Nonstop",), rows=rows, source="timetable")
    assert card.texts() == (
        "Riyadh to London",
        "Nonstop",
        "09:10 to 16:15",
        "flight T2 401 on a 787-9",
        "2,450 SAR",
        "14:40 to 21:45",
        "timetable",
    )


def test_the_marks_are_a_closed_set() -> None:
    assert CARD_MARKS == ("best", "chosen", "unavailable")
    for mark in CARD_MARKS:
        assert CardRow(title="x", mark=mark).mark == mark
    with pytest.raises(ValidationError) as refused:
        CardRow.model_validate({"title": "x", "mark": LEAK})
    assert LEAK not in str(refused.value)


@pytest.mark.parametrize(
    "row",
    [
        {"title": "x" * 81},
        {"title": "x", "detail": "x" * 121},
        {"title": "x", "value": "x" * 41},
        {"title": ""},
        {"title": "   "},
        {"title": "x", "detail": " "},
        {"title": "x", "value": ""},
        {"title": "x", "note": LEAK},  # no field beyond the four
        {"title": f"<b>{LEAK}</b>" * 20},
    ],
)
def test_a_row_past_its_bounds_or_with_an_unknown_field_is_refused(row: dict[str, str]) -> None:
    with pytest.raises(ValidationError) as refused:
        CardRow.model_validate(row)
    assert LEAK not in str(refused.value)


def test_a_card_holds_at_most_eight_rows() -> None:
    rows = tuple(CardRow(title=f"option {n}") for n in range(MAX_ROWS))
    assert len(Card(title="t", rows=rows).rows) == MAX_ROWS == 8
    with pytest.raises(ValidationError):
        Card(title="t", rows=(*rows, CardRow(title="one more")))


def test_a_row_at_its_bounds_is_taken() -> None:
    row = CardRow(title="x" * 80, detail="d" * 120, value="v" * 40, mark="best")
    assert row.texts() == ("x" * 80, "d" * 120, "v" * 40)
