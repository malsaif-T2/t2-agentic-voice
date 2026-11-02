"""The evaluation helpers a team scores its own golden set with (D-022): error rates, recall of
terms and IDs, text from silence, and the sign test by item; and the measurements of the
file-fed pipeline, where a call's turns end and how long each step of an echo call takes (plan
003's decision log). Provisional (D-021). A facade: it only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.domain.recall import Recall
from t2_agentic_voice.domain.scoring import id_recall, silence_output, term_recall
from t2_agentic_voice.domain.sign_test import sign_test
from t2_agentic_voice.testing.echo_timing import EchoTiming, TurnTiming, echo_timings
from t2_agentic_voice.testing.scorers import cer, wer
from t2_agentic_voice.testing.turns import TurnEnd, turn_ends

__all__ = [
    "EchoTiming",
    "Recall",
    "TurnEnd",
    "TurnTiming",
    "cer",
    "echo_timings",
    "id_recall",
    "sign_test",
    "silence_output",
    "term_recall",
    "turn_ends",
    "wer",
]
