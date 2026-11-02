"""Each value the app copies from the library, which no facade exports, is tied here to the
library's own, so a change on one side fails until the other follows: the owner's ruling of
2026-11-02 (plan 004), to tie the copies with tests rather than export them. A test may read the
library's internals; the app's code may not (ARCH-PUBLIC). The provider error kinds are tied in
`test_runs.py`."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import get_args

from ole5_voice.evals import answerers, matcher, run, run_settings, scorecard
from ole5_voice.evals.run_parts import Parts
from ole5_voice.evals.runs import Answer, SegmentAnswer
from pydantic import BaseModel
from t2_agentic_voice import VoiceSettings
from t2_agentic_voice.adapters import groq_stt
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.stt import SttModel, SttProvider
from t2_agentic_voice.domain.scoring import scored_form
from t2_agentic_voice.ports import Transcript

TABLE = Path(__file__).parents[2] / "t2_agentic_voice" / "fixtures"
TABLE /= "arabic_normalizer_characterization.json"
# Texts whose digits the scored form reads, in either language and in every letter form.
DIGITS = ["خمسة سبعة", "خمسه", "٥٧", "۵۷", "Five SEVEN", "تذكرة رقم ثلاثة", "إثنين"]


def test_the_apps_scored_form_is_the_librarys() -> None:
    """`matcher.normalize`, which the verdict, a window's words and a reference's words are
    counted in, is the library's `scored_form`; and it is the one form each of them takes."""
    rows = json.loads(TABLE.read_text(encoding="utf-8"))["rows"]
    texts = [row["input"] for row in rows] + DIGITS
    assert len(texts) > 40
    for text in texts:
        assert matcher.normalize(text) == scored_form(text), text
    assert Parts().normalize is matcher.normalize
    written = inspect.signature(scorecard.write_scorecard).parameters["normalize"].default
    assert written is matcher.normalize


def test_a_runs_models_are_the_ones_the_librarys_settings_take() -> None:
    assert get_args(SttModel) == run_settings.MODELS


def test_a_runs_default_address_is_the_librarys_default_base_url() -> None:
    assert GroqSettings.model_fields["base_url"].default == run_settings.GROQ_BASE_URL


def test_the_answerers_billing_minimum_is_the_adapters() -> None:
    assert answerers.GROQ_MINIMUM_S == groq_stt._MIN_BILLED_S


def test_an_answer_bounds_the_no_speech_estimate_as_a_transcript_does() -> None:
    bounds = Transcript.model_fields["no_speech_prob"]
    for model in (Answer, SegmentAnswer):
        field = model.model_fields["no_speech_prob"]
        assert (field.metadata, field.default) == (bounds.metadata, bounds.default), model


def test_each_speech_to_text_provider_the_settings_take_has_an_adapter() -> None:
    assert set(answerers._ADAPTERS) == set(get_args(SttProvider))


def _leaves(model: type[BaseModel], prefix: str = "") -> set[str]:
    names = set()
    for name, field in model.model_fields.items():
        kind = field.annotation
        if isinstance(kind, type) and issubclass(kind, BaseModel):
            names |= _leaves(kind, f"{prefix}{name}.")
        else:
            names.add(f"{prefix}{name}")
    return names


def test_a_run_records_every_setting_the_library_has(settings: VoiceSettings) -> None:
    """A run's scorecard and history line record each of its settings (`run_settings.shown`),
    `storage.var_dir` aside, a local path that changes no result: a setting the library gains is
    recorded too, or this fails."""
    args = run._parser().parse_args(["--show-settings"])
    shown = run_settings.shown(settings, args)
    assert _leaves(VoiceSettings) - {"storage.var_dir"} == {
        name for name in shown if not name.startswith("run.")
    }
