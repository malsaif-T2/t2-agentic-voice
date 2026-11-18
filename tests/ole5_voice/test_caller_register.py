"""Ole5 reads the register of a caller's Arabic as it did (GP-18): its settings leave the library's
`words.saudi_first` off and add no Saudi form (`words.dialect`), so a turn with no form of the
library's list is MSA, the flight app's forms among them, and one with a form is Saudi. Every
sentence is written for the test."""

from __future__ import annotations

import pytest
from ole5_voice.settings import load
from t2_agentic_voice.agent.language import call_register


def test_ole5s_settings_read_the_callers_register_as_before(
    environment: pytest.MonkeyPatch,
) -> None:
    words = load().voice.words
    assert (words.saudi_first, words.dialect) == (False, ())
    assert call_register(["السلام عليكم"], words) == "msa"
    assert call_register(["شوف يا طويل العمر، ودي أطبع الملف"], words) == "msa"
    assert call_register(["أبي أطبع الملف"], words) == "saudi"
    assert call_register(["كيف أطبع الملف؟", "تمام"], words) == "msa"
