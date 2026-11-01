"""Ole5's golden set and its measurement commands (evaluation.md; D-022).

The code is here; the data (items, manifests, the split, the strata, the history) is in
`apps/ole5-voice-agent/evals/`, and the audio is never in git. `models.py` holds the shapes
every part reads and writes, `audio.py` the WAV files; the commands `poe golden`, `poe eval`,
`poe eval-compare`, `poe eval-history` and `poe record` run `golden.py`, `run.py`,
`compare.py`, `history.py` and `recorder.py`. The library is reached only through its public
API (ARCH-PUBLIC).
"""
