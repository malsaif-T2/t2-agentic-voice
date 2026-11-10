"""`ActionSafetySuite`'s cases of an answer the yes rule's lists leave unplaced, which a chat model
judges for an agent that asks (`VoiceAgent.ask_on_unlisted_answers`; D-082): the rails that keep
the model's word from ever standing alone. Each is a `TextCall` of the team's agent whose fake
model (testing/action_scenes.py) answers the check with the word the case names, whatever the
words: a yes beside a change marker is a correction; a yes beside a no word, or a go-ahead with
a question mark, is asked again; a check that fails or times out is asked again; a yes over the
closing question with no send word is asked again; and an unlisted yes said once the question
ended confirms, once. Each ends with the call's checks clean, and passes at once for an agent
that does not ask, so every team's suite holds them.

The caller's lines are the owner's ruling's kinds, in the call's language (`JUDGED`), each with
a word on none of the lists, or send words among fillers, so the lists leave it unplaced.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import ConfirmationAnswered, ConfirmationDecision
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.consent_check import TIMEOUT_S
from t2_agentic_voice.testing.action_scenes import SETTLE_S, Scene, check, clean
from t2_agentic_voice.testing.llm_fakes import Pause, ScriptedLLM, ScriptStep
from t2_agentic_voice.testing.text_call import TextCall
from t2_agentic_voice.testing.text_moments import During


@dataclass(frozen=True, kw_only=True)
class JudgedLines:
    """One language's lines for the judged cases: a yes with a change, a yes with a no word, a
    go-ahead asked back, a go-ahead, and plain agreement."""

    change: str
    refused: str
    asked: str
    go_ahead: str
    agreement: str


JUDGED: dict[LanguageCode, JudgedLines] = {
    "en": JudgedLines(
        change="yes, but make it urgent",
        refused="yes, not like that",
        asked="go for it?",
        go_ahead="go for it",
        agreement="sure thing",
    ),
    "ar": JudgedLines(
        # eeh bas khalliha 'aajla, yes but make it urgent: alef, yeh, heh; beh, seen; khah, lam,
        # heh, alef; ain, alef, jeem, lam, teh marbuta
        change=("ايه بس خلها عاجلة"),
        # eeh mu kitha, yes, not like that: alef, yeh, heh; meem, waw; kaf, thal, alef
        refused="ايه مو كذا",
        # tawakkal ya ghaali?, go ahead, dear?: teh, waw, kaf, lam; yeh, alef; ghain, alef,
        # lam, yeh; the Arabic question mark
        asked="توكل يا غالي؟",
        # yalla arsilha, come on, send it: yeh, lam, alef; alef with hamza, reh, seen, lam,
        # heh, alef
        go_ahead="يلا أرسلها",
        agreement="صح",  # sah, right: sad, hah
    ),
}


def _word(word: str) -> tuple[ScriptStep, ...]:
    return ScriptedLLM.reply(word)


class JudgedAnswerCases:
    """The judged cases (the module's docstring), mixed into `ActionSafetySuite`, which gives
    each its `Scene`."""

    def _scene(self) -> Scene:
        raise NotImplementedError  # ActionSafetySuite's

    def test_a_model_yes_beside_a_change_marker_is_a_correction(self) -> None:
        scene = self._scene()
        lines = JUDGED[scene.code]
        asyncio.run(_answered(scene, lines.change, _word("yes"), "correction"))

    def test_a_model_yes_beside_a_no_word_or_a_question_mark_is_asked_again(self) -> None:
        scene = self._scene()
        lines = JUDGED[scene.code]
        asyncio.run(_answered(scene, lines.refused, _word("yes"), "asked_again"))
        asyncio.run(_answered(self._scene(), lines.asked, _word("send"), "asked_again"))

    def test_a_check_that_fails_or_times_out_is_asked_again(self) -> None:
        failed: tuple[ScriptStep, ...] = (ProviderError("server_error", True),)
        late = (Pause(TIMEOUT_S + 1.0), *_word("send"))
        for steps in (failed, late):
            scene = self._scene()
            asyncio.run(_answered(scene, JUDGED[scene.code].go_ahead, steps, "asked_again"))

    def test_a_model_yes_over_the_closing_question_with_no_send_word_is_asked_again(self) -> None:
        scene = self._scene()
        agreement = JUDGED[scene.code].agreement
        over: During = "closing_question"
        asyncio.run(_answered(scene, agreement, _word("yes"), "asked_again", during=over))

    def test_an_unlisted_yes_once_the_question_ended_confirms_once(self) -> None:
        scene = self._scene()
        asyncio.run(_answered(scene, JUDGED[scene.code].agreement, _word("yes"), "yes"))


async def _answered(
    scene: Scene,
    words: str,
    judged: tuple[ScriptStep, ...],
    decision: ConfirmationDecision,
    *,
    during: During | None = None,
) -> None:
    """The caller asks for the action, then answers its read-back with `words` (once it played
    whole, or `during` its closing question), the check answered `judged`: the answer is
    `decision`, by the model, and the action is written once for a yes, never otherwise."""
    if not scene.asks:
        return
    agent = scene.with_action(scene.writes.counted())
    model = scene.model({scene.request: scene.call_action()}, judged=judged)
    async with TextCall(agent, llm=model, language=scene.tag, caller=scene.caller) as call:
        await call.user(scene.request)
        if during is None:
            await call.advance(SETTLE_S)
        answer = await call.user(words, during=during)
        await call.advance(SETTLE_S)
        found = [
            (e.decision, e.by)
            for e in call._emitted
            if isinstance(e, ConfirmationAnswered) and e.turn_id == answer.turn_id
        ]
        turn = f"turn {answer.turn_id}"
        check(found == [(decision, "model")], f"{turn} was answered {found}, not {decision}")
        if decision == "yes":
            answer.expect.confirmed(scene.action.name, **scene.arguments)
            check(scene.writes.made == 1, f"a judged yes wrote {scene.writes.made} times")
        else:
            answer.expect.no_action()
            check(scene.writes.made == 0, f"{turn}'s {decision} wrote")
        clean(call)
