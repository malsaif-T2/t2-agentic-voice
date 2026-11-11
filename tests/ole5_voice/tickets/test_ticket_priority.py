"""A ticket's priority in Ole5's calls (the owner's ruling of 2026-11-11: the talker "should
classify it itself and not really communicate it with the user since it is an internal
detail"): the served talker through `TextCall`, as test_ticket_calls.py runs it, its fake model
scripted as the real one now should answer, calling create_ticket at once for a caller who says
only what is wrong, with no word of how urgent it is.

- The read-back plays in answer to that first turn, with nothing asked before it, in the
  caller's register (Saudi Arabic, MSA or English): the type and the summary, and no priority
  or word of one.
- The draft the caller confirms holds the default priority, Medium, and so does the ticket made.
- The model was told so: its instructions say to set the priority itself and never to ask for
  it or say it, and create_ticket's priority, as the model is told of it, says the same.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Final, Literal

import pytest
from ole5_voice.tickets import lines
from ole5_voice.tickets.drafts import PRIORITY_LABELS, TYPE_LABELS
from t2_agentic_voice.evals import ScriptedLLM, is_consent_check
from t2_agentic_voice.languages import normalize_arabic

from tests.ole5_voice.tickets.call_support import (
    SETTLE_S,
    Answer,
    Tag,
    model,
    ole5,
    text_call,
    yes_send,
)
from tests.ole5_voice.tickets.ticket_support import run

Register = Literal["msa", "saudi", "en"]
# The call's tag, and the tag its action's lines are read in, by the caller's register.
CALLED: Final[Mapping[Register, Tag]] = {"msa": "ar-SA", "saudi": "ar-SA", "en": "en"}
WORDING: Final[Mapping[Register, Literal["ar", "ar-SA", "en"]]] = {
    "msa": "ar",
    "saudi": "ar-SA",
    "en": "en",
}
# The caller says only what is wrong: the reports page in Ole5 has shown no data since the
# morning, open me a ticket («...ma tiTla' ayya bayaanaat min aS-SubH, iftaH li tadhkira»;
# «...la ta'riD ayya bayaanaat mundhu aS-SabaaH, arjoo fatH tadhkira»).
REQUEST: Final[Mapping[Register, str]] = {
    "msa": "صفحة التقارير في نظام أوله فايف لا تعرض أي بيانات منذ الصباح، أرجو فتح تذكرة.",
    "saudi": "صفحة التقارير في أوله فايف ما تطلع أي بيانات من الصبح، افتح لي تذكرة.",
    "en": "My Ole5 reports page has shown no data since this morning. Please open a ticket.",
}
SUMMARY: Final[Mapping[Register, str]] = {
    "msa": "صفحة التقارير لا تعرض أي بيانات منذ الصباح.",
    "saudi": "صفحة التقارير ما تعرض أي بيانات من الصبح.",
    "en": "The reports page has shown no data since this morning.",
}
# What says a priority, as a word's part: priority, urgent; awlawiyya (priority), 'aajil
# (urgent) and musta'jil (in a hurry); and every priority's label, as a whole word.
STEMS: Final = tuple(map(normalize_arabic, ("priorit", "urgen", "أولوي", "عاجل", "مستعجل")))
LABELS: Final = {
    normalize_arabic(word) for each in PRIORITY_LABELS.values() for word in each.values()
}


def _words(text: str) -> list[str]:
    return [normalize_arabic(word) for word in re.findall(r"\w+", text.lower())]


def _of_priority(text: str) -> list[str]:
    """The words of `text` that say a priority (`STEMS`, `LABELS`)."""
    return [w for w in _words(text) if w in LABELS or any(stem in w for stem in STEMS)]


@pytest.mark.parametrize("register", ["msa", "saudi", "en"])
def test_a_caller_who_says_only_what_is_wrong_hears_the_read_back_at_once_with_no_priority(
    tmp_path: Path, register: Register
) -> None:
    tag, wording = CALLED[register], WORDING[register]
    agent, tickets = ole5(tmp_path)
    # Straight to create_ticket with no priority: the draft's default is the one sent.
    steps = ScriptedLLM.call_tool("create_ticket", summary=SUMMARY[register], type="Report")
    llm = model(Answer(REQUEST[register], steps))

    async def scene() -> str:
        async with text_call(agent, llm, tag) as call:
            asked = await call.user(REQUEST[register])
            asked.expect.tool_call("create_ticket")
            asked.expect.read_back(contains=SUMMARY[register], priority="Medium")
            heard = " ".join(clause.text for clause in asked.heard())
            await call.advance(SETTLE_S)
            sent = await call.user(yes_send(tag))
            await call.advance(SETTLE_S)
            sent.expect.confirmed("create_ticket", summary=SUMMARY[register], priority="Medium")
            sent.expect.action_completed("create_ticket")
            assert call.violations == ()
            return heard

    heard = run(scene())
    assert _of_priority(heard) == [], heard
    # The first turn's reply is the read-back alone: its summary, then its closing question.
    summary, question = lines.TICKET_READ_BACK.for_language(wording)
    label = TYPE_LABELS["Report"]["en" if tag == "en" else "ar-SA"]
    read_back = summary.format(type=label, summary=SUMMARY[register])
    assert heard == f"{read_back} {question}", heard
    [made] = tickets.listed()
    assert (made.type, made.priority) == ("Report", "Medium")
    # The talker's first request told the model to set the priority itself.
    request = next(each for each in llm.requests if not is_consent_check(each))
    instructed = " ".join(request.messages[0].content.split())
    assert "never ask how urgent it is" in instructed
    assert "Never tell the caller the priority." in instructed
    [create] = [tool for tool in request.tools if tool.name == "create_ticket"]
    assert "never ask for it, and never say it" in json.dumps(create.parameters)
