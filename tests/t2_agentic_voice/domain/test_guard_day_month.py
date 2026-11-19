"""`guard.day_month_apart` (domain/guard_ids.py, D-134): a day and a month alone with one hyphen
between them, the ASCII one or a hyphen a model writes for it, are read as two numbers, not one
ID of their digits; a group of three or more hyphened numbers stays one; off by default, every
reading is as before. The model trial of 2026-11-19 heard a clause blocked for «26\u201111»."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.domain.guard_ids import check_ids

ON = GuardSettings(day_month_apart=True)
EVIDENCE = ("flynas XY 17 429",)


def _passes(clause: str, settings: GuardSettings) -> bool:
    return check_ids(clause, evidence=EVIDENCE, settings=settings, year=2026).passed


@pytest.mark.parametrize(
    "clause",
    [
        "يطلع 26\u201111 الساعة 09:35",  # the non-breaking hyphen of the trial
        "يطلع 26-11 بسعر 429",
        "leaves 11-26 at 09:35",
        "يوم 5\u201312",  # the en dash
    ],
)
def test_a_day_and_a_month_with_a_hyphen_pass_with_the_setting(clause: str) -> None:
    assert _passes(clause, ON)
    assert not _passes(clause, GuardSettings())  # off: one group of their digits, as before


@pytest.mark.parametrize(
    "clause",
    ["التذكرة 45-21-33", "رقم 1234", "القسيمة 12-1310", "الرقم 26-11-77"],
)
def test_ids_still_need_evidence_with_the_setting(clause: str) -> None:
    assert not _passes(clause, ON)


def test_a_full_date_and_a_known_number_pass_either_way() -> None:
    for settings in (ON, GuardSettings()):
        assert _passes("تاريخ 7-11-2026", settings)
        assert _passes("السعر 429", settings)
