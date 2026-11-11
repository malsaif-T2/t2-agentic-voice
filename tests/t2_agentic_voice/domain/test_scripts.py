"""The scripts a reply may hold (domain/text/scripts.py): the characters of the agent's own
scripts, punctuation, symbols, the arrows the speaking rules read and every digit the agent
writes are kept; a fullwidth form, the ideographic space, comma and full stop, and a digit of
another script are written as their ASCII form; every other letter or mark, the CJK and Hangul
ranges whatever their category, the pictographs and the private-use and surrogate code points
are taken out, each counted and labelled. A term the agent declares keeps its characters. Each
character is judged alone, so a text cut into pieces gives what it gives whole, and filtering
twice gives what filtering once does."""

from __future__ import annotations

import dataclasses
import unicodedata

import pytest
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.text.scripts import Kept, remove_stray_script

# The blocks each script keeps, as the rule lists them.
LATIN = [(0x0000, 0x036F), (0x1E00, 0x1EFF), (0x2C60, 0x2C7F), (0xA720, 0xA7FF), (0xFB00, 0xFB06)]
ARABIC = [(0x0600, 0x06FF), (0x0750, 0x077F), (0x0870, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)]
# What every agent keeps: General Punctuation, the Arabic-Indic and Persian digits, and every
# arrow the speaking rules read as "then".
ALWAYS = [
    (0x2000, 0x206F),
    (0x0660, 0x0669),
    (0x06F0, 0x06F9),
    (0x2190, 0x21FF),
    (0x27F0, 0x27FF),
    (0x2794, 0x2794),
    (0x279C, 0x279C),
]
PRESETS: dict[LanguageTag, list[tuple[int, int]]] = {
    "ar-SA": [*ARABIC, *LATIN],
    "ar": [*ARABIC, *LATIN],
    "en": LATIN,
}
# The owner's demo: "the icon 'reset the user's password'", with two Chinese characters («重新»,
# "again") where the passage holds «إعادة» ("i'aadat", resetting).
DEMO = 'أيقونة "إ重新 كلمة مرور المستخدم"'
DEMO_KEPT = 'أيقونة "إ كلمة مرور المستخدم"'
# A pictograph of each range taken out, and each emoji of the fixed set below U+1F000.
PICTOGRAPHS = [
    0x1F004,
    0x1F1F8,
    0x1F600,
    0x1F680,
    0x1F9D1,
    0x1FAF6,
    0x2600,
    0x2705,
    0x2714,
    0x27A1,
    0x27BF,
    *(0x231A, 0x231B, 0x2328, 0x23CF, *range(0x23E9, 0x23F4), 0x23F8, 0x23F9, 0x23FA),
    *(0x24C2, 0x25AA, 0x25AB, 0x25B6, 0x25C0, *range(0x25FB, 0x25FF)),
    *(0x2934, 0x2935, 0x2B05, 0x2B06, 0x2B07, 0x2B1B, 0x2B1C, 0x2B50, 0x2B55),
]
# Texts a model may write, in the agent's scripts and out of them, for the cut and the repeat.
SAMPLES = [
    DEMO,
    "Open Settings → Accounts, then press Reset重置 😀.",
    "اضغط Ctrl+Shift+R ثم «تحديث» ١٢٣ ۴۵ ，１２３ Restart it。Then",
    "Ваш пароль μs 10² ½ ५ ⭐▶ →️",
]
EVERYONE: list[tuple[LanguageTag, ...]] = [("en",), ("ar-SA",), ("ar",), ("ar-SA", "en")]


def _kept(text: str, *languages: LanguageTag, kept: tuple[str, ...] = ()) -> Kept:
    return remove_stray_script(text, languages=languages or ("en",), kept=kept)


@pytest.mark.parametrize("tag", sorted(PRESETS))
def test_every_code_point_of_a_presets_blocks_and_of_the_shared_ones_is_kept(
    tag: LanguageTag,
) -> None:
    for start, end in [*PRESETS[tag], *ALWAYS]:
        text = "".join(chr(code) for code in range(start, end + 1))
        found = _kept(text, tag)
        assert (found.text, found.changed, found.labels) == (text, 0, ()), hex(start)


def test_the_demo_loses_its_two_chinese_characters_and_nothing_else() -> None:
    found = _kept(DEMO, "ar-SA", "en")
    assert found == Kept(text=DEMO_KEPT, changed=2, labels=("CJK",))
    assert _kept(DEMO, "ar-SA").text == DEMO_KEPT  # one Arabic preset: the same


def test_an_english_agent_takes_out_arabic_letters_and_keeps_arabic_indic_digits() -> None:
    # "shukran", thanks; ٣ is 3.
    found = _kept("Press ٣ and ۴, شكرا", "en")
    assert found == Kept(text="Press ٣ and ۴, ", changed=4, labels=("ARABIC",))


@pytest.mark.parametrize(
    "text",
    [
        "اضغط Ctrl+Shift+R في Ole5",  # "press Ctrl+Shift+R in Ole5"
        "راسلنا على help.desk@example.com",  # "write to us at ..."
        "افتح https://example.com/reset?user=a&x=1#top",  # "open ..."
        "افتح الإعدادات → الحسابات",  # "open the settings, then the accounts"
    ],
)
def test_an_arabic_preset_keeps_latin_names_codes_emails_and_links(text: str) -> None:
    for tag in ("ar-SA", "ar"):
        found = _kept(text, tag)
        assert (found.text, found.changed) == (text, 0)
        assert found.text is text  # the text itself when nothing changed


def test_fullwidth_forms_and_ideographic_punctuation_are_written_one_for_one() -> None:
    assert _kept("，１２３", "en") == Kept(text=",123", changed=4, labels=("FULLWIDTH",))
    assert _kept("Restart it。Then", "en") == Kept(
        text="Restart it.Then", changed=1, labels=("IDEOGRAPHIC",)
    )
    assert _kept("a　b、c", "ar-SA").text == "a b,c"
    assert _kept("ＶＰＮ", "ar").text == "VPN"


def test_a_digit_of_another_script_is_its_ascii_digit_and_number_signs_stay() -> None:
    assert _kept("Step ५", "en") == Kept(text="Step 5", changed=1, labels=("DEVANAGARI",))
    assert _kept("\U0001d7d5", "en").text == "7"  # MATHEMATICAL BOLD DIGIT SEVEN
    for text in ("10²", "½", "x³", "٣", "۴"):
        assert _kept(text, "en").text == text


@pytest.mark.parametrize("code", PICTOGRAPHS, ids=hex)
def test_a_pictograph_is_taken_out(code: int) -> None:
    found = _kept(f"Done {chr(code)} now", "ar-SA", "en")
    assert found == Kept(text="Done  now", changed=1, labels=("PICTOGRAPH",))


def test_the_heavy_arrows_and_the_symbols_stay_a_variation_selector_goes() -> None:
    for text in ("a ➔ b", "a ➜ b", "© ® ™ ‼ ⁉ % $ € ± ≥ « » “ ”", "﷼ ٪ ؟ ،"):
        assert _kept(text, "ar-SA").text == text
    assert _kept("Open →️ Reset", "en") == Kept(
        text="Open → Reset", changed=1, labels=("VARIATION",)
    )
    assert _kept("1️⃣", "en").text == "1"  # a keycap emoji leaves its digit


def test_a_cjk_code_point_unassigned_in_pythons_tables_goes_another_unassigned_one_stays() -> None:
    newer = chr(0x2EBF0)  # CJK Extension I's first, added after Unicode 15.0
    assert unicodedata.unidata_version != "15.0.0" or unicodedata.category(newer) == "Cn"
    assert _kept(f"a{newer}b{chr(0x3A000)}c", "en").text == "abc"
    unassigned = chr(0x0378)  # unassigned in the Greek block, outside every range taken out
    assert unicodedata.category(unassigned) == "Cn"
    assert _kept(f"a{unassigned}b", "en").text == f"a{unassigned}b"


def test_hangul_private_use_and_a_lone_surrogate_go() -> None:
    found = _kept(f"a안녕b{chr(0xE000)}c{chr(0xD800)}d", "en")
    assert (found.text, found.changed) == ("abcd", 4)
    assert found.labels == ("Co", "Cs", "HANGUL")


def test_a_greek_letter_goes_unless_a_declared_term_holds_it() -> None:
    assert _kept("It takes 10 μs.", "en") == Kept(
        text="It takes 10 s.", changed=1, labels=("GREEK",)
    )
    assert _kept("It takes 10 μs.", "en", kept=("μs",)).text == "It takes 10 μs."
    assert _kept("Ваш μ", "en", kept=("μs",)).text == " μ"  # the term's characters, not more


def test_two_agents_with_other_terms_in_one_process_get_their_own_verdicts() -> None:
    assert _kept("μ λ", "en", kept=("μs",)).text == "μ "
    assert _kept("μ λ", "en", kept=("λ-desk",)).text == " λ"
    assert _kept("μ λ", "en").text == " "
    assert _kept("μ λ", "en", kept=("μs",)).text == "μ "


def test_at_most_eight_labels_sorted() -> None:
    letters = "αбאकกაաሀ가重"  # Greek, Cyrillic, Hebrew, Devanagari, Thai, Georgian, ...
    found = _kept(letters, "en")
    assert found.text == "" and found.changed == len(letters)
    assert len(found.labels) == 8 and list(found.labels) == sorted(found.labels)


def test_kept_is_frozen() -> None:
    found = _kept("a", "en")
    with pytest.raises(dataclasses.FrozenInstanceError):
        found.text = "b"  # type: ignore[misc]


@pytest.mark.parametrize("languages", EVERYONE, ids="+".join)
def test_piece_by_piece_equals_whole_for_every_cut(languages: tuple[LanguageTag, ...]) -> None:
    for sample in SAMPLES:
        whole = _kept(sample, *languages)
        for cut in range(len(sample) + 1):
            head, tail = _kept(sample[:cut], *languages), _kept(sample[cut:], *languages)
            assert head.text + tail.text == whole.text, (sample, cut)
            assert head.changed + tail.changed == whole.changed
            assert set(head.labels) | set(tail.labels) == set(whole.labels)


@pytest.mark.parametrize("languages", EVERYONE, ids="+".join)
def test_every_code_point_of_the_first_plane_gets_a_verdict_and_a_second_pass_changes_none(
    languages: tuple[LanguageTag, ...],
) -> None:
    plane = "".join(chr(code) for code in range(0x10000))
    once = _kept(plane, *languages)
    twice = _kept(once.text, *languages)
    assert twice.text == once.text and twice.changed == 0
    for code in range(0x10000):
        alone = _kept(chr(code), *languages)
        assert len(alone.text) <= 1 and alone.changed == (alone.text != chr(code)), hex(code)
