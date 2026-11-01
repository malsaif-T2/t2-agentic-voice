# T2 Agentic Voice — agent map

T2 Agentic Voice is a Python library that T2's teams install for speech-first voice agents
(turn-taking, interruptions, answers, actions only on a clear yes, in Saudi Arabic, MSA and
English). Its first app, the **Ole5 Voice Agent**, is built here on its public API (D-013). The
owner's full description is in [DESCRIPTION.md](docs/project/DESCRIPTION.md). Stack: Python 3.12
· a uv workspace · pydantic; the product libraries (Pipecat, FastAPI, Groq, Phoenix) are recorded
in [decisions.md](docs/design/decisions.md) (D-002). Groq is the only provider for now (D-004).

This file is a **map, not a manual**. Open the linked doc when your task touches that area.

## How we work

- **Humans steer, agents execute.** The owner sets goals and acceptance criteria; the agent
  writes all code, tests, docs, and tooling. See [PRINCIPLES](docs/harness/PRINCIPLES.md).
- **Propose before design changes.** On a design or architecture question, answer with a
  proposal and edit nothing until the owner approves. See [WORKING-RULES](WORKING-RULES.md).
- **The repository is the system of record.** A decision or lesson that matters goes into the
  repo (doc, test, or check), not only into chat.
- **Depth-first.** Non-trivial work runs from an execution plan and lands as small, verified
  blocks. See [plans](docs/plans/README.md).
- **When you struggle, fix the environment.** Ask "what capability is missing?" and add a test,
  check, tool, or doc, instead of adding more prose here.

## Commands

Run everything as `uv run poe <task>` (`uv run poe` lists tasks).

| Task | Purpose |
| --- | --- |
| `check` | Full gate: lint, types, arch, docs, test. **Must pass before a task is done.** |
| `fmt` | Auto-format and apply safe lint fixes. Run first when `lint` fails. |
| `lint` · `types` · `arch` · `docs` · `test` | Individual gates (`arch` and `docs` print a FIX line for every violation). |
| `gc` · `quality` | Say whether a garbage-collection round is due, then list its candidates · grade each layer after `check`; neither is a gate. |
| `golden` · `record` | Validate the golden set and freeze its expected answers · record and review its takes (a page on 127.0.0.1). |
| `eval` · `eval-compare` · `eval-history` | Run an answerer over the golden set (refuses the main checkout) · compare two runs (sign test by item) · render the run history. |

Add a row for every task the project adds. Add dependencies with `uv add <pkg>` (`--dev` for
tooling), in the member that needs them (`uv add --package t2-agentic-voice <pkg>`); never use
pip or edit `uv.lock`. The library's settings come from `T2V_*` environment
variables or `.env`, and [.env.example](.env.example) lists them all. The harness's own rules
(layers, the public API, the apps, owned libraries, required docs, size caps, the coverage
floor) live in [harness.toml](harness.toml).

## Where things are

| You need | Read |
| --- | --- |
| What we are building | [docs/project/DESCRIPTION.md](docs/project/DESCRIPTION.md) |
| The owner's documents (meeting notes, reports, snapshots) and how to write them | [docs/project/README.md](docs/project/README.md) |
| Layers, dependency rules, the library and its apps, the main flow | [ARCHITECTURE.md](ARCHITECTURE.md) |
| What the library provides, what an app provides, its public API | [docs/design/package-design.md](docs/design/package-design.md) |
| How teammates use the library (the guide) | [docs/guide/README.md](docs/guide/README.md) |
| How the agent works with the owner and other sessions; where new feedback goes | [WORKING-RULES.md](WORKING-RULES.md) |
| Security invariants and threat model | [docs/SECURITY.md](docs/SECURITY.md) |
| How a measured quality is measured, and a change judged | [docs/design/evaluation.md](docs/design/evaluation.md) |
| Why things are the way they are | [docs/design/decisions.md](docs/design/decisions.md) |
| Milestones and open questions | [docs/plans/roadmap.md](docs/plans/roadmap.md) |
| How plans work, and the template | [docs/plans/README.md](docs/plans/README.md) |
| Work in progress | [docs/plans/active/](docs/plans/active/) |
| Known debt | [docs/plans/tech-debt.md](docs/plans/tech-debt.md) |
| Golden principles and which check enforces each | [docs/harness/golden-principles.md](docs/harness/golden-principles.md) |
| Garbage collection: when and how to run a cleanup round | [docs/harness/garbage-collection.md](docs/harness/garbage-collection.md) |
| Quality grades per layer, and each layer's gaps | [docs/harness/quality.md](docs/harness/quality.md) |
| Generated docs (never edited by hand) | [docs/generated/README.md](docs/generated/README.md) |

## Code map

```
packages/t2-agentic-voice/src/t2_agentic_voice/   the library; its public API is __init__.py
  ports.py groq.py languages.py evals.py tracing.py   and these facades beside it (re-exports only)
  core/       settings, structured logging, error types (AppError), tracing, shared types
  domain/     the call's rules and the ports, no IO: the yes rule, interruptions, speech text
  adapters/   the outside services behind the ports: Groq, the knowledge base, the tickets
  actions/    the backend, the only part that acts: tools, the action record, outcomes
  agent/      the talker: prompts, tool definitions, one turn, the output guard
  voice/      one call's real-time pipeline: WebRTC, end of turn, interruptions, cancel scope
  testing/    what a team tests and measures with: the evaluation scorers; later, the fakes
  api/        HTTP and the composition root: the widget, call set-up, health
apps/ole5-voice-agent/src/ole5_voice/   the Ole5 app: only the library's public API (ARCH-PUBLIC)
  evals/      the golden set's commands; its data in apps/ole5-voice-agent/evals/, no audio
examples/minimal/src/minimal_example/   the smallest app: the quickstart, a test of the library
apps/ole5-voice-agent/web/   Ole5's browser widget (plain HTML/JS/CSS; not built yet)
scripts/      the harness: check_architecture.py (arch), check_docs.py (docs), gc_due.py and
              gc_report.py (gc), quality.py, and their helpers; all read harness.toml
              through harness_config.py
tests/        one folder per package (t2_agentic_voice/, ole5_voice/, minimal_example/);
              harness/ tests the checks themselves
docs/generated/  produced by commands, never edited by hand (a test fails when stale)
```

## Non-negotiables

1. **Respect layer boundaries and the public API.** `uv run poe arch` explains each violation
   and its fix. An app uses only the library's public modules (`[package] public`): the package
   root and its facades. A rule changes in `harness.toml` and ARCHITECTURE.md together (ARCH-DOC
   checks the layer table), with the reason in a decision (review).
2. **Parse at the boundaries.** Input from outside (requests, env, files, model output, database
   rows) becomes typed pydantic models. Never build on guessed shapes.
3. **Structured logs only**, via `core.logging.get_logger`. No `print`, and never log secrets.
4. **Never read or print `.env`**, and tests never touch the developer's `.env`, shell
   settings, or `var/`. Nothing modifies or wipes data the owner put there (GP-21).
5. **Tests with every behavior change.** Security changes also need adversarial tests.

## Definition of done

- `uv run poe check` passes.
- Docs affected by the change are updated. The docs check catches broken links and orphans,
  not stale content, so keeping content current is on you.
- The active plan's progress and decision logs are updated, and finished plans move to
  `docs/plans/completed/`.
- A mistake that could recur is encoded as a test, check, or doc, and noted in the plan.
