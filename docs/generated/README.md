# Generated documents

Everything else in this folder is written by a command and never edited by hand. Each file is
the output of a pure `render_*() -> str` function that both the command (which writes the file)
and a freshness test (which compares the result with the committed file) call. When the code
changes and the file does not, the test fails with a FIX line naming the command to run.

To add one:

1. Write the renderer and a command that writes its output here (a `poe` task in
   `pyproject.toml`, with a line in `CLAUDE.md`'s command table).
2. Add the freshness test in the same commit.
3. Add a row below.

| File | Command | Freshness test |
| --- | --- | --- |
| [eval-history.md](eval-history.md) | `uv run poe eval-history` | `tests/ole5_voice/evals/test_history.py` |

The run history renders records that are never edited, so `poe docs` reads it as history
(`[docs] historical` in `harness.toml`): a run's note keeps the references of its time, a debt
row since paid included ([evaluation.md](../design/evaluation.md) says what the history holds).

Typical candidates as the project grows: an HTTP API's OpenAPI contract, a database schema, the
catalog of test data, and the guide's settings and API reference (the design's 14).
