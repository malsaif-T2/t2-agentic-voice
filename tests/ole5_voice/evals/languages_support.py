"""What the tests of `poe eval-languages` and its H2 arm share (test_languages_run.py,
test_languages_score.py, test_run_arms.py): made-up turn records (the `evals` facade's
`LanguageTurn`), a variant's result, a pass's record, and a pass folder written as a run
writes it, so `--read` and `--language-from` read it back."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ole5_voice.evals.eot_score import Judged
from ole5_voice.evals.languages_card import LanguageResult, LanguagesRun
from ole5_voice.evals.languages_score import scorecard_of, write_pass
from ole5_voice.evals.models import Language
from t2_agentic_voice.evals import LanguageTurn
from t2_agentic_voice.ports import LanguageScores

from tests.ole5_voice.evals.run_support import COMMIT
from tests.ole5_voice.evals.samples import SHA, WHEN


def scores(en: float) -> LanguageScores:
    """A verdict giving English `en` of the two languages."""
    return LanguageScores.parsed({"ar": 1 - en, "en": en}, among=("ar", "en"), mass=0.9)


def turn(by: str = "classified", **fields: Any) -> LanguageTurn:
    """A turn asked at 1.5 s, its verdict at 1.8 s (English 0.9), decided at 2.0 s on 2.4 s
    of speech, ending at 2.5 s; a `short` turn is never asked, a `late` one's verdict comes at
    2.3 s, and a `session` turn is neither asked nor decided."""
    base: dict[str, Any] = {
        "speech_stop_ms": 2200.0,
        "end_ms": 2500.0,
        "named": "ar",
        "by": by,
        "decided_ms": 2000.0,
        "speech_s": 2.4,
        "asked_ms": 1500.0,
        "verdict_ms": 1800.0,
        "verdict": scores(0.9),
    }
    if by == "short":
        base |= {"speech_s": 1.2, "asked_ms": None, "verdict_ms": None, "verdict": None}
    elif by == "late":
        base |= {"verdict_ms": 2300.0}
    elif by == "session":
        base |= {"decided_ms": None, "speech_s": None, "asked_ms": None}
        base |= {"verdict_ms": None, "verdict": None}
    return LanguageTurn.model_validate(base | fields)


def result(
    item: str,
    *turns: LanguageTurn,
    language: Language = "saudi",
    kind: str = "request",
    judged: Judged | None = None,
    split: str = "dev",
) -> LanguageResult:
    return LanguageResult.model_validate(
        {
            "item": item,
            "variant": f"{item}-v1",
            "split": split,
            "kind": kind,
            "language": language,
            "device": "laptop",
            "turns": turns,
            "judged": judged,
        }
    )


def run_info(
    name: str, *, classifier: str = "silero", split: str = "dev", **more: Any
) -> LanguagesRun:
    base: dict[str, Any] = {
        "name": name,
        "started_at": WHEN,
        "commit": COMMIT,
        "split": split,
        "classifier": classifier,
        "settings": {"stt.live_language": "session" if classifier == "off" else "classified"},
        "data_digest": SHA,
        "lead_s": 1.0,
        "tail_s": 4.5,
        "from_s": 2.0,
        "min_share": 0.7,
        "threads": 2,
        "held_in": "ar",
        "note": "a made-up pass",
    }
    return LanguagesRun.model_validate(base | more)


def pass_folder(
    folder: Path, run: LanguagesRun, results: tuple[LanguageResult, ...], *, complete: bool = True
) -> Path:
    """A pass's folder as `poe eval-languages` leaves it: its scorecard and its turns."""
    folder.mkdir(parents=True)
    write_pass(folder, scorecard_of(run, results, complete=complete), results)
    return folder
