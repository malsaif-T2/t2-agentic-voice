# Tech-debt tracker

Pay debt down continuously, in small increments.

- Debt found along the way goes here, not into chat. A row says where it was found (for
  example "found in plan NNN's review"), why it matters, and the fix proposed.
- IDs are `TD-NNN` and never reused. A row is removed when the debt is paid; git keeps the
  history. Living docs must then stop citing it (DOC-REF fails on a citation of a removed
  row), which is intended: it forces the reference to be cleaned up.
- Every [garbage-collection round](../harness/garbage-collection.md) reviews every row: pays
  the ones that became cheap, and brings the others up to date.

`uv run poe docs` reads the rows below as `| TD-NNN |` at the start of a line, so keep that
shape.

| ID | Debt | Why it matters | Proposed fix |
| --- | --- | --- | --- |
