"""The command line of `poe eval-flights` (evals/run.py): the split, the repeats, the out folder,
the agent played (`--agent`, `scripted` by default or `lean`, D-113: the same scenarios, the lean
agent's scored by their outcomes, lean_checks.py), the talker's model and effort, the cap, a
resume, the keys' `.env`, other models' prices and limits, the input budget and the sends
of a request turned away."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final, get_args

from t2_agentic_voice import LlmSettings

from flight_voice.evals import run_setup as setup
from flight_voice.settings import AGENTS

MODELS: Final = get_args(LlmSettings.model_fields["model"].annotation)
EFFORTS: Final = get_args(LlmSettings.model_fields["reasoning_effort"].annotation)
REPEATS: Final = 3
CAP_USD: Final = 10.0


def parser() -> argparse.ArgumentParser:
    made = argparse.ArgumentParser(
        prog="poe eval-flights",
        description="Play the flight agent's scripted calls over one split, into --out.",
    )
    add = made.add_argument
    add("--split", choices=("dev", "held-out"), required=True, help="the split, all of it")
    add("--repeats", type=setup.count, default=REPEATS, help=f"plays a scenario ({REPEATS})")
    add("--out", type=Path, required=True, help="a new absolute folder, the main checkout's var/")
    add("--agent", choices=AGENTS, default="scripted", help="the agent played (scripted)")
    add("--model", choices=MODELS, default=setup.MODEL, help=f"the talker's ({setup.MODEL})")
    add("--effort", choices=EFFORTS, default="medium", help="its reasoning effort (medium)")
    add("--cap-usd", type=setup.amount, default=CAP_USD, help=f"the most it spends ({CAP_USD:g})")
    add("--resume", action="store_true", help="go on with the stopped run in --out")
    add("--env-file", type=Path, help="the .env the keys load from")
    add("--price", type=setup.price, action="append", default=[], metavar="MODEL=IN/OUT")
    add("--limits", type=setup.limits, action="append", default=[], metavar="MODEL=RPM/TPM/RPD")
    add("--input-budget-tokens", type=setup.count, default=setup.INPUT_BUDGET)
    add("--max-attempts", type=setup.count, default=4, help="sends of a request turned away")
    return made
