"""`poe eval-talker` (talker_run.py), run K, on fakes only: each variant measured once through
the call factory, scored, written as it finishes; the scorecard and a history line per session;
held-out read only as aggregates; the smoke test first; the cap and the day's limit stopping a
run, which `--resume` goes on with; failures counted apart (plan 006's registration, K)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ole5_voice.evals import talker_run
from ole5_voice.evals.run_folder import RESULTS_FILE, SESSIONS_FILE
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.talker_lines import TalkerLine
from ole5_voice.evals.talker_score import TalkerScorecard
from t2_agentic_voice import ProviderError

from tests.ole5_voice.evals.talker_fakes import JUDGE, TALKER, Scripted, passage
from tests.ole5_voice.evals.talker_support import Setup, make_setup

DEV = ("--split", "dev", "--call-language", "variant")


def _card(setup: Setup, name: str = "k1-a") -> TalkerScorecard:
    return TalkerScorecard.model_validate_json((setup.out(name) / SCORECARD_FILE).read_bytes())


def _saudi(setup: Setup) -> None:
    """Each Saudi variant's reply in Saudi Arabic, and the `none` item judged honest."""
    for item_id in ("a1", "a2", "n1", "h1", "h2", "h3"):
        setup.calls.script[f"كيف أطبع؟ {item_id}"] = Scripted(language="ar-SA")
    setup.chat.verdicts["n1"] = "not_in_knowledge"
    setup.chat.verdicts["h3"] = "right"


@pytest.fixture
def setup(tmp_path: Path) -> Setup:
    found = make_setup(tmp_path)
    _saudi(found)
    return found


def test_a_dev_run_measures_each_variant_once_and_writes_what_it_found(setup: Setup) -> None:
    setup.calls.script["كيف أطبع؟ a1"] = Scripted(language="en", search=False)
    setup.calls.script["كيف أطبع؟ n1"] = Scripted(language="ar-SA", search=False)
    code = talker_run.main([*setup.argv(), *DEV], parts=setup.parts())
    assert code == 0
    card = _card(setup)
    assert card.complete and card.stopped is None and card.run.split == "dev"
    by_key = {(r.item, r.variant): r for r in card.variants}
    assert sorted(by_key) == [(i, v) for i in ("a1", "a2", "n1") for v in ("v1", "v2")]
    # The smoke test's call, then one call a variant, each in its words' language.
    assert len(setup.calls.said) == 7
    assert [said[3] for said in setup.calls.said[1:3]] == ["en", "ar-SA"]
    a1, a1_saudi, a2 = by_key["a1", "v1"], by_key["a1", "v2"], by_key["a2", "v1"]
    assert a1.own_hit is True and a1.raw_hit is True and a1.passed is True
    assert a2.own_hit is False and a2.raw_hit is False  # point 1 found, point 2 expected
    assert a1_saudi.own_hit is False and a1_saudi.search_right is False  # it never searched
    assert a1_saudi.language_right is False  # an English reply to Saudi words
    assert by_key["n1", "v1"].passed is True and by_key["n1", "v1"].raw_passages is None
    assert by_key["n1", "v2"].search_right is False
    assert card.totals.verdicts["not_in_knowledge"] == 2 and card.totals.failures == 0
    assert card.targets["guard"] is True and card.targets["honest"] is True
    assert card.totals.retrieval is not None and card.totals.retrieval.hits == 1
    # Each record as it finished, the sessions, and the line in both places.
    lines = (setup.out() / RESULTS_FILE).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 6 and json.loads(lines[0])["item"] == "a1"
    assert len((setup.out() / SESSIONS_FILE).read_text(encoding="utf-8").splitlines()) == 1
    ((first, shared), (second, copied)) = setup.lines.lines
    assert first == second and isinstance(first, TalkerLine)
    assert shared == setup.data / "history.jsonl" and copied == setup.out() / "history.jsonl"
    assert first.requests == {TALKER: 7, JUDGE: 7} and first.session == 1 and first.complete
    assert first.cost_usd == pytest.approx(card.cost_usd) and first.cost_usd > 0
    assert setup.chat.closed and setup.kb.closed


def test_every_call_is_held_in_the_agents_first_language_when_asked(setup: Setup) -> None:
    argv = [*setup.argv(), "--split", "dev", "--call-language", "first"]
    assert talker_run.main(argv, parts=setup.parts()) == 0
    assert {said[3] for said in setup.calls.said} == {"ar-SA"}


def test_a_held_out_run_keeps_aggregates_only(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [*setup.argv(out="k1-h"), "--split", "held-out", "--call-language", "variant"]
    assert talker_run.main(argv, parts=setup.parts()) == 0
    card = _card(setup, "k1-h")
    assert card.complete and card.variants == () and card.totals.variants == 6
    assert set(card.breakdowns["kind"]) == {"other"}  # two answerable, one small talk: pooled
    assert not (setup.out("k1-h") / RESULTS_FILE).exists()
    # The smoke test is a dev variant; every other call is a held-out one's.
    assert setup.calls.said[0][0].endswith("a1") and setup.calls.said[1][0].endswith("h1")
    logged = capsys.readouterr().out
    assert "h1" not in logged and "variant_done" in logged


def test_a_smoke_test_that_fails_stops_the_run_before_any_variant(setup: Setup) -> None:
    setup.calls.script["How do I print? a1"] = Scripted(error=ProviderError("server_error", True))
    assert talker_run.main([*setup.argv(), *DEV], parts=setup.parts()) == 1
    card = _card(setup)
    assert card.stopped == "smoke_failed" and not card.complete and card.variants == ()
    assert len(setup.calls.said) == 1 and len(setup.lines.lines) == 2


def test_a_smoke_test_with_a_retried_request_fails(setup: Setup) -> None:
    setup.chat.errors = [ProviderError("rate_limited", True, 1.5)]
    assert talker_run.main([*setup.argv(), *DEV], parts=setup.parts()) == 1
    assert _card(setup).stopped == "smoke_failed"
    assert 1.5 in setup.clock.pauses  # the 429's own retry-after


def test_the_smoke_test_alone(setup: Setup) -> None:
    assert talker_run.main([*setup.argv(), *DEV, "--smoke-only"], parts=setup.parts()) == 0
    card = _card(setup)
    assert card.complete and [(r.item, r.variant) for r in card.variants] == [("a1", "v1")]


def test_the_cap_stops_a_run_that_writes_what_it_measured(setup: Setup) -> None:
    setup.chat.input_tokens = 2000  # each request costs about a third of its budget
    assert talker_run.main([*setup.argv(cap="0.012"), *DEV], parts=setup.parts()) == 1
    card = _card(setup)
    assert card.stopped == "cap" and not card.complete
    assert 0 < len(card.variants) < 6
    assert card.cost_usd <= 0.012


def test_the_days_limit_stops_a_run_which_resume_goes_on_with(setup: Setup) -> None:
    setup.today[TALKER] = 995  # room for the smoke test and four variants' talker requests
    assert talker_run.main([*setup.argv(), *DEV], parts=setup.parts()) == 1
    first = _card(setup)
    assert first.stopped == "daily_limit" and len(first.variants) == 4
    setup.today[TALKER] = 0  # the next day
    assert talker_run.main([*setup.argv(), *DEV, "--resume"], parts=setup.parts()) == 0
    card = _card(setup)
    assert card.complete and len(card.variants) == 6 and len(card.sessions) == 2
    assert card.cost_usd == pytest.approx(sum(s.cost_usd for s in card.sessions))
    lines = [line for line, path in setup.lines.lines if path.name == "history.jsonl"]
    assert [line.session for line in lines[::2]] == [1, 2]  # type: ignore[attr-defined]
    # The first session's fifth variant was refused; the second measured the two left.
    assert len(setup.calls.said) == (1 + 4 + 1) + (1 + 2)


def test_failures_are_counted_apart(setup: Setup) -> None:
    setup.calls.script["How do I print? a1"] = Scripted()
    setup.calls.script["كيف أطبع؟ a1"] = Scripted(error=ProviderError("timeout", True))
    setup.kb.failing.add("How do I print? a2")
    setup.chat.verdicts["n1"] = "right"  # not a verdict a `none` item takes: the judge failed
    setup.calls.script["كيف أطبع؟ a2"] = Scripted(delay_s=0.5)
    argv = [*setup.argv(), *DEV, "--variant-timeout-s", "0.05"]
    assert talker_run.main(argv, parts=setup.parts()) == 0
    by_key = {(r.item, r.variant): r for r in _card(setup).variants}
    assert by_key["a1", "v2"].failure == "provider" and by_key["a1", "v2"].turn is None
    assert by_key["a2", "v1"].failure == "provider" and by_key["a2", "v1"].searches[0].failed
    assert by_key["a2", "v2"].failure == "stuck"
    assert by_key["n1", "v1"].failure == "judge"
    assert _card(setup).totals.failures == 5


def test_a_failed_reference_search_is_a_provider_failure(setup: Setup) -> None:
    setup.calls.script["How do I print? a2"] = Scripted(search=False)
    setup.kb.failing.add("How do I print? a2")
    assert talker_run.main([*setup.argv(), *DEV], parts=setup.parts()) == 0
    by_key = {(r.item, r.variant): r for r in _card(setup).variants}
    assert by_key["a2", "v1"].failure == "provider" and by_key["a2", "v1"].searches == ()


def test_a_violation_of_the_guard_is_counted_and_fails_its_target(setup: Setup) -> None:
    setup.calls.script["How do I print? a2"] = Scripted(violations=1, blocked=2)
    assert talker_run.main([*setup.argv(), *DEV], parts=setup.parts()) == 0
    card = _card(setup)
    assert card.totals.violations == 1 and card.totals.blocked == 2
    assert card.targets["guard"] is False


def test_an_interrupt_keeps_what_was_measured(setup: Setup) -> None:
    setup.calls.script["كيف أطبع؟ a2"] = Scripted(error=KeyboardInterrupt())
    assert talker_run.main([*setup.argv(), *DEV], parts=setup.parts()) == 1
    card = _card(setup)
    assert card.stopped == "interrupted" and len(card.variants) == 3


def test_an_error_the_run_does_not_score_is_raised_once_its_scorecard_is_written(
    setup: Setup,
) -> None:
    setup.calls.script["كيف أطبع؟ a2"] = Scripted(error=RuntimeError("made up"))
    with pytest.raises(RuntimeError, match="made up"):
        talker_run.main([*setup.argv(), *DEV], parts=setup.parts())
    assert _card(setup).stopped == "error"


def test_a_held_out_run_that_does_not_finish_keeps_no_result(setup: Setup) -> None:
    setup.calls.script["كيف أطبع؟ h2"] = Scripted(error=KeyboardInterrupt())
    argv = [*setup.argv(out="k1-h"), "--split", "held-out", "--call-language", "variant"]
    assert talker_run.main(argv, parts=setup.parts()) == 1
    card = _card(setup, "k1-h")
    assert card.totals.variants == 0 and not card.complete


def test_the_talkers_first_query_gives_retrieval(setup: Setup) -> None:
    setup.kb.found["How do I print? a2"] = [
        passage(5),
        passage(4),
        passage(3),
        passage(9),
        passage(2),
    ]
    assert talker_run.main([*setup.argv(), *DEV], parts=setup.parts()) == 0
    a2 = {(r.item, r.variant): r for r in _card(setup).variants}["a2", "v1"]
    # The fifth passage is the expected point; a passage points.toml does not hold is a miss.
    assert a2.own_hit is True and a2.searches[0].passages[3].endswith("chunk_009")
    limits = [limit for query, _, limit in setup.kb.searches if query.endswith("a2")]
    assert set(limits) == {5}  # the tool's 3 asked as 5, and the reference search's 5


def test_a_stop_the_talker_swallowed_still_stops_the_run(setup: Setup) -> None:
    setup.today[TALKER] = 997  # the smoke test and two variants, then a refusal
    setup.calls.script["كيف أطبع؟ a2"] = Scripted(swallows=True)
    setup.calls.script["How do I print? a2"] = Scripted(swallows=True)
    assert talker_run.main([*setup.argv(), *DEV], parts=setup.parts()) == 1
    card = _card(setup)
    assert card.stopped == "daily_limit" and len(card.variants) == 2


def test_a_judge_whose_provider_fails_gives_a_judge_failure(setup: Setup) -> None:
    setup.chat.judge_fails_at = {2}  # the first variant's verdict; the smoke test's passes
    assert talker_run.main([*setup.argv(), *DEV], parts=setup.parts()) == 0
    first = _card(setup).variants[0]
    assert first.failure == "judge" and first.judged is not None and first.judged.verdict is None
    setup.chat.judge_fails_at, setup.chat.judged = {1}, 0  # the smoke test's own
    assert talker_run.main([*setup.argv(out="k1-b"), *DEV], parts=setup.parts()) == 1
    assert _card(setup, "k1-b").stopped == "smoke_failed"


def test_the_judge_is_never_the_talkers_model(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [*setup.argv(), *DEV]
    argv[argv.index("--judge-model") + 1] = TALKER
    with pytest.raises(SystemExit):
        talker_run.main(argv, parts=setup.parts())
    assert "--judge-model is a model other than the talker's" in capsys.readouterr().err


def test_a_model_request_the_talker_caught_still_fails_its_variant(setup: Setup) -> None:
    setup.calls.script["How do I print? a1"] = Scripted(swallows=True)
    setup.chat.fails_at = {3}  # the first variant's talker request, after the smoke test's two
    assert talker_run.main([*setup.argv(), *DEV], parts=setup.parts()) == 0
    first = _card(setup).variants[0]
    assert first.failure == "provider" and first.turn is not None and first.judged is None
