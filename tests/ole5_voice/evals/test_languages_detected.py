"""`poe eval-languages --classifier detected` (D-038's amendment, run H): a pass under
`stt.live_language = "detected"`, through a fake `turn_languages`, builds no classifier, records
each turn's `detects` (whether it also went naming no language) and the registered
`stt.detect_from_s`; a pass under another length is refused before any clip is fed."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from ole5_voice.evals import languages_setup, run_settings
from ole5_voice.evals.languages_card import TURNS_FILE, LanguagesLine, LanguagesScorecard
from ole5_voice.evals.runs import SCORECARD_FILE
from t2_agentic_voice import ConfigurationError, VoiceSettings
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.evals import LanguageTurn

from tests.ole5_voice.evals.eot_support import Lines
from tests.ole5_voice.evals.languages_support import turn
from tests.ole5_voice.evals.test_languages_run import (
    Classifiers,
    FakeTurnLanguages,
    _argv,
    _main,
    _out,
    _world,
)


def test_a_detected_pass_builds_no_classifier_and_keeps_which_turns_detect(
    tmp_path: Path,
) -> None:
    world, parts = _world(tmp_path)
    script: list[tuple[LanguageTurn, ...]] = [
        (turn("session", detects=n % 2 == 0),) for n in range(4)
    ]
    fake, classifiers, lines = FakeTurnLanguages(script), Classifiers(), Lines()
    assert _main(_argv(world, classifier="detected"), parts, fake, classifiers, lines) == 0
    assert classifiers.settings == [] and fake.asked["classifier"] is None
    assert fake.asked["settings"].stt.live_language == "detected"
    out = _out(world)
    card = LanguagesScorecard.model_validate_json((out / SCORECARD_FILE).read_bytes())
    assert card.run.classifier == "detected" and card.card.by == {"session": 4}
    assert card.run.settings["stt.classifier"] == "none"
    assert card.run.settings["stt.detect_from_s"] == "1.2"
    rows = [json.loads(line) for line in (out / TURNS_FILE).read_text("utf-8").splitlines()]
    assert [row["turns"][0]["detects"] for row in rows] == [True, False, True, False]
    (line, _), _ = lines.appended
    assert isinstance(line, LanguagesLine) and line.classifier == "detected"


def test_a_detected_pass_under_another_length_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded = VoiceSettings(env="test", stt=SttSettings(detect_from_s=2.0))
    monkeypatch.setattr(run_settings, "env_settings", lambda args: loaded)
    args = argparse.Namespace(classifier="detected", classifier_dir=None)
    with pytest.raises(ConfigurationError, match=r"detect_from_s 1.2"):
        languages_setup.settings_of(args)
    registered = loaded.model_copy(update={"stt": SttSettings()})
    monkeypatch.setattr(run_settings, "env_settings", lambda args: registered)
    assert languages_setup.settings_of(args).stt.live_language == "detected"
