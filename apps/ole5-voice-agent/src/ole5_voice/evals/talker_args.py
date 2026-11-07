"""What runs K and S share before anything is sent (plan 006's registration): the command line's
model, judge, prices, limits, cap, agent and data, each pinned there; the settings they become;
the parts a run is built from (`TalkerParts`, each replaceable by a test's fake); the knowledge
set and the points' text the judge reads, with the digest of every file a run depends on; and
the paced chat model every request goes through; and the checks of the cap and the day's limit
before a run starts.

Two settings a run uses: the chat adapter's, loaded from the environment and `--env-file` (or
the working folder's `.env`, `run_settings.DOTENV`) for the key alone, its base URL `--base-url`
or the SDK's own and its timeout `--timeout-s`; and the call's, built in code from the
library's defaults and the command line's `llm` group, so no `T2V_` variable changes an arm.
The agent and its knowledge base come from factories named `module:name` inside `ole5_voice`
(`--agent`, given the knowledge base; `--knowledge`, given the `--env-file`: factories.py), so a
run measures the app's own declaration through the library's public API.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final, get_args

from pydantic import BaseModel
from t2_agentic_voice import LlmSettings, VoiceAgent, VoiceSettings, get_logger
from t2_agentic_voice.evals import TextCall
from t2_agentic_voice.groq import GroqChat
from t2_agentic_voice.ports import ChatModel

from ole5_voice.evals import run_folder, run_settings
from ole5_voice.evals.chat_pacing import Limits, ModelPacer, PacedChat, Price, Spend
from ole5_voice.evals.factories import env_file_of, load_factory
from ole5_voice.evals.groq_answerer import Clock, Sleep
from ole5_voice.evals.judge import JUDGE_MODEL
from ole5_voice.evals.models import NAME_RULE, is_name
from ole5_voice.evals.runs import holds_placeholder
from ole5_voice.evals.talker_call import CallFactory
from ole5_voice.evals.worktree import Git, refused, run_git

MODELS: Final = get_args(LlmSettings.model_fields["model"].annotation)  # `llm.model`'s choices
EFFORTS: Final = get_args(LlmSettings.model_fields["reasoning_effort"].annotation)
INPUT_BUDGET: Final = 6000  # tokens a request is budgeted to read: the prompt, history, passages
_SECRET = re.compile(r"(^|_)(key|keys|secret|token|password|file)$")
_LIMITS: Final = ("rpm", "tpm", "rpd")
log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def _here() -> Path:
    return Path(__file__).resolve().parent


@dataclass(frozen=True)
class TalkerParts:
    """What a run of K or S is built from, each replaceable by a test's fake: the folder whose
    checkout runs, `git`, the chat adapter, the call (`TextCall`), the factories' loader, the
    shared history's appender and checks, and the clocks."""

    folder: Path = field(default_factory=_here)
    git: Git = run_git
    chat: Callable[[VoiceSettings], ChatModel] = GroqChat.from_settings
    call: CallFactory = TextCall
    load_factory: Callable[[str], Callable[..., object]] = load_factory
    append_line: Callable[[BaseModel, Path], None] = run_folder.append_shared
    history_accepts: Callable[[BaseModel], bool] = run_folder.history_accepts
    requests_today: Callable[[Path, date], Counter[str]] = run_folder.requests_today
    now: Callable[[], datetime] = _now
    clock: Clock = time.perf_counter
    sleep: Sleep = asyncio.sleep


def count(text: str) -> int:
    if (value := int(text)) < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


def amount(text: str) -> float:
    if not math.isfinite(value := float(text)) or value < 0:
        raise argparse.ArgumentTypeError("must be a finite number, 0 or more")
    return value


def seconds(text: str) -> float:
    if not math.isfinite(value := float(text)) or value <= 0:
        raise argparse.ArgumentTypeError("must be a finite number of seconds above 0")
    return value


def price(text: str) -> tuple[str, Price]:
    model, equals, rest = text.partition("=")
    read, slash, written = rest.partition("/")
    if not equals or not model or not slash:
        raise argparse.ArgumentTypeError("give a price as MODEL=IN/OUT, USD per million tokens")
    return model, Price(amount(read), amount(written))


def limit(text: str) -> tuple[str, int]:
    model, equals, value = text.partition("=")
    if not equals or not model:
        raise argparse.ArgumentTypeError("give a limit as MODEL=N")
    return model, count(value)


def add_common(parser: argparse.ArgumentParser) -> None:
    """The flags runs K and S share."""
    add = parser.add_argument
    add("--arm", help="the arm's name, such as k1")
    add("--model", choices=MODELS, help="llm.model, the talker's model")
    add("--reasoning-effort", choices=EFFORTS, help="llm.reasoning_effort")
    add("--max-output-tokens", type=count, help="llm.max_output_tokens")
    add("--timeout-s", type=seconds, help="llm.timeout_s, each model request's")
    add("--judge-model", default=JUDGE_MODEL, help=f"the judge's model ({JUDGE_MODEL})")
    add("--judge-max-output-tokens", type=count, default=300, help="each verdict's, at most")
    add("--base-url", help=f"groq.base_url ({run_settings.GROQ_BASE_URL})")
    add("--env-file", type=Path, help="the .env the key and the knowledge base's access load from")
    add("--price", type=price, action="append", default=[], metavar="MODEL=IN/OUT")
    for name in _LIMITS:
        add(f"--{name}", type=limit, action="append", default=[], metavar="MODEL=N")
    add("--cap-usd", type=amount, help="the most the run may spend, its sessions together")
    add("--input-budget-tokens", type=count, default=INPUT_BUDGET, help="a request's, read")
    add("--max-attempts", type=count, default=4, help="sends of a request turned away (4)")
    add("--variant-timeout-s", type=seconds, default=180.0, help="each call's limit (180)")
    add("--agent", help="the agent's factory, ole5_voice.<module>:<name>, given the base")
    add("--knowledge", help="the knowledge base's factory, given --env-file")
    add("--search-tool", help="the name of the agent's knowledge tool")
    add("--points-text", type=Path, help="the snapshot of the points' text the judge reads")
    add("--out", type=Path, help="a new folder outside the worktree, which git ignores")
    add("--resume", action="store_true", help="go on with the stopped run in --out")
    add("--note", help="why the run is made")
    add("--smoke-only", action="store_true", help="run the smoke test alone")


def require(parser: argparse.ArgumentParser, args: argparse.Namespace, *also: str) -> None:
    """The command line's checks runs K and S share: every flag a run needs (`also` too), a
    note with no install placeholder, an arm that is a name, a judge that is not the talker's
    model (Q6), and no smoke test alone in a resumed run."""
    named = ["arm", "model", "reasoning_effort", "max_output_tokens", "timeout_s", "cap_usd"]
    named += ["agent", "knowledge", "search_tool", "points_text", "out", "note", *also]
    if lacking := [f"--{n.replace('_', '-')}" for n in named if getattr(args, n) is None]:
        parser.error(f"a run needs {', '.join(lacking)}")
    if holds_placeholder(args.note):
        parser.error("--note holds an install placeholder, which the docs check refuses")
    if not is_name(args.arm):
        parser.error(f"--arm is not a name, which is {NAME_RULE}")
    if args.judge_model == args.model:
        parser.error("--judge-model is a model other than the talker's (Q6)")
    if args.resume and args.smoke_only:
        parser.error("--resume goes on with a run's work: no --smoke-only")


def chat_settings(args: argparse.Namespace) -> VoiceSettings:
    """The chat adapter's settings: the key from the environment and the `.env`, the base URL
    and the timeout from the command line."""
    loaded = VoiceSettings.from_env(env_file=env_file_of(args), env="dev")
    data = loaded.model_dump()
    data["groq"]["base_url"] = args.base_url or run_settings.GROQ_BASE_URL
    data["llm"]["timeout_s"] = args.timeout_s
    data["tracing"]["endpoint"] = None
    checked = VoiceSettings.model_validate(data, context={"prefix": loaded.prefix})
    return loaded.model_copy(update=dict(checked))


def call_settings(args: argparse.Namespace) -> VoiceSettings:
    """The call's settings: the library's defaults, with the command line's `llm` group."""
    llm = {
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "max_output_tokens": args.max_output_tokens,
        "timeout_s": args.timeout_s,
    }
    return VoiceSettings.model_validate({"env": "test", "llm": llm})


def flat(settings: VoiceSettings) -> dict[str, str]:
    """Every setting of every group by its dotted name, as text: a secret, a key map and a
    secret's file only as set or not set, a sequence as its length, a map by its keys."""
    found: dict[str, str] = {"env": settings.env}
    for group in type(settings).model_fields:
        values = getattr(settings, group)
        if not isinstance(values, BaseModel):
            continue
        for name in type(values).model_fields:
            value = getattr(values, name)
            if _SECRET.search(name):
                text = "set" if value else "not set"
            elif value is None or isinstance(value, bool):
                text = "none" if value is None else str(value).lower()
            elif isinstance(value, Mapping):
                text = ",".join(sorted(map(str, value))) or "none"
            elif isinstance(value, tuple | list):
                text = f"{len(value)} entries"
            else:
                text = str(value)
            found[f"{group}.{name}"] = text
    found.pop("storage.var_dir", None)  # a local path, which changes no result
    return found


def shown(
    args: argparse.Namespace, chat: VoiceSettings, call: VoiceSettings, agent: VoiceAgent
) -> dict[str, str]:
    """Every setting a run has, as its scorecard and history record them."""
    run = {
        "groq.base_url": chat.groq.base_url,
        "groq.api_key": "not set" if chat.groq.resolved_api_key() is None else "set",
        "run.arm": args.arm,
        "run.agent": args.agent,
        "run.agent_name": agent.name,
        "run.agent_version": agent.version or "none",
        "run.knowledge": args.knowledge,
        "run.search_tool": args.search_tool,
        "run.judge_model": args.judge_model,
        "run.judge_max_output_tokens": str(args.judge_max_output_tokens),
        "run.input_budget_tokens": str(args.input_budget_tokens),
        "run.max_attempts": str(args.max_attempts),
        "run.variant_timeout_s": str(args.variant_timeout_s),
        "run.cap_usd": str(args.cap_usd),
        "run.smoke_only": str(args.smoke_only).lower(),
    }
    for flag in _LIMITS:
        run |= {f"run.{flag}.{model}": str(n) for model, n in getattr(args, flag)}
    run |= {f"run.price.{m}": f"{p.input_usd:g}/{p.output_usd:g}" for m, p in args.price}
    return flat(call) | run


def pacing(
    args: argparse.Namespace,
    inner: ChatModel,
    *,
    today: Mapping[str, int],
    before_usd: float,
    parts: TalkerParts,
) -> PacedChat:
    """The paced chat model of a run: each of its two models (the talker's and the judge's)
    with its price and limits from the command line, refused when one has none."""
    models = sorted({args.model, args.judge_model})
    given: dict[str, Mapping[str, object]] = {"price": dict(args.price)}
    given |= {name: dict(getattr(args, name)) for name in _LIMITS}
    for name, values in given.items():
        if lacking := [model for model in models if model not in values]:
            raise refused(
                f"--{name} names nothing for {', '.join(lacking)}",
                f"give --{name} MODEL=... for the talker's model and the judge's",
            )
    prices = {model: dict(args.price)[model] for model in models}
    pacers = {
        model: ModelPacer(
            Limits(*(dict(getattr(args, name))[model] for name in _LIMITS)),
            used_today=today.get(model, 0),
            clock=parts.clock,
            sleep=parts.sleep,
        )
        for model in models
    }
    return PacedChat(
        inner,
        pacers=pacers,
        spend=Spend(prices=prices, cap_usd=args.cap_usd, before_usd=before_usd),
        input_budget=args.input_budget_tokens,
        attempts=args.max_attempts,
        sleep=parts.sleep,
    )


def check_budget(
    args: argparse.Namespace,
    paced: PacedChat,
    *,
    units: int,
    requests: Mapping[str, int],
    whole_day: bool,
) -> None:
    """The cap and the day's limit checked before a run: `requests` are the most one of its
    `units` (a variant, a scenario's play) sends to each model. The run's most spend is logged;
    it is refused when the cap leaves no room for one unit, and, with `whole_day` (a held-out
    run, which is never resumed), when its units' requests would pass a model's daily limit."""
    written = {args.model: args.max_output_tokens, args.judge_model: args.judge_max_output_tokens}
    one = sum(
        n * paced.spend.prices[model].of(args.input_budget_tokens, written[model])
        for model, n in requests.items()
    )
    spent = paced.spend.cost_usd()
    log.info("run_estimate", units=units, most_usd=round(one * units, 4), spent_usd=spent)
    if spent + one > args.cap_usd:
        raise refused(
            f"--cap-usd {args.cap_usd:g} leaves no room for one more (spent {spent:.4f})",
            "raise the cap, within the plan's",
        )
    for model, n in requests.items() if whole_day else ():
        pacer = paced.pacers[model]
        if (left := pacer.limits.rpd - pacer.today) < n * units:
            raise refused(
                f"{model}'s daily limit leaves {left} requests today, and the run may send "
                f"{n * units}",
                "run it on a day with room, since a held-out run is never resumed",
            )
