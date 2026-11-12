"""The output guard's rule A (domain/claims.py; docs/SECURITY.md, invariant 2): no clause claims
an action, or holds an action's number, unless the call's record or a `reports_on` result holds
it. Adversarial (GP-08): model text claiming a ticket was made, a passage holding a fake number,
a number never issued; each blocked without evidence and passed with it. A status result backs
only a claim that names one of its numbers, or one in a reply that already said one (the owner's
ruling of 2026-11-10 on TD-144, "Number or same reply"), while the record backs any. Every number
here is made up for the test."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.claims import (
    ActionEvidence,
    ClaimVerdict,
    any_action_claims,
    check_claims,
    default_claims,
    holds_an_id,
)
from t2_agentic_voice.domain.guard_ids import guard_form

SETTINGS = GuardSettings()
TICKET = "2026110482000123"  # the made-up number the backend issued
FAKE = "2026110482000999"  # one a passage carries, never issued
# A team's own phrases for its action, in each language.
CLAIMS: Mapping[str, Sequence[str]] = {"create_ticket": ("opened your ticket", "ticket opened")}
ARABIC_CLAIMS: Mapping[str, Sequence[str]] = {"create_ticket": ("فتحت لك التذكرة",)}
MADE = ActionEvidence(action="create_ticket", texts=(f'{{"ticket_number": "{TICKET}"}}',))
# What a status of an older ticket gives back: its whole number (a team's tool), or its last
# four digits alone (as Ole5's `ticket_status` does).
LAST_FOUR = "4417"
WHOLE_STATUS = f'{{"number": "{TICKET}", "state": "open"}}'
FOUR_STATUS = f'{{"tickets": [{{"ends_in": "{LAST_FOUR}", "status": "open"}}], "total": 1}}'


def _check(
    clause: str,
    *evidence: ActionEvidence,
    code: LanguageCode = "en",
    claims: Mapping[str, Sequence[str]] | None = None,
    settings: GuardSettings = SETTINGS,
    earlier: Sequence[str] = (),
    added: Sequence[str] = (),
) -> ClaimVerdict:
    own = claims if claims is not None else (CLAIMS if code == "en" else ARABIC_CLAIMS)
    return check_claims(
        clause,
        claims=own,
        any_action=(*default_claims(code), *added),
        evidence=evidence,
        settings=settings,
        year=2026,
        earlier=earlier,
    )


def _status(text: str, action: str = "create_ticket") -> ActionEvidence:
    """A `reports_on` tool's result about `action`, holding `text`."""
    return ActionEvidence(action=action, texts=(text,), source="status")


@pytest.mark.parametrize(
    ("clause", "code"),
    [
        ("I've created a ticket for you.", "en"),
        ("I have submitted your request to the support team.", "en"),
        ("Your ticket has been created.", "en"),
        ("Great news, I’ve opened your ticket!", "en"),  # the team's own phrase, a curly mark
        ("تم إنشاء التذكرة بنجاح.", "ar"),
        ("وتمّ إنشاء تذكرتك.", "ar"),  # after waw, with a shadda
        ("سجلت لك الطلب، وراح يتواصلون معك.", "ar"),
        ("لقد أنشأت التذكرة.", "ar"),
        ("فتحت لك التذكرة.", "ar"),
    ],
)
def test_model_text_claiming_an_action_is_blocked_without_a_record(
    clause: str, code: LanguageCode
) -> None:
    verdict = _check(clause, code=code)
    assert verdict.passed is False
    assert _check(clause, MADE, code=code).passed is True


def test_a_teams_phrase_names_its_action_and_a_default_any_action_with_evidence() -> None:
    assert _check("Ticket opened.").claimed == ("create_ticket",)
    other = ActionEvidence(action="hand_off", texts=())
    assert _check("I've created it.", MADE, other).claimed == ("create_ticket", "hand_off")
    assert _check("I've created it.") == ClaimVerdict(claimed=(), passed=False)


def test_a_claim_of_one_action_is_no_claim_of_another() -> None:
    handed = ActionEvidence(action="hand_off", texts=(f"ticket {TICKET}",))
    verdict = _check("Ticket opened.", handed)
    assert verdict == ClaimVerdict(claimed=("create_ticket",), passed=False)


@pytest.mark.parametrize(
    "clause",
    [
        f"I've created your ticket, its number is {FAKE}.",
        f"تم إنشاء تذكرتك ورقمها {FAKE}",
    ],
)
def test_a_passages_fake_number_in_a_claim_is_blocked_even_with_a_record(clause: str) -> None:
    """The passage holding it is no evidence for rule A: only the action's result is."""
    code: LanguageCode = "en" if clause.startswith("I") else "ar"
    assert _check(clause, code=code) == ClaimVerdict(claimed=(), passed=False, unsupported=(FAKE,))
    verdict = _check(clause, MADE, code=code)
    assert verdict == ClaimVerdict(claimed=("create_ticket",), passed=False, unsupported=(FAKE,))
    issued = ActionEvidence(action="create_ticket", texts=(f"number {FAKE}",))
    assert _check(clause, issued, code=code).passed


def test_a_number_never_issued_is_blocked_and_the_issued_one_passes() -> None:
    never = _check("Your ticket 4521 3390 has been created.", MADE)
    assert never.passed is False and never.unsupported == ("45213390",)
    assert _check(f"Your ticket {TICKET} has been created.", MADE).passed


@pytest.mark.parametrize(
    "said",
    [
        "4521 3390",
        "45 21 33 90",
        "4521-3390",
        "٤٥٢١٣٣٩٠",
        "four five two one three three nine zero",
    ],
)
def test_a_number_spaced_or_said_digit_by_digit_is_the_number(said: str) -> None:
    clause = f"I've opened your ticket, number {said}."
    issued = ActionEvidence(action="create_ticket", texts=('{"number": "45213390"}',))
    assert _check(clause, issued).passed
    other = ActionEvidence(action="create_ticket", texts=('{"number": "45213391"}',))
    assert _check(clause, other).unsupported == ("45213390",)


def test_a_status_result_supports_the_claim_and_its_number() -> None:
    """A `reports_on` tool's result is evidence for the action it reports on."""
    status = _status(f'{{"{TICKET}": "open"}}')
    assert _check(f"Your ticket {TICKET} has been registered and is open.", status).passed


# The owner's ruling on TD-144 ("Number or same reply"): a status backs a claim that names one of
# its numbers, whole or by the last digits it holds, or a claim with no number in a reply whose
# earlier clause, one the guard passed, named one; the record backs any claim, as before. Each
# case in English, Saudi Arabic and MSA, by the team's own phrase or a default one (any action).
# «fataHt lak tadhkira 'an SafHat at-taqaareer»: I opened you a ticket about the reports page;
# «laqad fataHtu tadhkiratan li-SafHati at-taqaareer»: I have opened a ticket for the reports
# page (MSA); «fataHt lak at-tadhkira»: I opened you the ticket (the team's own).
NO_NUMBER = [
    pytest.param("I've opened a ticket for your reports page.", "en", id="default_english"),
    pytest.param("Ticket opened for your reports page.", "en", id="own_english"),
    pytest.param("فتحت لك تذكرة عن صفحة التقارير.", "ar", id="default_saudi"),
    pytest.param("فتحت لك التذكرة.", "ar", id="own_saudi"),
    pytest.param("لقد فتحت تذكرة لصفحة التقارير.", "ar", id="default_msa"),
]
# The same claims naming a number: {} is the number, as the status holds it or another.
NAMED = [
    pytest.param("I've opened your ticket {}.", "en", id="default_english"),
    pytest.param("Ticket opened, its number is {}.", "en", id="own_english"),
    pytest.param("فتحت لك تذكرة رقمها {}.", "ar", id="default_saudi"),
    pytest.param("فتحت لك التذكرة اللي تنتهي بـ {}.", "ar", id="own_saudi"),
    pytest.param("لقد فتحت تذكرة رقمها {}.", "ar", id="default_msa"),
]
# A clause that names the ticket's number and claims nothing, said earlier in the same reply:
# «tadhkirtak illi tintihi bi-{} maftooHa», your ticket ending {} is open (Saudi); «tadhkiratuka
# allati tantahi bi-{} maftooHa» (MSA).
SAID_FIRST = {
    "en": "Your ticket ending {} is open.",
    "ar": "تذكرتك اللي تنتهي بـ {} مفتوحة.",
}
MSA_SAID_FIRST = "تذكرتك التي تنتهي بـ {} مفتوحة."


@pytest.mark.parametrize(("clause", "code"), NO_NUMBER)
def test_a_status_alone_backs_no_claim_that_names_no_number(
    clause: str, code: LanguageCode
) -> None:
    """The TD-144 scenario: a status of an older ticket, then a claim of a new one with no
    action called. The record backs the same claim, with no number, as before."""
    for status in (_status(WHOLE_STATUS), _status(FOUR_STATUS)):
        verdict = _check(clause, status, code=code)
        assert verdict.passed is False and verdict.unsupported == ()
    assert _check(clause, MADE, code=code).passed


@pytest.mark.parametrize(("clause", "code"), NAMED)
def test_a_status_backs_a_claim_that_names_its_number_whole_or_its_last_four(
    clause: str, code: LanguageCode
) -> None:
    whole = _check(clause.format(TICKET), _status(WHOLE_STATUS), code=code)
    four = _check(clause.format(LAST_FOUR), _status(FOUR_STATUS), code=code)
    assert whole.passed and four.passed
    assert whole.claimed == four.claimed == ("create_ticket",)


@pytest.mark.parametrize(("clause", "code"), NAMED)
def test_a_claim_naming_another_number_than_the_status_holds_is_blocked(
    clause: str, code: LanguageCode
) -> None:
    for status in (_status(WHOLE_STATUS), _status(FOUR_STATUS)):
        verdict = _check(clause.format("5521"), status, code=code)
        assert verdict.passed is False and verdict.unsupported == ("5521",)
    # Its last four digits are no number of a status holding the whole one: only its own texts,
    # read as rule B reads them, back a claim.
    assert not _check(clause.format(TICKET[-4:]), _status(WHOLE_STATUS), code=code).passed


@pytest.mark.parametrize(("clause", "code"), NO_NUMBER)
def test_a_claim_with_no_number_passes_once_its_reply_named_a_status_number(
    clause: str, code: LanguageCode
) -> None:
    said = (MSA_SAID_FIRST if "لقد" in clause else SAID_FIRST[code]).format(LAST_FOUR)
    status = _status(FOUR_STATUS)
    assert _check(clause, status, code=code, earlier=(said,)).passed
    # Earlier clauses that named no number of this status's, or none: no backing.
    other = (SAID_FIRST[code].format("5521"), "Sure, one moment.")
    assert _check(clause, status, code=code, earlier=other).passed is False
    # A clause that names a number is read by its own: one the reply said before backs no other.
    assert not _check(f"{clause.rstrip('.')} 5521.", status, code=code, earlier=(said,)).passed


def test_a_later_sentence_of_a_status_answer_passes_and_alone_is_blocked() -> None:
    """The accepted cost: "It has been escalated" passes after the sentence that named the
    ticket's digits, and is blocked in a later reply that named none (the guard's fixed phrase
    said instead)."""
    status = _status(FOUR_STATUS, action="hand_off")
    said = SAID_FIRST["en"].format(LAST_FOUR)
    escalated = "It has been escalated to the network team."
    assert _check(escalated, status, earlier=(said,)) == ClaimVerdict(
        claimed=("hand_off",), passed=True
    )
    assert _check(escalated, status) == ClaimVerdict(claimed=(), passed=False)
    # «wa-tamma taS'eed Talabak li-fareeq ash-shabakaat»: and your request was escalated to the
    # network team.
    arabic = "وتم تصعيد طلبك لفريق الشبكات."
    assert _check(arabic, status, code="ar", earlier=(SAID_FIRST["ar"].format(LAST_FOUR),)).passed
    assert not _check(arabic, status, code="ar").passed


def test_a_default_phrase_stands_for_each_action_that_backs_it() -> None:
    """The record backs its action with no number; a status-only action joins only when the
    clause or its reply named one of its numbers."""
    reported = _status(FOUR_STATUS, action="hand_off")
    claim = "I've opened a ticket for your reports page."
    assert _check(claim, MADE, reported).claimed == ("create_ticket",)
    named = _check(f"I've opened a ticket ending {LAST_FOUR} for you.", MADE, reported)
    assert named == ClaimVerdict(claimed=("create_ticket", "hand_off"), passed=True)
    said = (SAID_FIRST["en"].format(LAST_FOUR),)
    assert _check(claim, MADE, reported, earlier=said).claimed == ("create_ticket", "hand_off")


def test_the_settings_phrases_claim_any_action_on_the_same_terms() -> None:
    """`guard.claims`, as Ole5's «رقم تذكرتك» and "your ticket number is" (raqm tadhkirtak, your
    ticket's number): a status backs the number it holds, and no other."""
    added = ("your ticket number is", "رقم تذكرتك")
    status = _status(FOUR_STATUS)
    written: tuple[tuple[str, LanguageCode], ...] = (
        ("Your ticket number is {}.", "en"),
        ("رقم تذكرتك {}.", "ar"),
    )
    for clause, code in written:
        assert _check(clause.format(LAST_FOUR), status, code=code, added=added).passed
        held = _check(clause.format("5521"), status, code=code, added=added)
        assert held == ClaimVerdict(claimed=(), passed=False, unsupported=("5521",))


def test_a_record_and_a_status_of_one_action_back_its_claims_as_the_record_does() -> None:
    """An action done in this call is backed by its record, whatever a status says of it: the
    numbers of a claim about it are read against both."""
    status = _status(FOUR_STATUS)
    assert _check("I've opened a ticket for your reports page.", MADE, status).passed
    assert _check(f"I've opened your ticket ending {LAST_FOUR}.", MADE, status).passed
    assert _check(f"I've opened your ticket {TICKET}.", MADE, status).passed
    assert not _check("I've opened your ticket 5521.", MADE, status).passed


def test_a_clause_with_no_claim_phrase_passes_whatever_it_holds() -> None:
    """Its numbers are rule B's (domain/guard_ids.py)."""
    verdict = _check(f"The reference in the article is {FAKE}.")
    assert verdict == ClaimVerdict(claimed=(), passed=True)
    assert _check("To open a ticket, call the support line.").passed
    assert _check("إذا تبي ترسل مراسلة، اضغط إرسال.", code="ar").passed


def test_a_declared_pattern_in_a_claim_needs_the_actions_evidence() -> None:
    settings = GuardSettings(id_patterns=(r"LT-\d{5}",))
    issued = ActionEvidence(action="create_ticket", texts=("LT-00423",))
    clause = "I've registered LT-00423 for you."
    assert _check(clause, issued, settings=settings).passed
    assert "00423" in _check(clause, MADE, settings=settings).unsupported


@pytest.mark.parametrize(
    ("result", "held"),
    [
        ('{"tickets": [{"ends_in": "4417", "opened_on": "2025-11-02"}], "total": 1}', True),
        ('{"tickets": [], "total": 0, "asked_ends_in": null, "note": "None ends in it."}', False),
        ('{"state": "none", "opened_on": "2026-11-10", "count": 12}', False),
    ],
    ids=["a_ticket", "found_nothing", "a_date_and_a_count"],
)
def test_a_status_result_backs_a_claim_only_when_it_holds_an_id(result: str, held: bool) -> None:
    """A status that found nothing holds no record of the action (invariant 2); this year and
    the parts of a date are no ID, as in rule B."""
    assert holds_an_id([result], settings=SETTINGS, year=2026) is held


def test_the_phrases_that_claim_any_action_are_every_languages() -> None:
    found = any_action_claims({"en": ("all sorted",)})
    assert set(found) == {*default_claims("ar"), *default_claims("en"), "all sorted"}
    assert len(set(found)) == len(found)


def test_the_defaults_are_written_in_the_guards_form_each_once() -> None:
    codes: tuple[LanguageCode, ...] = ("ar", "en")
    for code in codes:
        phrases = default_claims(code)
        assert phrases and all(phrase == guard_form(phrase) for phrase in phrases)
        assert len(set(phrases)) == len(phrases)


# The owner's live call `_Hdmiy0vDE` (2026-11-12): asked "did you open the ticket?" with none
# made, the true answer «ما فتحت لك التذكرة» (ma fatah-t lak at-tadhkara, I did not open the
# ticket for you) was held back twice. A negated phrase claims nothing (D-089); every form that
# says it was done still needs its evidence.
@pytest.mark.parametrize(
    "clause",
    [
        "لا، ما فتحت لك التذكرة لأنك ما أكدت.",  # la, ma fatah-t lak ..., no, I did not open it
        "وما فتحت لك التذكرة للحين.",  # wa-ma ..., and I have not opened it yet
        "مب فتحت لك التذكرة.",  # mub ..., I did not open it
        "ما تم فتح طلب لك.",  # ma tamma fath talab, no request was opened (a default phrase)
    ],
)
def test_a_negated_claim_passes_with_no_evidence(clause: str) -> None:
    assert _check(clause, code="ar").passed


@pytest.mark.parametrize(
    "clause",
    [
        "بعد ما فتحت لك التذكرة بيوصلك إيميل.",  # ba'd ma ..., after I opened it, an email comes
        "أول ما فتحت لك التذكرة وصلك رقمها.",  # awwal ma ..., as soon as I opened it
        "ما فتحت لك التذكرة إلا بعد ما أكدت.",  # ma ... illa ..., I opened it only after you said
        "ما فتحت لك التذكرة غير وحدة.",  # ma ... ghair wahda, I opened only one
        "ما فتحت لك التذكرة؟",  # didn't I open the ticket for you?
        "ما فتحت لك التذكرة، بس فتحت لك التذكرة الثانية.",  # not that one, but the second one
        "فتحت لك التذكرة.",  # I opened the ticket for you
    ],
)
def test_a_claim_said_otherwise_than_negated_is_still_blocked(clause: str) -> None:
    verdict = _check(clause, code="ar")
    assert not verdict.passed and verdict.claimed == ("create_ticket",)
