"""The repeat measures of a call's replies (testing/repeats.py), through the `evals` facade: an
identical repeat, a near repeat by its first clause or its token overlap, the cut repeat's
share, the exemptions and a reply that says nothing, on crafted replies in Saudi Arabic, MSA
and English."""

from __future__ import annotations

import pytest
from t2_agentic_voice.evals import (
    Repeat,
    cut_reply_share,
    find_repeat,
    first_clause,
    repeats_cut_reply,
    token_overlap,
)
from t2_agentic_voice.testing.repeats import CUT_REPEAT_SHARE, NEAR_REPEAT_OVERLAP

LISTING_EN = "There are three flights to London on Thursday, at nine, noon and six."
LISTING_SAUDI = "عندي لك ثلاث رحلات للرياض بكرة، الصبح والظهر والليل."
LISTING_MSA = "توجد ثلاث رحلات إلى لندن يوم الخميس صباحًا وظهرًا ومساءً"


def test_the_thresholds_are_the_registered_ones() -> None:
    assert NEAR_REPEAT_OVERLAP == 0.8
    assert CUT_REPEAT_SHARE == 0.6


@pytest.mark.parametrize(
    ("before", "reply"),
    [
        ("Let me check the flights.", "let me CHECK the flights"),
        ("أبشر، لقيت لك رحلتين.", "ابشر لقيت لك رحلتين"),  # hamza and punctuation folded
        ("حسنًا، الرحلة رقم ٤٠١ متاحة.", "حسنا الرحلة رقم 401 متاحة"),  # tanween, digits
        ("تمام، خلني أشيك.", "تمـــام، خلني اشيك."),  # tatweel
    ],
)
def test_the_same_normalized_text_is_an_identical_repeat(before: str, reply: str) -> None:
    found = find_repeat(reply, ["Hello, where to?", before])
    assert found == Repeat(kind="identical", earlier=1, by="text", overlap=1.0)


@pytest.mark.parametrize(
    ("before", "reply"),
    [
        ("Let me check the guide. One moment.", "Let me check the guide, then the fares."),
        ("خلني أشيك على الرحلات؟ لحظة", "خلني اشيك على الرحلات، عندك تاريخ ثاني؟"),
        ("دعني أتحقق من الرحلات؛ لحظة من فضلك", "دعني اتحقق من الرحلات. هل لديك تاريخ آخر؟"),
    ],
)
def test_the_same_first_clause_is_a_near_repeat(before: str, reply: str) -> None:
    found = find_repeat(reply, [before])
    assert found is not None
    assert (found.kind, found.earlier, found.by) == ("near", 0, "first_clause")
    assert found.overlap < NEAR_REPEAT_OVERLAP


def test_a_one_word_opener_is_a_first_clause_as_registered() -> None:
    """The registered definition reads any first clause, so two replies opening with «تمام،»
    or "Sure," and going on apart are a near repeat."""
    assert find_repeat("Sure, two travelers.", ["Sure, which day?"]) is not None
    assert find_repeat("تمام، كم مسافر؟", ["تمام، أي يوم؟"]) is not None


@pytest.mark.parametrize(
    ("before", "reply"),
    [
        (LISTING_EN, "There are three flights to London on Thursday at nine, noon and six today."),
        (LISTING_SAUDI, "عندي لك ثلاث رحلات للرياض بكرة الصبح والظهر والليل كلها."),
        (LISTING_MSA, "توجد ثلاث رحلات إلى لندن يوم الخميس صباحا وظهرا ومساء أيضا"),
    ],
)
def test_a_token_overlap_of_four_in_five_is_a_near_repeat(before: str, reply: str) -> None:
    found = find_repeat(reply, [before])
    assert found is not None
    assert (found.kind, found.by) == ("near", "overlap")
    assert found.overlap >= NEAR_REPEAT_OVERLAP


def test_an_overlap_just_under_four_in_five_is_no_repeat() -> None:
    # 8 tokens shared over the longer reply's 11 (0.73), first clauses apart
    before = "red green blue black white pink gray brown"
    reply = "brown gray pink white black blue green red alpha beta gamma"
    assert token_overlap(reply, before) == pytest.approx(8 / 11)
    assert find_repeat(reply, [before]) is None


def test_the_overlap_reads_the_longer_reply_so_a_short_reply_is_no_repeat() -> None:
    assert token_overlap("To London.", LISTING_EN) == pytest.approx(2 / 13)
    assert token_overlap(LISTING_EN, "To London.") == token_overlap("To London.", LISTING_EN)
    assert find_repeat("To London.", [LISTING_EN]) is None


def test_tokens_are_a_multiset() -> None:
    assert token_overlap("yes yes yes", "yes") == pytest.approx(1 / 3)
    assert cut_reply_share("yes", "yes yes yes no no") == pytest.approx(1 / 5)


def test_an_identical_repeat_is_preferred_and_the_latest_named() -> None:
    replies = [LISTING_EN, "Which day?", LISTING_EN, LISTING_EN.replace("six", "six tonight")]
    found = find_repeat(LISTING_EN, replies)
    assert found == Repeat(kind="identical", earlier=2, by="text", overlap=1.0)
    near = find_repeat("Which day? Or a week later.", ["Which day, then?", "Which day?"])
    assert near is not None
    assert (near.kind, near.earlier) == ("near", 1)


def test_different_replies_are_no_repeat() -> None:
    replies = [LISTING_EN, LISTING_SAUDI, LISTING_MSA]
    assert find_repeat("The cheapest is 420 riyals, economy.", replies) is None
    assert find_repeat("أرخص وحدة بأربعمية وعشرين ريال.", replies) is None


@pytest.mark.parametrize("flags", [{"asks_repeat": True}, {"read_back": True}])
def test_an_asked_repeat_and_a_read_back_said_again_are_exempt(flags: dict[str, bool]) -> None:
    read_back = "رحلتك من الرياض إلى لندن يوم الخميس، شخص واحد، الدرجة السياحية. أأكد الحجز؟"
    assert find_repeat(LISTING_EN, [LISTING_EN], **flags) is None
    assert find_repeat(read_back, [read_back], **flags) is None
    assert find_repeat(read_back, [read_back]) is not None


@pytest.mark.parametrize("empty", ["", "   ", ". . ؟ ،", "‏"])
def test_a_reply_that_says_nothing_is_no_repeat_and_repeats_nothing(empty: str) -> None:
    assert find_repeat(empty, [empty, LISTING_EN]) is None
    assert find_repeat(LISTING_EN, [empty]) is None
    assert first_clause(empty) == ""
    assert token_overlap(empty, LISTING_EN) == 0.0
    assert token_overlap(LISTING_EN, empty) == 0.0
    assert cut_reply_share(LISTING_EN, empty) == 0.0
    assert cut_reply_share(empty, LISTING_EN) == 0.0
    assert not repeats_cut_reply(LISTING_EN, empty)


def test_earlier_is_a_sequence_of_replies() -> None:
    with pytest.raises(TypeError, match="sequence of replies"):
        find_repeat(LISTING_EN, LISTING_EN)


@pytest.mark.parametrize(
    ("text", "clause"),
    [
        ("تمام، خلني أشوف", "تمام"),  # Arabic comma
        ("كم مسافر؟ وأي درجة", "كم مسافر"),  # Arabic question mark
        ("خلني أشيك على الرحلات؛ لحظة", "خلني اشيك علي الرحلات"),  # Arabic semicolon, folded
        ("الرحلة الأولى۔ الثانية", "الرحله الاولي"),  # Arabic full stop
        ("بالضبط؟وش تبي", "بالضبط"),  # a sentence's end glued to the next
        ("Let me check the guide. One moment.", "let me check the guide"),
        ("Flight 3.5 hours long, fine", "flight 35 hours long"),  # a mark in a word cuts none
        (". . Sure, fine", "sure"),  # a clause of marks only is left out
        ("no marks at all", "no marks at all"),
    ],
)
def test_the_first_clause_is_cut_by_the_library_splitter(text: str, clause: str) -> None:
    assert first_clause(text) == clause


@pytest.mark.parametrize(
    ("cut", "again"),
    [
        (
            "There are three flights to London on Thursday: at nine, at noon and at six.",
            "Sure: three flights to London on Thursday, at nine, noon and six.",
        ),
        (LISTING_SAUDI, "أكيد، عندي ثلاث رحلات للرياض بكرة: الصبح والظهر والليل."),
        (LISTING_MSA, "بالتأكيد، توجد ثلاث رحلات إلى لندن يوم الخميس: صباحا وظهرا ومساء."),
    ],
)
def test_a_reply_holding_most_of_the_cut_reply_repeats_it(cut: str, again: str) -> None:
    assert cut_reply_share(again, cut) >= CUT_REPEAT_SHARE
    assert repeats_cut_reply(again, cut)


@pytest.mark.parametrize(
    ("cut", "again"),
    [
        (LISTING_EN, "I can help you with flights."),
        (LISTING_SAUDI, "أقدر أساعدك في الرحلات."),
        (LISTING_MSA, "يمكنني مساعدتك في حجز الرحلات."),
    ],
)
def test_a_reply_that_says_little_of_the_cut_reply_does_not(cut: str, again: str) -> None:
    assert not repeats_cut_reply(again, cut)


def test_the_cut_share_reads_the_cut_reply_and_holds_at_three_in_five() -> None:
    cut = "red green blue black white"
    assert cut_reply_share("red green blue", cut) == pytest.approx(0.6)
    assert repeats_cut_reply("red green blue", cut)
    assert not repeats_cut_reply("red green", cut)
    # a longer reply that says all of the cut one and more still repeats it
    assert repeats_cut_reply(f"Again: {cut}, and pink, gray and brown.", cut)
