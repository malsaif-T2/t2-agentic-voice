"""What a run of the flight agent's scripted calls (evals/run.py) reads and checks before anything
is sent: its command line's values, the scenarios and their rules, the call's settings, each
model's price and limits, and the dry estimate of the run's most spend.

- **The scenarios** are read from the run's own tree (`CALLS`) and refused when one cannot be
  read or the set breaks a rule (rules.py's `problems`); while no held-out scenario exists yet,
  each kind's missing held-out one is the one rule left, as the scenarios' own test holds it.
- **The models** a play sends to: the talker's (`--model`), and the library's own requests of a
  call, an uncertain overlap's (D-069) and the yes rule's check (D-082), each with its price
  (USD per million tokens read and written) and its limits (requests and tokens a minute,
  requests a day), the defaults of `PRICES` and `LIMITS` (the owner's key, as Ole5's runs give
  them) or `--price` and `--limits`; a model with neither is refused.
- **A play's settings** (`play_settings`): the run's, a call that needs `language_switch` under
  `stt.live_language = "detected"` (D-103).
- **The dry estimate** (`most_usd`): for each play, each turn's most talker requests (the
  settings' `llm.max_requests_per_turn`, the app's 4), an overlap's request for each turn said
  over the agent, and the yes rule's check for each turn that may answer a read-back (one said
  over it, or after a turn whose outcome is a read-back or an ask-again), each reading the input
  budget and writing its model's most.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Final

from t2_agentic_voice import LlmSettings, Providers, VoiceSettings, get_logger
from t2_agentic_voice.evals import (
    Limits,
    Price,
    consent_check_request,
    run_refused,
    uncertain_overlap_request,
)
from t2_agentic_voice.ports import ChatModel

from flight_voice.evals.rules import problems
from flight_voice.evals.scenarios import Scenario, ScenarioError, load, waiting
from flight_voice.evals.score import RunInfo

MODEL: Final = "openai/gpt-oss-120b"  # the talker's model unless named (D-074)
# A play's call ends this long after the caller's last turn, not the library's 120 s: no play
# that goes on waits that long for the agent (a booking's timeout and a slow search are about
# 20 s), so only a play stuck on the agent's turn reaches it, and it ends sooner.
IDLE_S: Final = 60.0
INPUT_BUDGET: Final = 8000  # tokens a request is budgeted to read: the prompt, history, results
APP: Final = Path("apps") / "flight-voice-agent"
CALLS: Final = APP / "evals" / "calls"  # under the run's tree
HISTORY: Final = APP / "evals" / "history.jsonl"
OVERLAP: Final = uncertain_overlap_request("-", "-")
CHECK: Final = consent_check_request("-", "-", "-")
OUTPUT_BUDGET: Final = 1024  # a request that names no most, as `PacedChat` budgets it
OVER: Final = frozenset({"agent_speaking", "read_back", "closing_question"})
ANSWERS: Final = frozenset({"read_back", "asked_again"})
PRICES: Final = {MODEL: Price(input_usd=0.15, output_usd=0.60)}
LIMITS: Final = {MODEL: Limits(rpm=30, tpm=100_000, rpd=10_000)}
_NO_HELD_OUT: Final = "has no held-out scenario"
log = get_logger(__name__)

__all__ = ["CALLS", "HISTORY", "INPUT_BUDGET", "MODEL", "waiting"]


def count(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError("give a whole number of 1 or more")
    return value


def amount(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        value = -1.0
    if not 0 <= value < float("inf"):
        raise argparse.ArgumentTypeError("give an amount of 0 or more")
    return value


def price(text: str) -> tuple[str, Price]:
    model, equals, rest = text.partition("=")
    read, slash, written = rest.partition("/")
    if not equals or not model or not slash:
        raise argparse.ArgumentTypeError("give a price as MODEL=IN/OUT, USD per million tokens")
    return model, Price(amount(read), amount(written))


def limits(text: str) -> tuple[str, Limits]:
    model, equals, rest = text.partition("=")
    parts = rest.split("/")
    if not equals or not model or len(parts) != 3:
        raise argparse.ArgumentTypeError("give limits as MODEL=RPM/TPM/RPD")
    rpm, tpm, rpd = (count(part) for part in parts)
    return model, Limits(rpm=rpm, tpm=tpm, rpd=rpd)


def checked_scenarios(folder: Path) -> tuple[Scenario, ...]:
    """The scenarios under `folder`, refused when one cannot be read or the set breaks a rule
    (the module's docstring)."""
    try:
        found = load(folder)
    except ScenarioError as error:
        raise run_refused(
            f"the scenarios cannot be read ({error})", "fix them; `poe check`"
        ) from None
    broken = problems(found)
    if not any(s.split == "held-out" for s in found):
        broken = [p for p in broken if _NO_HELD_OUT not in p]
    if broken:
        first, _, fix = broken[0].partition(". FIX: ")
        raise run_refused(
            f"the scenarios break {len(broken)} rule(s), first: {first}",
            fix.rstrip(".") or "fix them",
        )
    return found


def chat(env_file: Path | None, model: str) -> ChatModel:
    """The chat adapter for the talker's `model` (the library's `chat_model`: Groq's, or the
    route to OpenAI's, D-112), its keys from the environment and `env_file` when given."""
    keys = VoiceSettings.from_env(env_file=env_file, env="dev")
    llm = keys.llm.model_copy(update={"provider": LlmSettings.provider_of(model)})
    return Providers.chat_model(keys.model_copy(update={"llm": llm}))


def call_settings(model: str, effort: str) -> VoiceSettings:
    """The call's settings: the library's defaults, the talker's model and effort the run's,
    and a call that ends `IDLE_S` after the caller's last turn."""
    return VoiceSettings.model_validate(
        {
            "env": "test",
            "llm": {
                "provider": LlmSettings.provider_of(model),
                "model": model,
                "reasoning_effort": effort,
            },
            "limits": {"idle_s": IDLE_S},
        }
    )


def play_settings(scenario: Scenario, settings: VoiceSettings) -> VoiceSettings:
    """The settings `scenario` plays with: the run's, but `stt.live_language = "detected"`
    (D-103, off by default) for one that needs `language_switch`, the setting that lets a call
    move; every other scenario plays the app's default."""
    if "language_switch" not in scenario.needs:
        return settings
    stt = settings.stt.model_copy(update={"live_language": "detected"})
    return settings.model_copy(update={"stt": stt})


def models_of(model: str) -> tuple[str, ...]:
    """Every model a play may send to: the talker's, the overlap's and the yes rule's check's."""
    return tuple(sorted({model, OVERLAP.model, CHECK.model}))


def prices_and_limits(
    model: str,
    given_prices: Sequence[tuple[str, Price]],
    given_limits: Sequence[tuple[str, Limits]],
) -> tuple[dict[str, Price], dict[str, Limits]]:
    """Each model's price and limits, the defaults with the command line's on top; refused
    when a model a play sends to has none."""
    prices, limits = PRICES | dict(given_prices), LIMITS | dict(given_limits)
    for name, held, flag in (("price", prices, "--price"), ("limits", limits, "--limits")):
        if lacking := [m for m in models_of(model) if m not in held]:
            raise run_refused(
                f"no {name} for {', '.join(lacking)}", f"give {flag} MODEL=... for each model"
            )
    return (
        {m: prices[m] for m in models_of(model)},
        {m: limits[m] for m in models_of(model)},
    )


def asks(scenario: Scenario, settings: VoiceSettings) -> tuple[tuple[str, int, int], ...]:
    """The most requests one play of `scenario` sends, each model's with the most each writes
    (the module's docstring)."""
    said = [t for t in scenario.turns if not t.stop]
    over = sum(t.when in OVER for t in said)
    answers = sum(
        t.when in OVER or (before.outcome in ANSWERS)
        for before, t in zip(scenario.turns, scenario.turns[1:], strict=False)
        if not t.stop
    )
    llm = settings.llm
    return (
        (llm.model, llm.max_requests_per_turn * len(said), llm.max_output_tokens),
        (OVERLAP.model, over, OVERLAP.max_output_tokens or OUTPUT_BUDGET),
        (CHECK.model, answers, CHECK.max_output_tokens or OUTPUT_BUDGET),
    )


def most_usd(
    plays: Sequence[Scenario],
    args: argparse.Namespace,
    settings: VoiceSettings,
    prices: dict[str, Price],
) -> float:
    """The most `plays` spend at `prices` (the module's docstring)."""
    read = args.input_budget_tokens
    return sum(
        n * prices[model].of(read, written)
        for scenario in plays
        for model, n, written in asks(scenario, settings)
    )


def check_estimate(most: float, before: float, cap_usd: float, *, plays: int) -> None:
    """The dry estimate logged, and the run refused when it and what was spent pass the cap."""
    log.info("run_estimate", plays=plays, most_usd=round(most, 4), spent_usd=round(before, 4))
    if before + most > cap_usd:
        raise run_refused(
            f"its most spend, {most:.4f} USD, with {before:.4f} spent, passes --cap-usd "
            f"{cap_usd:g}",
            "lower --input-budget-tokens, or raise the cap within the plan's",
        )


def run_info(
    args: argparse.Namespace,
    name: str,
    began: datetime,
    commit: str,
    most: float,
    prices: dict[str, Price],
    limits: dict[str, Limits],
    data: tuple[str, ...],
) -> RunInfo:
    """What the run is, from its command line and what was checked."""
    return RunInfo(
        name=name,
        started_at=began,
        commit=commit,
        split=args.split,
        agent=args.agent,
        model=args.model,
        effort=args.effort,
        repeats=args.repeats,
        cap_usd=args.cap_usd,
        input_budget_tokens=args.input_budget_tokens,
        estimate_usd=round(most, 6),
        prices={m: f"{p.input_usd:g}/{p.output_usd:g}" for m, p in sorted(prices.items())},
        limits={m: f"{x.rpm}/{x.tpm}/{x.rpd}" for m, x in sorted(limits.items())},
        data=data,
    )
