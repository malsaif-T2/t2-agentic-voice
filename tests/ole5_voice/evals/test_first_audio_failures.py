"""`poe first-audio` stopped by a failure once it started (plan 006's registration, T): a
progress line the voice failed at the replay's start, a library error mid-run, and a bug, each
with what was measured kept, its scorecard and history line written, every request counted."""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.evals import first_audio
from ole5_voice.evals.measure_lines import FirstAudioLine
from t2_agentic_voice import ProviderError, T2VoiceError

from tests.ole5_voice.evals.first_audio_support import call, t_run


def test_a_progress_line_the_voice_failed_at_the_start_stops_the_run_with_its_card(
    tmp_path: Path,
) -> None:
    run = t_run(tmp_path)

    async def failing() -> None:
        raise ProviderError("timeout", True)

    run.replay.start = failing  # type: ignore[method-assign]
    assert first_audio.main(run.argv(), parts=run.parts()) == 1
    assert run.card().stopped == "phrases_failed" and run.replay.asked == []
    assert len(run.lines.appended) == 2 and run.replay.closed == 1


def test_a_library_error_mid_run_keeps_what_was_measured_its_card_and_line_written(
    tmp_path: Path,
) -> None:
    run = t_run(tmp_path, call(), call(), T2VoiceError("Something the run did not expect."))
    assert first_audio.main(run.argv(), parts=run.parts()) == 1
    card = run.card()
    assert card.stopped == "error" and len(card.variants) == 1 and not card.complete
    (line, _), _ = run.lines.appended
    assert isinstance(line, FirstAudioLine) and line.cost_usd == card.cost_usd > 0
    assert run.replay.closed == 1 and run.stt.closed and run.tts.closed


def test_a_bug_mid_run_is_raised_once_its_card_and_line_are_written(tmp_path: Path) -> None:
    run = t_run(tmp_path, call(), RuntimeError("a bug"))
    with pytest.raises(RuntimeError, match="a bug"):
        first_audio.main(run.argv(), parts=run.parts())
    assert run.card().stopped == "error" and len(run.lines.appended) == 2
