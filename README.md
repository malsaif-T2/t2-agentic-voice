# Ole5 Voice Agent

A voice-first support assistant for Ole5 that answers from the knowledge base and opens tickets only on a clear yes, in Saudi Arabic, MSA and English.

Built by an AI coding agent while the owner steers (harness engineering). The agent's entry
point is [CLAUDE.md](CLAUDE.md), a map to everything else; the idea is in
[DESCRIPTION.md](docs/project/DESCRIPTION.md).

## Quickstart

Needs [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 itself).

```
uv sync                 # the locked dependencies
cp .env.example .env    # local settings; .env is never committed
uv run poe check        # the full gate: lint, types, arch, docs, test
uv run poe              # every task
```

## How the work is organized

- [docs/plans/roadmap.md](docs/plans/roadmap.md): the milestones, and the plans behind them.
- [docs/design/decisions.md](docs/design/decisions.md): why things are the way they are.
- [WORKING-RULES.md](WORKING-RULES.md): how the agent works with the owner.
- [harness.toml](harness.toml): the rules the checks enforce.
