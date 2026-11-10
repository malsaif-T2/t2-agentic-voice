"""An action's lines read in the caller's register (actions/spoken_lines.py, action_runner.py,
action_job.py; the owner's ruling of 2026-11-10 on MSA read-backs): `propose` reads the
action's texts in the `wording` the talker gives (agent/language.py's `wording`: `ar`, MSA, for
an `ar-SA` reply to an MSA caller), each line its `ar` text, its `ar-SA` one where it gives
none, as before, and the library's own lines in MSA; the plan keeps the reply's tag and that
wording, and `run`, handed the wording, reads the outcome's line in it too."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from t2_agentic_voice.actions import spoken_lines
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.action_declaration import Say
from t2_agentic_voice.domain.action_lines import ActionLines, default_action_lines

from tests.t2_agentic_voice.actions.action_support import (
    ISSUED,
    SAUDI_AND_MSA,
    SUMMARY,
    Mode,
    Rig,
    confirmed_of,
)

SAUDI_SENDING = Say({"ar-SA": "أفتحه لك الحين.", "en": "Opening it now."})  # aftaHuh lak al-Heen
# "tamm, ar-raqm {number}" and "tamma dhalik, wa-raqmuhu {number}": done, the number is ...
SAUDI_AND_MSA_DONE = Say({"ar-SA": "تم، الرقم {number:id}.", "ar": "تم ذلك، ورقمه {number:id}."})
# "ma gidart aftaH aT-Talab": I couldn't open the request, in Saudi Arabic alone.
SAUDI_FAILED = Say({"ar-SA": "ما قدرت أفتح الطلب.", "en": "I could not open it."})


@pytest.mark.parametrize("wording", ["ar", "ar-SA", None])
def test_a_draft_read_in_msa_is_said_from_the_msa_texts_in_the_replys_own_tag(
    monkeypatch: pytest.MonkeyPatch, wording: LanguageTag | None
) -> None:
    """Read in `ar`: each line from the action's `ar` text, its `ar-SA` one where it gives none
    (`sending` here), and the library's own lines in MSA; the plan keeps the reply's tag, which
    the session speaks in, and the send words of its code. Read in `ar-SA`, or with no wording
    given, it is Saudi, as it was."""
    asked: list[LanguageTag] = []

    def lines(tag: LanguageTag) -> ActionLines:
        asked.append(tag)
        return default_action_lines(tag)

    monkeypatch.setattr(spoken_lines, "default_action_lines", lines)
    rig = Rig(read_back=SAUDI_AND_MSA, sending=SAUDI_SENDING, declined=None)
    plan = asyncio.run(rig.plan("ar-SA", wording=wording))
    read = wording or "ar-SA"
    summary, question = SAUDI_AND_MSA.for_language(read)
    library = default_action_lines(read)
    assert plan.summary.text == summary.format(category="برامج", summary=SUMMARY)
    assert plan.question.text == question and plan.sending.text == "أفتحه لك الحين."
    assert plan.asked_again.text == library.asked_again
    assert plan.declined.text == library.declined and set(asked) == {read}
    assert (plan.language, plan.wording, plan.send_words) == ("ar-SA", read, ("أرسله",))
    assert default_action_lines("ar").asked_again != default_action_lines("ar-SA").asked_again


@pytest.mark.parametrize(
    ("mode", "said"), [("answer", f"تم ذلك، ورقمه {ISSUED}."), ("reject", "ما قدرت أفتح الطلب.")]
)
def test_an_outcome_read_in_msa_is_said_from_the_msa_texts_its_read_back_was_read_in(
    mode: Mode, said: str
) -> None:
    """The wording given at propose, handed on to `run`: `done` from its `ar` text, `failed`
    from its `ar-SA` one, the action giving no other."""
    rig = Rig(mode, done=SAUDI_AND_MSA_DONE, failed=SAUDI_FAILED)

    async def scenario() -> Any:
        plan = await rig.plan("ar-SA", wording="ar")
        return await rig.run(confirmed_of(plan), language="ar-SA", wording=plan.wording)

    assert asyncio.run(scenario()).line.text == said
