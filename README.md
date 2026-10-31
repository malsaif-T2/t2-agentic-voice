# T2 Agentic Voice

A Python library for speech-first voice agents that T2's teams install in their own products: a
live call in the browser, natural turn-taking and interruptions, answers from the product's own
knowledge, and actions taken only after a clear spoken yes, in Saudi Arabic, MSA and English.
Its first app is the **Ole5 Voice Agent**, a voice support assistant for Ole5, built here on the
library's public API.

| Folder | What it is |
| --- | --- |
| [packages/t2-agentic-voice](packages/t2-agentic-voice) | The library (`import t2_agentic_voice`) |
| [apps/ole5-voice-agent](apps/ole5-voice-agent) | The Ole5 Voice Agent (`import ole5_voice`) |
| [examples/minimal](examples/minimal) | The smallest app: the quickstart |
| [docs/guide](docs/guide/README.md) | How teammates use the library |

Built by an AI coding agent while the owner steers (harness engineering). The agent's entry
point is [CLAUDE.md](CLAUDE.md), a map to everything else; the idea is in
[DESCRIPTION.md](docs/project/DESCRIPTION.md).

## Quickstart (working on this repository)

Needs [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 itself).

```
uv sync                 # every package of the workspace, from the lockfile
cp .env.example .env    # local settings; .env is never committed
uv run poe check        # the full gate: lint, types, arch, docs, test
uv run poe              # every task
```

## How the work is organized

- [docs/plans/roadmap.md](docs/plans/roadmap.md): the milestones, and the plans behind them.
- [docs/design/decisions.md](docs/design/decisions.md): why things are the way they are.
- [docs/design/package-design.md](docs/design/package-design.md): what the library provides
  and what an app provides.
- [WORKING-RULES.md](WORKING-RULES.md): how the agent works with the owner.
- [harness.toml](harness.toml): the rules the checks enforce.
