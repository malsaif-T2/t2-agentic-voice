"""The evaluation helpers a team scores its own golden set with (D-022): error rates, recall of
terms and IDs, text from silence, and the sign test by item; and the measurements of the
file-fed pipeline, where a call's turns end and how long each step of an echo call takes (plan
003's decision log), with the phrase audio an echo call plays (`PhraseAudio`, which the `stores`
facade's `PhraseCache` meets); and the replay of a clip over a reply (`AudioCall`, the design's
9.5), each overlap's verdict, requests and stop time (plan 005); and the call held in text
(`TextCall`, the design's 9.2) with the fakes it runs on (plan 006), until the testing kit is a
public module of its own (the design's 5.1). Provisional (D-021). A facade: it only re-exports
(ARCH-FACADE)."""

from t2_agentic_voice.domain.recall import Recall
from t2_agentic_voice.domain.scoring import id_recall, silence_output, term_recall
from t2_agentic_voice.domain.sign_test import sign_test
from t2_agentic_voice.testing.audio_call import AudioCall, OverlapReplay, OverlapRequest
from t2_agentic_voice.testing.echo_timing import EchoTiming, TurnTiming, echo_timings
from t2_agentic_voice.testing.knowledge_fake import FakeKnowledgeBase, KnowledgeSearch
from t2_agentic_voice.testing.llm_fakes import FunctionLLM, ScriptedLLM
from t2_agentic_voice.testing.scorers import cer, wer
from t2_agentic_voice.testing.text_call import TextCall, TextTurn, TurnExpectations
from t2_agentic_voice.testing.turns import TurnEnd, turn_ends
from t2_agentic_voice.voice.session.io import PhraseAudio

__all__ = [
    "AudioCall",
    "EchoTiming",
    "FakeKnowledgeBase",
    "FunctionLLM",
    "KnowledgeSearch",
    "OverlapReplay",
    "OverlapRequest",
    "PhraseAudio",
    "Recall",
    "ScriptedLLM",
    "TextCall",
    "TextTurn",
    "TurnEnd",
    "TurnExpectations",
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
