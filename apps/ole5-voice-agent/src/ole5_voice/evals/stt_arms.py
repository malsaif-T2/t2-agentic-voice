"""The speech-to-text providers `poe eval` (`run.py`) measures (D-100): each one the library's
`stt.provider` takes is an answerer of its own name, `groq` (Whisper, the baseline) and the
providers measured beside it, each asked through the library's port by `groq_answerer.py`'s
answerer, with its pacer, budget and retries.

- `SttArm`: what a run of one provider needs to know of it: the model its scorecard and history
  line record (Groq's is `stt.model`, Telnyx's `telnyx.stt_model`; another's is its adapter's
  fixed model, which a test ties to the adapter), the least it bills a request, the audio
  a request carries past its clip (`run_arm`: Telnyx's streamed engine hears 1.5 s of
  silence after each turn, which it bills), the most requests a minute its key allows,
  whether it needs the language named (Cohere detects none), and whether its answer names the
  language it heard, so a pass of `poe eval-languages` can hear turns through it
  (provider_language.py; Speechmatics' pack, Cohere, Telnyx and Nabrah name none).
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
from dataclasses import dataclass, replace
from typing import Final, Literal

from t2_agentic_voice import VoiceSettings, get_logger

from ole5_voice.evals.groq_answerer import GROQ_MINIMUM_S, least_billed
from ole5_voice.evals.runs import AnswerRequest, cost_usd
from ole5_voice.evals.worktree import refused

log = get_logger(__name__)


@dataclass(frozen=True)
class SttArm:
    """One provider as `poe eval` runs it (the module's docstring); `model` None for one whose
    model is a setting (Groq's `stt.model`, Telnyx's `telnyx.stt_model`)."""

    provider: str
    model: str | None
    minimum_s: float
    max_rpm: int
    names_language: bool = False
    hears_language: bool = False
    extra_s: float = 0.0


# The minimums: Groq bills 10 s a request at the least; the others bill the audio sent, by the
# provider guide's reading of their pricing (2026-11-16; Speechmatics' and Soniox's rounding
# unconfirmed; Telnyx bills by the minute and Nabrah 100 credits a minute, their rounding
# unconfirmed too). Cohere's trial key allows 5 requests a minute.
ARMS: Final = {
    "groq": SttArm("groq", None, GROQ_MINIMUM_S, 20, hears_language=True),
    "elevenlabs": SttArm("elevenlabs", "scribe_v3", 0.0, 20, hears_language=True),
    "speechmatics": SttArm("speechmatics", "ar_en-enhanced", 0.0, 20),
    "cohere": SttArm("cohere", "cohere-transcribe-arabic-07-2026", 0.0, 5, names_language=True),
    "soniox": SttArm("soniox", "stt-async-v6", 0.0, 20, hears_language=True),
    "telnyx": SttArm("telnyx", None, 0.0, 20),
    "nabrah": SttArm("nabrah", "nabrah_stt_v1", 0.0, 20),
}
# Telnyx's models heard only on its WebSocket, and the silence its adapter sends after each
# turn there (adapters/telnyx_stt.py's STREAMED and TAIL_S, which a test ties them to).
TELNYX_STREAMED: Final = frozenset({"humain/realtime"})
TELNYX_TAIL_S: Final = 1.5


def run_arm(settings: VoiceSettings, answerer: str) -> SttArm:
    """The arm a run of `answerer` bills by: Telnyx's with its tail of silence on each request
    when `telnyx.stt_model` is a streamed one, any other as `ARMS` holds it."""
    arm = ARMS[answerer]
    if answerer == "telnyx" and settings.telnyx.stt_model in TELNYX_STREAMED:
        return replace(arm, extra_s=TELNYX_TAIL_S)
    return arm


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
    """The model a run of `answerer` records: Groq's `stt.model`, Telnyx's
    `telnyx.stt_model`, or the provider's own."""
    arm = ARMS.get(answerer)
    if arm is not None and arm.model is not None:
        return arm.model
    return settings.telnyx.stt_model if answerer == "telnyx" else settings.stt.model


def check_cost(
    settings: VoiceSettings, sent: Sequence[AnswerRequest], args: argparse.Namespace
) -> Literal["estimated", "within"]:
    """Log the run's dry estimate (the module's docstring), then refuse it when its least cost
    passes `--cap-usd`: each request sent once, billed as `--answerer`'s provider bills it
    (`run_arm`; a retry, a windows run's requests and a batch job's own wait come on top), at
    `--price-per-hour`. `estimated` when the run is `--estimate-only`, so nothing is sent;
    else `within`."""
    arm, price_per_hour_usd = run_arm(settings, args.answerer), args.price_per_hour or 0.0
    cap_usd, max_rpm = args.cap_usd, args.max_rpm
    billed = least_billed(sent, minimum_s=arm.minimum_s, extra_s=arm.extra_s)
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
