"""Ole5's golden set and its measurement commands (evaluation.md; D-022).

The code is here; the data (items, manifests, the split, the strata, the history) is in
`apps/ole5-voice-agent/evals/`, and the audio is never in git. `models.py` holds the shapes
of the golden set, `runs.py` those of a run, `takes.py` the recorder's files and `audio.py` the
WAV files; `files.py` reads every file one way and `cli.py` parses what the commands share. The
commands `poe golden`, `poe eval`, `poe eval-compare`, `poe eval-history` and `poe record` run
`golden.py`, `run.py`, `compare.py`, `history.py` and `recorder.py`; `knowledge_set.py` reads
and checks the knowledge set, the requests the talker is measured on. The library is reached
only through its public API (ARCH-PUBLIC); the values it copies from the library are tied to
the library's own by `tests/ole5_voice/evals/test_library_copies.py`.
"""
