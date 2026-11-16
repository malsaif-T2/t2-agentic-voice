"""The folder of a run of K or S (`--out`), and what the runners read of the shared history.

A run's folder holds what it was (`run.json`, written before anything is sent), each result as
it finishes (`results.jsonl`, a dev run's only), each session (`sessions.jsonl`), the scorecard
after the last session (written whole, then moved into place) and its history lines. A run that
stopped at the key's daily limit, the cap or an interrupt goes on in a new session with
`--resume`, at the same commit, settings and data, its finished results kept: so a run is spread
over days rather than passing the key's daily limit. A held-out run keeps no result, so it is
never resumed: it is run again whole.

`requests_today` counts each model's requests in the lines of one UTC day of the shared history
and of every other app's run history (the library's day counter), which a run's pacers start the
day's count from; `history_accepts` says whether the shared
history can hold a line of this shape (`run_lines.AnyLine`), which a run asks before it starts,
and `append_shared` adds one.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
from typing import Final

from pydantic import BaseModel, TypeAdapter, ValidationError
from t2_agentic_voice.evals import Checkout, Git, check_out, every_history, run_refused
from t2_agentic_voice.evals import requests_today as day_requests

from ole5_voice.evals.files import parse_json, read_model, read_text, write_json
from ole5_voice.evals.history import append_line, read_history
from ole5_voice.evals.models import NAME_RULE, is_name
from ole5_voice.evals.run_lines import AnyLine
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.talker_data import TalkerDataError

RUN_FILE: Final = "run.json"
RESULTS_FILE: Final = "results.jsonl"
SESSIONS_FILE: Final = "sessions.jsonl"
_LINE: Final[TypeAdapter[AnyLine]] = TypeAdapter(AnyLine)


def history_accepts(line: BaseModel) -> bool:
    """Whether the shared history reads `line` back as one of its kinds."""
    try:
        _LINE.validate_json(line.model_dump_json(warnings=False))
    except ValidationError:
        return False
    return True


def append_shared(line: BaseModel, history: Path) -> None:
    """Add `line` to the shared history as `history.append_line` does, once it reads back as
    one of the history's kinds; TalkerDataError naming the fields otherwise."""
    checked = parse_json(
        _LINE,
        line.model_dump_json(warnings=False),
        lambda problem: TalkerDataError(f"the shared history takes no such line ({problem})"),
    )
    append_line(checked, history)


def requests_today(history: Path, today: date) -> Counter[str]:
    """Each model's requests in the lines of `history`, and of every other app's run history
    beside it (the library's `every_history`), whose run began on `today` (UTC): the apps spend
    on one key, so its day is counted once over all of them. The shared history is read strictly
    first, as every reader of it reads it; none when there is no history yet."""
    if history.exists():
        read_history(history)
    return day_requests(every_history(history), today)


def folder_for(out: Path, *, resume: bool, checkout: Checkout, git: Git) -> RunFolder:
    """The run's folder: a new one where a run may write (`worktree.check_out`), or with
    `resume` the folder of a run already begun; its name, the run's, a name."""
    if resume:
        target = out.expanduser().resolve()
        if not (target / RUN_FILE).is_file():
            raise run_refused(
                f"--resume: {target} holds no run", "give the --out of the stopped run"
            )
    else:
        target = check_out(out, checkout, git)
    if not is_name(target.name):
        raise run_refused(
            f"the --out folder's name, the run's, is not a name, which is {NAME_RULE}",
            "name the folder like k1-dev-a",
        )
    return RunFolder(target)


class RunFolder:
    """A run's `--out` folder (the module's docstring)."""

    def __init__(self, out: Path) -> None:
        self.out = out

    def resumed[M: BaseModel](self, run: M) -> M:
        """The run begun in the folder, refused unless it is `run` but for when it began: the
        same commit, settings, data and note."""
        earlier = self.run(type(run))
        fields = [name for name in type(run).model_fields if name != "started_at"]
        if differing := [name for name in fields if getattr(earlier, name) != getattr(run, name)]:
            raise run_refused(
                f"--resume: the run in --out differs in {', '.join(differing)}",
                "go on at the same commit, with the same command line and data",
            )
        return earlier

    def begin(self, run: BaseModel) -> None:
        """Make the folder, and write what the run is."""
        self.out.mkdir(parents=True)
        self._write(RUN_FILE, run.model_dump_json(indent=2) + "\n")

    def run[M: BaseModel](self, shape: type[M]) -> M:
        """What the run in the folder is; TalkerDataError when it holds no run of `shape`."""
        return read_model(self.out / RUN_FILE, shape, self._refuse(RUN_FILE))

    def results[M: BaseModel](self, shape: type[M]) -> list[M]:
        return self._lines(RESULTS_FILE, shape)

    def sessions[M: BaseModel](self, shape: type[M]) -> list[M]:
        return self._lines(SESSIONS_FILE, shape)

    def add_result(self, result: BaseModel) -> None:
        self._append(RESULTS_FILE, result)

    def add_session(self, session: BaseModel) -> None:
        self._append(SESSIONS_FILE, session)

    def write_scorecard(self, card: BaseModel) -> None:
        """The scorecard, written whole and then moved into place (`files.write_json`)."""
        write_json(self.out, SCORECARD_FILE, card)

    def _lines[M: BaseModel](self, name: str, shape: type[M]) -> list[M]:
        path = self.out / name
        if not path.exists():
            return []
        text = read_text(path)
        if text is None:
            raise TalkerDataError(f"{name} in the run's folder cannot be read as UTF-8 text")
        return [
            parse_json(shape, line, self._refuse(f"{name}, line {number}"))
            for number, line in enumerate(text.splitlines(), start=1)
            if line
        ]

    def _append(self, name: str, model: BaseModel) -> None:
        with (self.out / name).open("a", encoding="utf-8", newline="\n") as file:
            file.write(model.model_dump_json() + "\n")

    def _write(self, name: str, text: str) -> None:
        (self.out / name).write_bytes(text.encode("utf-8"))

    @staticmethod
    def _refuse(where: str) -> _Refusal:
        return _Refusal(where)


class _Refusal:
    """A refusal naming the run folder's file, and the fields only."""

    def __init__(self, where: str) -> None:
        self.where = where

    def __call__(self, problem: str) -> TalkerDataError:
        return TalkerDataError(f"{self.where} in the run's folder: {problem}")
