# Quality by layer

How good each part of the code is, measured the same way every time, so a round of cleanup can
see where it matters and whether it worked ([PRINCIPLES](PRINCIPLES.md), section 5).

`uv run poe quality` grades each layer of the package (the layers in `harness.toml`), and
`scripts/`, after a test run (`uv run poe check` writes the coverage data it reads). It is not a
gate.

| Signal | Measures | Weight |
| --- | --- | --- |
| Coverage | the share of the layer's statements the tests run | 40 |
| Size | the share of its modules within the size watch (below the hard limit `poe arch` enforces) | 20 |
| Suppressions | `noqa`, `type: ignore`, and `pragma: no cover` per 1,000 lines; 10 or more scores zero | 15 |
| Duplication | repeated runs of code that touch the layer (`poe gc`'s detector); 5 or more scores zero | 15 |
| Docstrings | the share of its modules that say what they are for | 10 |

The weights and the two zero points are set in `harness.toml` (`[quality]`), and the size watch
is `[gc] size_watch`. The score is out of 100. Without coverage data, it is out of the other
signals. A grade is A from 90, B from 80, C from 70, and D below. The command lives in
`scripts/quality.py`. Every
[garbage-collection round](garbage-collection.md) updates the table below and writes each
layer's gaps in words: a number shows where to look, and only a reader knows why.

## Grades

`uv run poe gc` compares the current grades with the rows of this table, so keep each row's
first four cells in this shape: `| layer | **A** | score | coverage |`, with the letter in bold.

Not measured yet: the first `uv run poe quality` after the scaffold fills it.

| Layer | Grade | Score | Coverage | Modules within the size watch | Largest | Suppressions per 1,000 lines | Duplicate runs | Docstrings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Gaps

- (Each layer's gaps in words, refreshed every round.)
