# Golden principles

Opinionated, mechanical rules that keep the codebase legible and consistent for future agent
runs. They are this project's application of the [harness principles](PRINCIPLES.md).

A rule listed as enforced by **review** is a candidate for automation. When it is violated
twice, promote it into a check or test, and change its row to name that check. `uv run poe docs`
reads the rows as `| GP-NN |` at the start of a line; IDs are never reused.

| ID | Principle | Enforced by |
| --- | --- | --- |
| GP-01 | Imports follow the layer graph in `harness.toml`, explained in [ARCHITECTURE.md](../../ARCHITECTURE.md), whose layer table matches it; code sits inside a layer. A rule changes in both together, with its reason in a decision | `poe arch` (ARCH-LAYER, ARCH-DOC); the decision: review |
| GP-02 | Each IO or framework library is owned by one layer, listed in `harness.toml` | `poe arch` (ARCH-OWNER) |
| GP-03 | Structured logging only: `get_logger(__name__)`, snake_case event names, key/value context; no `print`; the standard library's logging is routed through the same format | `poe arch` (ARCH-PRINT, ARCH-OWNER), `tests/t2_agentic_voice/core/test_logging.py`; event names and context: review |
| GP-04 | Configuration only through `Settings`; `.env.example` lists every setting | `poe arch` (ARCH-ENV), `tests/t2_agentic_voice/core/test_config.py` |
| GP-05 | Modules stay small and single-purpose, under the line limit in `harness.toml`, in the library, the apps, `scripts/`, and `tests/` | `poe arch` (ARCH-SIZE) |
| GP-06 | Parse, don't guess: data crossing a boundary (HTTP, env, files, model output, database rows) becomes a typed model | `poe types` (mypy strict) + review |
| GP-07 | Errors are `AppError` subclasses (`core/errors.py`) with stable codes and user-safe messages; nothing below the outermost layer knows the transport (HTTP, CLI) | `tests/t2_agentic_voice/core/test_errors.py` (stable codes) + review |
| GP-08 | Every behavior change ships with tests; security changes ship with adversarial tests. An exception escaping a thread or a finalizer fails the test run | `poe test` (coverage floor, `filterwarnings`) + review |
| GP-09 | Docs are the system of record: required docs exist, links resolve with exact case, nothing is orphaned, `CLAUDE.md` stays a map, and no install placeholder is left; each plan is named `NNN-slug.md`, has its sections and a full Status line that matches its folder, and the roadmap links every active plan; no number is given to two plans, decisions, debt rows, principles, or invariants | `poe docs` (DOC-REQUIRED, DOC-LINK, DOC-ORPHAN, DOC-ENTRY, DOC-PLACEHOLDER, DOC-PLAN, DOC-REGISTER) |
| GP-10 | Prefer boring, well-known libraries; build our own only for correctness, observability, or legibility | review |
| GP-11 | Generated docs (`docs/generated/`) come from a command and are never edited by hand; each has a freshness test that fails when it is stale | one freshness test per generated doc ([list](../generated/README.md)) + review |
| GP-12 | Test and demo data are deterministic: fixed seeds, a fixed reference date, no wall-clock time | review |
| GP-13 | The formatter owns code layout, with LF line endings everywhere; `# fmt: skip` only ends a module- or class-level assignment of hand-aligned data | `poe lint` (layout; line endings of Python files), `poe docs` (DOC-EOL: docs, code, root config), `poe arch` (ARCH-FMT) |
| GP-14 | Code cites decisions (`D-NNN`), never milestone numbers; living docs cite only milestones in the roadmap; every cited decision, debt item, principle, plan, and invariant exists | `poe docs` (DOC-MILESTONE, DOC-REF) |
| GP-15 | Tests never touch the developer's machine state: no `.env`, none of this project's variables from the shell, no `var/`; every path comes from `Settings`, which the tests point at a scratch folder | `tests/harness/test_isolation.py`, the fixtures in `tests/conftest.py` |
| GP-16 | Docs record what was decided, measured, or said, and by whom; never a reason, a policy, or a number nobody gave. The agent's own reasoning is marked as its own | review, and each garbage-collection round's read |
| GP-17 | Commands are safe to explore and read the same anywhere: each parses its arguments, so `--help` only prints help, and every `poe` task writes UTF-8, piped or not | `tests/harness/test_commands.py` |
| GP-18 | New behavior that changes a measured outcome lands behind a setting; the default changes only on a registered measurement ([evaluation.md](../design/evaluation.md)) | review |
| GP-19 | The outermost layer turns every error, a crash included, into one shape for its transport, with the error's stable code and the request's reference (so a user's report leads to the request's logs); it never echoes a rejected value | review (a test per transport once the outermost layer exists) |
| GP-20 | Models at a boundary (requests, command arguments, files) reuse core's field types and constraints, never restate them: invalid input is rejected as invalid input, never a server error | review |
| GP-21 | Commands and agents never modify or wipe data they did not create: the owner's files under `var/` (or any folder the owner names) are read-only to them; a command that rebuilds data rewrites only what it owns, and destructive runs go to a scratch store given on the command line | review, GP-15's tests for the test suite |
| GP-22 | Every outside service (speech-to-text, the model, text-to-speech, the knowledge base, the ticket system) is reached through a port in `domain` and an adapter in `adapters`, chosen by a setting, so a provider is swapped by configuration (D-004; the mechanism is D-003's) | `poe arch` (ARCH-OWNER on the service clients) + review, including that no Pipecat provider service is used |
