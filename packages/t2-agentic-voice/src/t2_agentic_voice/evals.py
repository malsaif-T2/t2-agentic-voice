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
language (`turn_languages`, `chosen`; D-086, run H), and the rule that moves a call to the
language Whisper detected (`switch_to`, D-038's amendment), so a measurement applies it exactly;
and what every app's measurement run that spends shares (D-101): the paced, capped chat model
(`PacedChat`, its `ModelPacer` and `MinutePacer` on a `RunClock` and a `RunSleep`, its `Spend`
at each model's `Price`, each model's `ModelUse` and `ModelSpend`), the day's requests of one
key counted over every app's run history (`requests_today`, `every_history`), and the checks
before a run, the main checkout refused and an out folder that may not be lost or committed
(`run_checkout`, `check_out`); and the repeat measures of a call's replies, an identical or a
near repeat of an earlier reply and how much of a cut reply the next says again (`find_repeat`,
`Repeat`, `first_clause`, `token_overlap`, `cut_reply_share`, `repeats_cut_reply`), one
definition for every app's runs. Provisional (D-021). A facade: it only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.domain.consent_check import (
    consent_check_answer,
    consent_check_request,
    is_consent_check,
)
from t2_agentic_voice.domain.language_switch import switch_to
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
from t2_agentic_voice.testing.paced_chat import PacedChat
from t2_agentic_voice.testing.repeats import (
    Repeat,
    cut_reply_share,
    find_repeat,
    first_clause,
    repeats_cut_reply,
    token_overlap,
)
from t2_agentic_voice.testing.run_checkout import (
    Checkout,
    Git,
    GitResult,
    check_out,
    inspect_checkout,
    run_checkout,
    run_git,
    run_refused,
    worktree_tops,
)
from t2_agentic_voice.testing.run_history import RunHistoryError, every_history, requests_today
from t2_agentic_voice.testing.run_pacing import (
    DailyLimitError,
    Limits,
    MinutePacer,
    ModelPacer,
    RunClock,
    RunSleep,
)
from t2_agentic_voice.testing.run_spend import CapReachedError, ModelSpend, ModelUse, Price, Spend
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
    "CapReachedError",
    "Checkout",
    "DailyLimitError",
    "EchoTiming",
    "FakeKnowledgeBase",
    "FunctionLLM",
    "Git",
    "GitResult",
    "HeardClause",
    "KnowledgeSearch",
    "LanguageChoice",
    "LanguageTurn",
    "Limits",
    "MinutePacer",
    "ModelPacer",
    "ModelSpend",
    "ModelUse",
    "OverlapReplay",
    "OverlapRequest",
    "PacedChat",
    "Pause",
    "PhraseAudio",
    "Price",
    "Recall",
    "Repeat",
    "RunClock",
    "RunHistoryError",
    "RunSleep",
    "ScriptExhaustedError",
    "ScriptStep",
    "ScriptedLLM",
    "Spend",
    "TextCall",
    "TextToolCall",
    "TextTurn",
    "TurnEnd",
    "TurnExpectations",
    "TurnReplay",
    "TurnTiming",
    "cer",
    "check_out",
    "chosen",
    "consent_check_answer",
    "consent_check_request",
    "cut_reply_share",
    "echo_timings",
    "every_history",
    "find_repeat",
    "first_clause",
    "id_recall",
    "inspect_checkout",
    "is_consent_check",
    "repeats_cut_reply",
    "requests_today",
    "run_checkout",
    "run_git",
    "run_refused",
    "sign_test",
    "silence_output",
    "switch_to",
    "term_recall",
    "token_overlap",
    "turn_ends",
    "turn_languages",
    "uncertain_overlap_answer",
    "uncertain_overlap_request",
    "wer",
    "worktree_tops",
]
