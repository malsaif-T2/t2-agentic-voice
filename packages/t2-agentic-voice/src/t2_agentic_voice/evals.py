"""The evaluation helpers a team scores its own golden set with (D-022): error rates, recall of
terms and IDs, text from silence, and the sign test by item; and the measurements of the
file-fed pipeline, where a call's turns end and how long each step of an echo call takes (plan
003's decision log), with the phrase audio an echo call plays (`PhraseAudio`, which the `stores`
facade's `PhraseCache` meets); and the replay of a clip over a reply (`AudioCall`, the design's
9.5), each overlap's verdict, requests and stop time (plan 005), or of a clip as a turn,
its time to first audio (`TurnReplay`); and the call held in text
(`TextCall`, the design's 9.2) with the fakes it runs on (the fake chat models, their script's
steps and pauses, and the failure of a script that ran out), what each of its turns did, as
data (plan 006), and `ActionSafetySuite` (the design's 9.3), until the testing kit is a public
module of its own (the design's 5.1); and the chat model's requests a call makes of its own, an
uncertain overlap's (D-069) and the yes rule's check of an answer its lists leave unplaced
(D-082), so a fake or a measurement tells them apart and answers them; and each turn's language
in a file-fed call of an agent of two languages, with the rule read back for any call's
language (`turn_languages`, `chosen`; plan 007's Block H, run H).
Provisional (D-021). A facade: it only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.domain.consent_check import (
    consent_check_answer,
    consent_check_request,
    is_consent_check,
)
from t2_agentic_voice.domain.recall import Recall
from t2_agentic_voice.domain.scoring import id_recall, silence_output, term_recall
from t2_agentic_voice.domain.sign_test import sign_test
from t2_agentic_voice.domain.turn_language import LanguageChoice
from t2_agentic_voice.domain.uncertain_overlaps import (
    uncertain_overlap_answer,
    uncertain_overlap_request,
)
from t2_agentic_voice.testing.action_safety import ActionSafetySuite
from t2_agentic_voice.testing.audio_call import AudioCall, OverlapReplay, OverlapRequest
from t2_agentic_voice.testing.echo_timing import EchoTiming, TurnTiming, echo_timings
from t2_agentic_voice.testing.knowledge_fake import FakeKnowledgeBase, KnowledgeSearch
from t2_agentic_voice.testing.llm_fakes import (
    FunctionLLM,
    Pause,
    ScriptedLLM,
    ScriptExhaustedError,
    ScriptStep,
)
from t2_agentic_voice.testing.scorers import cer, wer
from t2_agentic_voice.testing.text_call import TextCall, TextTurn, TurnExpectations
from t2_agentic_voice.testing.turn_data import BlockedClause, HeardClause, TextToolCall
from t2_agentic_voice.testing.turn_languages import LanguageTurn, chosen, turn_languages
from t2_agentic_voice.testing.turn_replay import TurnReplay
from t2_agentic_voice.testing.turns import TurnEnd, turn_ends
from t2_agentic_voice.voice.session.io import PhraseAudio

__all__ = [
    "ActionSafetySuite",
    "AudioCall",
    "BlockedClause",
    "EchoTiming",
    "FakeKnowledgeBase",
    "FunctionLLM",
    "HeardClause",
    "KnowledgeSearch",
    "LanguageChoice",
    "LanguageTurn",
    "OverlapReplay",
    "OverlapRequest",
    "Pause",
    "PhraseAudio",
    "Recall",
    "ScriptExhaustedError",
    "ScriptStep",
    "ScriptedLLM",
    "TextCall",
    "TextToolCall",
    "TextTurn",
    "TurnEnd",
    "TurnExpectations",
    "TurnReplay",
    "TurnTiming",
    "cer",
    "chosen",
    "consent_check_answer",
    "consent_check_request",
    "echo_timings",
    "id_recall",
    "is_consent_check",
    "sign_test",
    "silence_output",
    "term_recall",
    "turn_ends",
    "turn_languages",
    "uncertain_overlap_answer",
    "uncertain_overlap_request",
    "wer",
]
