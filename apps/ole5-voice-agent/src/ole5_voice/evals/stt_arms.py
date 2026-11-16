"""The speech-to-text providers `poe eval` (`run.py`) measures (D-100): each one the library's
`stt.provider` takes is an answerer of its own name, `groq` (Whisper, the baseline) and the
providers measured beside it, each asked through the library's port by `groq_answerer.py`'s
answerer, with its pacer, budget and retries.

- `SttArm`: what a run of one provider needs to know of it: the model its scorecard and history
  line record (Groq's is `stt.model`; another's is its adapter's fixed model, which a test ties
  to the adapter), the least it bills a request, the most requests a minute its key allows, and
  whether it needs the language named (Cohere detects none).
- `arm_problem`: what the parser refuses of a provider's flags, before anything is sent:
  `--model` and `--base-url` are Groq's; `--language-hint auto` for a provider that detects no
  language; a `--max-rpm` past its key's limit.
- `arm_settings`: the run's settings with `stt.provider` the answerer's, so no `T2V_` variable
  changes a registered arm; every other group is recorded as it is (`run_settings._others`).
- `check_cost`: the dry estimate, logged before anything is sent (its requests, the least
  seconds billed and dollars, and the least minutes at the run's pace), and the refusal of a
  run whose least cost passes `--cap-usd`.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from t2_agentic_voice import VoiceSettings, get_logger

from ole5_voice.evals.groq_answerer import GROQ_MINIMUM_S, least_billed
from ole5_voice.evals.runs import AnswerRequest, cost_usd
from ole5_voice.evals.worktree import refused

log = get_logger(__name__)


@dataclass(frozen=True)
class SttArm:
    """One provider as `poe eval` runs it (the module's docstring); `model` None for Groq's,
    which is `stt.model`."""

    provider: str
    model: str | None
    minimum_s: float
    max_rpm: int
    names_language: bool = False


# The minimums: Groq bills 10 s a request at the least; the others bill the audio sent, by the
# provider guide's reading of their pricing (2026-11-16; Speechmatics' and Soniox's rounding
# unconfirmed). Cohere's trial key allows 5 requests a minute.
ARMS: Final = {
    "groq": SttArm("groq", None, GROQ_MINIMUM_S, 20),
    "elevenlabs": SttArm("elevenlabs", "scribe_v3", 0.0, 20),
    "speechmatics": SttArm("speechmatics", "ar_en-enhanced", 0.0, 20),
    "cohere": SttArm("cohere", "cohere-transcribe-arabic-07-2026", 0.0, 5, names_language=True),
    "soniox": SttArm("soniox", "stt-async-v6", 0.0, 20),
}


def arm_problem(args: argparse.Namespace) -> str | None:
    """What `poe eval`'s parser refuses of a provider's flags (the module's docstring), or
    None; none for the `reference` answerer."""
    arm = ARMS.get(args.answerer or "")
    if args.estimate_only and (arm is None or args.windows_ms):
        return "--estimate-only serves a provider's run of whole variants: no --windows-ms"
    if arm is None or arm.provider == "groq":
        return None
    if args.model or args.base_url:
        return f"--model and --base-url are Groq's: not with --answerer {arm.provider}"
    if arm.names_language and args.language_hint == "auto":
        return f"{arm.provider} detects no language: give --language-hint label, ar or en"
    if args.max_rpm > arm.max_rpm:
        return f"{arm.provider}'s key allows --max-rpm {arm.max_rpm} at the most"
    return None


def arm_settings(settings: VoiceSettings, answerer: str) -> VoiceSettings:
    """`settings` with `stt.provider` the answerer's when it names a provider; as they are for
    the `reference` answerer."""
    if answerer not in ARMS:
        return settings
    stt = settings.stt.model_copy(update={"provider": answerer})
    return settings.model_copy(update={"stt": stt})


def recorded_model(settings: VoiceSettings, answerer: str) -> str:
    """The model a run of `answerer` records: Groq's `stt.model`, or the provider's own."""
    arm = ARMS.get(answerer)
    return settings.stt.model if arm is None or arm.model is None else arm.model


def check_cost(
    arm: SttArm, sent: Sequence[AnswerRequest], price_per_hour_usd: float, args: argparse.Namespace
) -> Literal["estimated", "within"]:
    """Log the run's dry estimate (the module's docstring), then refuse it when its least cost
    passes `--cap-usd`: each request sent once, billed as the provider bills it (a retry, a
    windows run's requests and a batch job's own wait come on top). `estimated` when the run
    is `--estimate-only`, so nothing is sent; else `within`."""
    cap_usd, max_rpm = args.cap_usd, args.max_rpm
    billed = least_billed(sent, minimum_s=arm.minimum_s)
    requests = sum(len(request.segments) for request in sent)
    least = cost_usd(billed, price_per_hour_usd)
    log.info(
        "run_estimate",
        provider=arm.provider,
        requests=requests,
        least_billed_s=round(billed, 1),
        least_usd=round(least, 4),
        cap_usd=cap_usd,
        least_minutes=round(requests / max_rpm, 1),
    )
    if least > cap_usd:
        raise refused(
            f"the run's least cost, ${least:.4f}, passes --cap-usd",
            "raise --cap-usd, or check --price-per-hour",
        )
    return "estimated" if args.estimate_only else "within"
