"""actions: the backend, the only part of the system that acts: it runs the read tools the
talker asks for and, after a clear yes, each confirmed action as a job, keeps each call's record
of the actions it completed, and words every outcome from a real result.

It reaches the outside world only through domain's ports, injected by the api layer, and imports
neither the talker nor the voice pipeline. ARCHITECTURE.md's "Layers" maps the layers and what
each owns; each module's docstring says what it holds.
"""
