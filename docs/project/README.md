# The owner's documents

This folder holds what the owner gives the project and what the project gives the owner:
the [description](DESCRIPTION.md) of what is being built, and, as the project grows, meeting
notes, reports, and snapshot overviews. Each kind has a convention, so a later reader can tell
what was said from what was inferred, and where every number came from.

Every document here is linked from this list (or from a document that is), since the docs check
fails on an orphan (DOC-ORPHAN):

- [DESCRIPTION.md](DESCRIPTION.md): what is being built, in the owner's terms.

## Meeting notes and the owner's messages

`meeting-YYYY-MM-DD.md`, written the day the owner relays a meeting or a long message.

- **Record it as the owner relayed it.** Their words are quoted, dated, and attributed (the
  owner, or who they report); a paraphrase says it is one. Nothing is added that nobody said
  (GP-16).
- **Then act on it, in the repository:** each decision becomes a `D-NNN` entry whose Evidence
  quotes the note; each change of direction re-plans the [roadmap](../plans/roadmap.md) (its
  Decided and Open questions sections); each task becomes a plan or a row in a plan. The note
  ends with a list of what it changed, each with its link.
- **Open points** stay listed as open, in the note and in the roadmap's open questions, until
  the owner answers.

## Reports for the owner

A milestone report (`mN-report.md`), a results report, or a status report, written when the
owner asks or a milestone closes.

- **Every number names its source:** the run, the scorecard file, or the command and its output
  that produced it. A number nobody measured is not written.
- **Separate what was measured from what is believed:** results first, with their noise or
  uncertainty when there is any; then the agent's reading, marked as its own; then what is
  left open, and the decisions the owner is asked to make.
- **Plain words:** written for a reader who did not follow the work; terms defined on first
  use; no internal names without a sentence that says what they are.

## Snapshot overviews

A document that explains the whole system in one read (for a newcomer, a reviewer, a meeting).
It opens with what it is a snapshot of: "As of commit `<hash>` (YYYY-MM-DD). Where it disagrees
with the sources of truth (the code, ARCHITECTURE.md, the decisions), they win." It is refreshed
on request, never edited piecemeal, and the next garbage-collection round checks it is still
labelled with its commit.

## Technical notes

Research and analysis the owner asked for (a comparison of options, a reading of a paper, a
diagnosis). Each claim carries its source in brackets: `[measured: <run or file>]`,
`[source: <title, author, section>]`, `[owner, YYYY-MM-DD]`, or `[agent's reading]`. A note on
someone else's work quotes at most a sentence and links to it (third-party rules:
[WORKING-RULES.md](../../WORKING-RULES.md)).
