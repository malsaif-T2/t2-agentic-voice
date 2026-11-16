"""A run's folder and what runs K and S read of the shared history (run_folder.py): the run, its
results and sessions written and read back strictly, a resume only of the same run, the day's
requests counted from the history and every other app's, and the history's kinds checked before
a line is added."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ole5_voice.evals.history import read_history
from ole5_voice.evals.run_folder import (
    RUN_FILE,
    RunFolder,
    append_shared,
    folder_for,
    history_accepts,
    requests_today,
)
from ole5_voice.evals.run_lines import TimingLine
from ole5_voice.evals.scorecard import EvalDataError
from ole5_voice.evals.talker_data import TalkerDataError
from ole5_voice.evals.talker_score import PriceShown, Session, TalkerRun
from t2_agentic_voice import InvalidRequestError
from t2_agentic_voice.evals import inspect_checkout

from tests.ole5_voice.evals.run_support import make_world
from tests.ole5_voice.evals.samples import WHEN

DIGEST = "ab" * 32


def _run(note: str = "why") -> TalkerRun:
    return TalkerRun(
        name="k1-a",
        started_at=WHEN,
        commit="ab" * 20,
        arm="k1",
        model="openai/gpt-oss-120b",
        judge_model="llama-3.3-70b-versatile",
        split="dev",
        settings={"llm.model": "openai/gpt-oss-120b"},
        prices={"openai/gpt-oss-120b": PriceShown(input_usd=0.15, output_usd=0.6)},
        cap_usd=1.0,
        data_digest=DIGEST,
        note=note,
    )


def _timing(day: datetime, requests: dict[str, int]) -> TimingLine:
    return TimingLine(
        time=day,
        commit="ab" * 20,
        run="t1",
        settings={},
        split="dev",
        variants=1,
        cut_variants=0,
        failures=0,
        phrase_requests=0,
        requests=requests,
        characters={},
        billed_seconds=1.0,
        price_per_hour_usd=0.1,
        tts_price_per_million_usd={},
        cost_usd=0.01,
        medians_ms={},
        scorecard="scorecard.json",
        data_digest=DIGEST,
        note="made up",
        complete=True,
    )


def test_a_folder_holds_the_run_its_results_and_sessions(tmp_path: Path) -> None:
    folder = RunFolder(tmp_path / "k1-a")
    folder.begin(_run())
    assert folder.run(TalkerRun) == _run()
    assert folder.results(Session) == [] and folder.sessions(Session) == []
    session = Session(started_at=WHEN, stopped="cap", variants=2)
    folder.add_session(session)
    folder.add_result(session)
    assert folder.sessions(Session) == [session] == folder.results(Session)
    folder.write_scorecard(session)
    assert (folder.out / "scorecard.json").exists()
    assert not list(folder.out.glob(".*partial"))


def test_a_resume_takes_only_the_same_run(tmp_path: Path) -> None:
    folder = RunFolder(tmp_path / "k1-a")
    folder.begin(_run())
    later = _run().model_copy(update={"started_at": datetime(2026, 12, 1, tzinfo=UTC)})
    assert folder.resumed(later) == _run()  # its first start kept
    with pytest.raises(InvalidRequestError, match="differs in note"):
        folder.resumed(_run(note="another"))


def test_a_folders_unreadable_file_is_refused_by_name(tmp_path: Path) -> None:
    folder = RunFolder(tmp_path / "k1-a")
    folder.begin(_run())
    (folder.out / "results.jsonl").write_text('{"started_at": 1}\n', encoding="utf-8")
    with pytest.raises(TalkerDataError, match=r"results\.jsonl, line 1 in the run's folder"):
        folder.results(Session)
    (folder.out / "sessions.jsonl").write_bytes(b"\xff\n")
    with pytest.raises(TalkerDataError, match="cannot be read"):
        folder.sessions(Session)
    (folder.out / RUN_FILE).write_text("{}", encoding="utf-8")
    with pytest.raises(TalkerDataError, match=r"run\.json in the run's folder"):
        folder.run(TalkerRun)


def test_the_folder_of_a_new_run_or_of_a_resumed_one(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    checkout = inspect_checkout(world.top, world.git)
    out = world.main / "var" / "runs" / "k1-a"
    assert folder_for(out, resume=False, checkout=checkout, git=world.git).out == out
    with pytest.raises(InvalidRequestError, match="holds no run"):
        folder_for(out, resume=True, checkout=checkout, git=world.git)
    RunFolder(out).begin(_run())
    assert folder_for(out, resume=True, checkout=checkout, git=world.git).out == out.resolve()
    with pytest.raises(InvalidRequestError, match="is not a name"):
        folder_for(world.main / "var" / "Bad Name", resume=False, checkout=checkout, git=world.git)


def test_the_days_requests_are_counted_from_the_history(tmp_path: Path) -> None:
    history = tmp_path / "history.jsonl"
    assert requests_today(history, date(2026, 11, 7)) == {}
    day = datetime(2026, 11, 7, 9, tzinfo=UTC)
    append_shared(_timing(day, {"whisper-large-v3": 4, "orpheus": 2}), history)
    append_shared(_timing(day, {"whisper-large-v3": 1}), history)
    append_shared(_timing(datetime(2026, 11, 6, 23, tzinfo=UTC), {"whisper-large-v3": 9}), history)
    found = requests_today(history, date(2026, 11, 7))
    assert found == {"whisper-large-v3": 5, "orpheus": 2}
    assert len(read_history(history)) == 3


def test_the_days_requests_are_counted_over_every_apps_history(tmp_path: Path) -> None:
    """The apps spend on one key: Ole5's runs start the day from the flight agent's runs too, and
    the shared history is still read strictly."""
    apps = tmp_path / "apps"
    history = apps / "ole5-voice-agent" / "evals" / "history.jsonl"
    history.parent.mkdir(parents=True)
    append_shared(
        _timing(datetime(2026, 11, 7, 9, tzinfo=UTC), {"openai/gpt-oss-120b": 4}), history
    )
    flights = apps / "flight-voice-agent" / "evals" / "history.jsonl"
    flights.parent.mkdir(parents=True)
    line = '{"kind": "flights", "time": "2026-11-07T11:00:00+00:00", "requests": '
    flights.write_bytes((line + '{"openai/gpt-oss-120b": 30, "judge": 2}}\n').encode())
    found = requests_today(history, date(2026, 11, 7))
    assert found == {"openai/gpt-oss-120b": 34, "judge": 2}
    with history.open("ab") as file:
        file.write(b'{"kind": "flights", "time": "2026-11-07T11:00:00+00:00"}\n')
    with pytest.raises(EvalDataError, match="line 2: not a history line"):
        requests_today(history, date(2026, 11, 7))


def test_the_history_takes_only_its_own_kinds(tmp_path: Path) -> None:
    assert history_accepts(_timing(WHEN, {})) is True
    assert history_accepts(_run()) is False
    with pytest.raises(TalkerDataError, match="takes no such line"):
        append_shared(_run(), tmp_path / "history.jsonl")
    assert not (tmp_path / "history.jsonl").exists()
