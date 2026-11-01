"""The evaluation helpers a team scores its own golden set with (D-022): error rates, recall of
terms and IDs, text from silence, and the sign test by item. Provisional (D-021). A facade: it
only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.domain.recall import Recall
from t2_agentic_voice.domain.scoring import id_recall, silence_output, term_recall
from t2_agentic_voice.domain.sign_test import sign_test
from t2_agentic_voice.testing.scorers import cer, wer

__all__ = [
    "Recall",
    "cer",
    "id_recall",
    "sign_test",
    "silence_output",
    "term_recall",
    "wer",
]
