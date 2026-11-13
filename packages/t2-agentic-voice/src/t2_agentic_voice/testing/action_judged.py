"""`ActionSafetySuite`'s cases of an answer the yes rule's lists leave unplaced, which a chat model
judges for an agent that asks (`VoiceAgent.ask_on_unlisted_answers`; D-082): the rails that keep
the model's word from ever standing alone. Each is a `TextCall` of the team's agent whose fake
model (testing/action_scenes.py) answers the check with the word the case names, whatever the
words: a yes beside a change marker is a correction; a yes beside a no word, or a go-ahead with
a question mark, is asked again; a check that fails or times out on a go-ahead is asked again
(on words with a no word it is declined, D-082); a yes over the closing question with no send
word is asked again; the closing question heard back as it plays, judged a go-ahead, confirms
nothing (the echo rail, the owner's third ruling); and an unlisted yes said once the question
ended confirms, once. Two more are said in the agent's other language than the read-back's, as a
call that classifies each turn's language hears them (plan 007's Block H; the text call names
the language, testing/text_side.py's `heard_in`): a yes beside a change marker is a correction,
and a no word beside a go-ahead is asked again, never a yes, since the rails read every
language's no words and change markers. Each ends with the call's checks clean, and
passes at once for an agent that does not ask (the two in another language, for an agent of one
language too), so every team's suite holds them.

The caller's lines are the owner's ruling's kinds, in the call's language (`JUDGED`), each with
a word on none of the lists, or send words among fillers, so the lists leave it unplaced.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import ConfirmationAnswered, ConfirmationDecision
from t2_agentic_voice.core.settings.words import LanguageCode, primary_code
from t2_agentic_voice.domain.consent_check import TIMEOUT_S
from t2_agentic_voice.domain.interruption_words import QUESTION_MARKS
from t2_agentic_voice.testing.action_scenes import SETTLE_S, Scene, check, clean
from t2_agentic_voice.testing.llm_fakes import Pause, ScriptedLLM, ScriptStep
from t2_agentic_voice.testing.text_call import TextCall
from t2_agentic_voice.testing.text_moments import During
from t2_agentic_voice.testing.text_watch import plans_of


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


@dataclass(frozen=True, kw_only=True)
class MixedLines:
    """One language's lines said over a read-back in the agent's other language: a yes with a
    change, and a no word beside a go-ahead."""

    change: str
    refused: str


MIXED: dict[LanguageCode, MixedLines] = {
    "en": MixedLines(change="yes, but change the date", refused="no, send it"),
    "ar": MixedLines(
        # na'am bas ghayyir al-maw'id, yes but change the date: noon, ain, meem; beh, seen;
        # ghain, yeh, shadda, reh; alef, lam, meem, waw, ain, dal
        change=(
            "\u0646\u0639\u0645 \u0628\u0633 "
            "\u063a\u064a\u0651\u0631 \u0627\u0644\u0645\u0648\u0639\u062f"
        ),
        # la arsilha, no, send it: lam, alef; alef with hamza above, reh, seen, lam, heh, alef
        refused="\u0644\u0627 \u0623\u0631\u0633\u0644\u0647\u0627",
    ),
}


def _other(scene: Scene) -> LanguageCode | None:
    """The agent's language other than the call's, which a mixed answer is heard in; None for
    an agent of one language."""
    codes: set[LanguageCode] = {primary_code(each.tag) for each in scene.agent.languages}
    others = sorted(codes - {scene.code})
    return others[0] if others else None


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

    def test_the_closing_question_heard_back_as_it_plays_confirms_nothing(self) -> None:
        asyncio.run(_echoed(self._scene()))

    def test_an_unlisted_yes_once_the_question_ended_confirms_once(self) -> None:
        scene = self._scene()
        asyncio.run(_answered(scene, JUDGED[scene.code].agreement, _word("yes"), "yes"))

    def test_a_yes_with_a_change_in_another_language_is_a_correction(self) -> None:
        scene = self._scene()
        other = _other(scene)
        if other is not None:
            change = MIXED[other].change
            asyncio.run(_answered(scene, change, _word("yes"), "correction", heard_in=other))

    def test_a_no_word_in_another_language_is_never_a_yes(self) -> None:
        scene = self._scene()
        other = _other(scene)
        if other is not None:
            refused = MIXED[other].refused
            asyncio.run(_answered(scene, refused, _word("yes"), "asked_again", heard_in=other))


async def _echoed(scene: Scene) -> None:
    """The caller asks for the action; over its closing question the question's own words are
    heard back, its question marks dropped, and the check answers `send`: the echo rail keeps
    any yes from them, and nothing is written."""
    if not scene.asks:
        return
    agent = scene.with_action(scene.writes.counted())
    model = scene.model({scene.request: scene.call_action()}, judged=_word("send"))
    async with TextCall(agent, llm=model, language=scene.tag, caller=scene.caller) as call:
        await call.user(scene.request)
        plans = plans_of(call._reads().watched)
        check(bool(plans), "the action was never read back")
        question = plans[-1].question.text
        heard = "".join(mark for mark in question if mark not in QUESTION_MARKS).strip()
        echo = await call.user(heard, during="closing_question")
        await call.advance(SETTLE_S)
        found = [
            e.decision
            for e in call._emitted
            if isinstance(e, ConfirmationAnswered) and e.turn_id == echo.turn_id
        ]
        check("yes" not in found, f"the closing question heard back was answered {found}")
        echo.expect.no_action()
        check(scene.writes.made == 0, "the closing question heard back wrote")
        clean(call)


async def _answered(
    scene: Scene,
    words: str,
    judged: tuple[ScriptStep, ...],
    decision: ConfirmationDecision,
    *,
    during: During | None = None,
    heard_in: LanguageCode | None = None,
) -> None:
    """The caller asks for the action, then answers its read-back with `words` (once it played
    whole, or `during` its closing question), heard in `heard_in` (the call's language unless
    given), the check answered `judged`: the answer is `decision`, by the model, and the action
    is written once for a yes, never otherwise."""
    if not scene.asks:
        return
    agent = scene.with_action(scene.writes.counted())
    model = scene.model({scene.request: scene.call_action()}, judged=judged)
    async with TextCall(agent, llm=model, language=scene.tag, caller=scene.caller) as call:
        await call.user(scene.request)
        if during is None:
            await call.advance(SETTLE_S)
        call._parts()[0].heard_in = heard_in
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
