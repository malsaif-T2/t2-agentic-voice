"""A card's links (domain/cards.py's `CardLink`, D-126): none by default, so a card with none is
as it was (GP-18); each a label of 1 to 40 characters with no digit, which the output guard
reads with the card's texts, and an https url of at most 2048 characters, of any host, which no
guard reads (`texts` never holds it); at most two to a card; and `t2v/1`'s `card` carries them
as the tool gave them."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from t2_agentic_voice import Card, CardLink, CardRow
from t2_agentic_voice.domain.cards import MAX_LINKS, MAX_URL
from t2_agentic_voice.voice.protocol import ShowCard, wire

LEAK = "zx-made-up-link-42"  # a value no refusal may repeat
URL = "https://www.google.com/travel/flights?q=Flights%20to%20JED%20from%20RUH&hl=en"


def test_a_card_has_no_links_by_default_and_its_texts_and_payload_are_as_they_were() -> None:
    card = Card(title="Reset", steps=("Open Settings",), source="a.pdf")
    assert card.links == ()
    assert card.texts() == ("Reset", "Open Settings", "a.pdf")
    assert wire(ShowCard.of(card))["links"] == []


def test_a_links_label_is_read_with_the_cards_texts_and_its_url_never_is() -> None:
    links = (
        CardLink(label="Book on flynas", url=URL),
        CardLink(label="احجز على طيران ناس", url=URL),
    )
    card = Card(title="Your trip", rows=(CardRow(title="Total", value="429 SAR"),), links=links)
    assert card.texts() == ("Your trip", "Total", "429 SAR", "Book on flynas", "احجز على طيران ناس")
    assert all("https" not in text and "google" not in text for text in card.texts())


def test_the_payload_carries_the_links_as_the_tool_gave_them() -> None:
    other = "https://example.com/" + "a" * (MAX_URL - len("https://example.com/"))
    links = (CardLink(label="Book on Saudia", url=URL), CardLink(label="x" * 40, url=other))
    sent = wire(ShowCard.of(Card(title="Your trip", slot="review", links=links)))
    assert sent["links"] == [
        {"label": "Book on Saudia", "url": URL},
        {"label": "x" * 40, "url": other},
    ]
    assert len(other) == MAX_URL == 2048
    assert ShowCard.model_validate(sent) == ShowCard.of(
        Card(title="Your trip", slot="review", links=links)
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://www.google.com/travel/flights",  # not https
        "javascript:alert(1)",
        "data:text/html,<b>x</b>",
        "https://",  # no host
        "https:///travel",
        "//www.google.com/travel",
        "www.google.com/travel",
        "https://www.google.com/travel flights",  # a space
        "https://www.google.com/\n",
        "https://www.google.com/رحلات",  # not ASCII: an address is sent encoded
        "https://example.com/" + "a" * MAX_URL,  # too long
        "",
        f"ftp://{LEAK}",
    ],
)
def test_a_url_that_is_not_https_or_past_its_bound_is_refused(url: str) -> None:
    with pytest.raises(ValidationError) as refused:
        CardLink(label="Book", url=url)
    assert LEAK not in str(refused.value)


@pytest.mark.parametrize(
    "label",
    ["", "   ", "x" * 41, "Book SV 1020", "احجز ١٠٢٠", f"{LEAK}"],
)
def test_a_label_past_its_bounds_or_with_a_digit_is_refused(label: str) -> None:
    with pytest.raises(ValidationError) as refused:
        CardLink(label=label, url=URL)
    assert LEAK not in str(refused.value)


def test_a_card_holds_at_most_two_links_and_a_link_no_other_field() -> None:
    link = CardLink(label="Book", url=URL)
    assert len(Card(title="t", links=(link,) * MAX_LINKS).links) == MAX_LINKS == 2
    with pytest.raises(ValidationError):
        Card(title="t", links=(link,) * (MAX_LINKS + 1))
    with pytest.raises(ValidationError):
        ShowCard(title="t", links=(link,) * (MAX_LINKS + 1))
    with pytest.raises(ValidationError):
        CardLink.model_validate({"label": "Book", "url": URL, "target": "_self"})
