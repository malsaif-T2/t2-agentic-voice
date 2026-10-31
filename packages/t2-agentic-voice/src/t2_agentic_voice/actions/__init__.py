"""actions: the backend, the only part of the system that acts.

It runs the tools the talker asks for (a knowledge search, a ticket's status, the ticket flow, a
handoff), keeps each call's record of the actions it completed, and words every outcome from a
real result. It reaches the outside world only through domain's ports, injected by the api
layer, and imports neither the talker nor the voice pipeline.
"""
