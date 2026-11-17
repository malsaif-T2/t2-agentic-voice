"""The `stt` group: speech-to-text, and the filter for text from silence (plan 005), on by
default since the registered rule F held on plan 002's runs R1 and R3 (GP-18); the Whisper
prompt each request sends, on by default since run W kept its arm W1 (plan 006, Q23); and the
spoken-language classifier of `live_language = "classified"`, off by default, since run H kept
no arm (D-086, as amended on 2026-11-12); and `live_language = "hinted"`, one request a turn
whose answer's language and probability move the call (D-115), off by default until run H's
Scribe arms are measured (GP-18)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field

from t2_agentic_voice.core.settings.base import Group

# The speech-to-text adapters a setting picks: ElevenLabs' Scribe v3, the default by the owner's
# ruling (D-105); Groq's Whisper, the fallback; and the other providers measured beside them
# (D-100), each needing its own key group's key.
SttProvider = Literal["groq", "elevenlabs", "speechmatics", "cohere", "soniox", "telnyx", "nabrah"]
# The providers that report no language they heard (Speechmatics' ar_en pack, Cohere's Arabic
# model, Telnyx's streamed HUMAIN engine, Nabrah's Saudi model), so a request naming none detects
# nothing: under `live_language = "detected"` their calls send no second request, and keep the
# call's language until a switch request or the talker moves it.
HEARS_NO_LANGUAGE: frozenset[SttProvider] = frozenset(
    {"speechmatics", "cohere", "telnyx", "nabrah"}
)
# The providers whose answer gives the language heard with its probability (ElevenLabs'
# `language_code` and `language_probability`): only on them does `live_language = "hinted"`
# move a call; on any other it runs as `session` (D-115).
REPORTS_PROBABILITY: frozenset[SttProvider] = frozenset({"elevenlabs"})
SttModel = Literal["whisper-large-v3", "whisper-large-v3-turbo"]
# The least Groq bills a transcription request, in seconds, however short its audio (its
# pricing, read 2026-11-01; the design's 10.4): the adapter's billed seconds, the session's
# usage and the echo timings count it so.
WHISPER_MIN_BILLED_S = 10.0
# The language a live call sends Whisper: the session's, none (for Whisper to detect), each
# turn's from a spoken-language classifier, the call's current one with a second request of a
# long turn naming none, whose language moves the call (D-038's amendment), or the call's current
# one as a hint with the agent's other languages beside it, the answer's language and probability
# moving the call (D-115).
LiveLanguage = Literal["session", "auto", "classified", "detected", "hinted"]
# The spoken-language classifier: Silero's 95 languages on onnxruntime, or ECAPA on VoxLingua107,
# which runs on torch through SpeechBrain, the library's `ecapa` extra.
Classifier = Literal["silero", "ecapa"]


class SttSettings(Group):
    """Speech-to-text: the adapter, the Whisper model, how long a request may take, the
    language and the prompt a call sends, the classifier of each turn's language, and the
    filter for text from silence."""

    provider: SttProvider = Field(
        default="elevenlabs",
        description=(
            "Which adapter turns speech into text: elevenlabs (Scribe v3, the default, D-105; it "
            "needs T2V_ELEVENLABS__API_KEY), groq (Whisper, the fallback, on the Groq key alone), "
            "or one measured beside them (D-100): speechmatics (its ar_en pack, a batch "
            "job), cohere (Transcribe Arabic, the language always named), soniox "
            "(stt-async-v6, a batch job), telnyx (the model telnyx.stt_model names, HUMAIN's "
            "Arabic engine by default, a turn on its WebSocket) or nabrah (its Saudi Arabic "
            "model, a turn on its WebSocket); a provider with no key set is refused when "
            "chosen, naming its key's setting."
        ),
    )
    model: SttModel = Field(
        default="whisper-large-v3",
        description=(
            "The Whisper model: whisper-large-v3 or whisper-large-v3-turbo. The default stayed "
            "large-v3 on a registered measurement (D-025), and changes only on another (GP-18)."
        ),
    )
    timeout_s: float = Field(
        default=6.0,
        gt=0,
        allow_inf_nan=False,
        description="The longest one transcription request may take before it is a timeout.",
    )
    live_language: LiveLanguage = Field(
        default="session",
        description=(
            "The language a live call sends Whisper: session (the call's language, fixed when "
            "it joins from the caller's pick or the join token's locale), auto (none, so "
            "Whisper detects it) or classified (each turn's, chosen among the agent's languages "
            "by the classifier `stt.classifier` names from the turn's first "
            "`stt.classifier_from_s` seconds; a short, unsure, late, busy or failed turn keeps "
            "the language last classified, the call's until one is) or detected (each request "
            "names the call's current language, and a turn with `stt.detect_from_s` seconds of "
            "voiced speech or more is also sent naming none, at the same time: when Whisper "
            "hears the agent's other language in a question or request, never a short reply, "
            "that transcript is the turn's and the call moves to that language; on speechmatics, "
            "cohere, telnyx or nabrah, which report no language heard, no second request goes, "
            "and only a switch request or the talker moves the call) or hinted (each turn's one "
            "request names the call's current language as a hint and the agent's other "
            "languages beside it, which Scribe v3 takes as secondary languages; when the answer "
            "gives one of the agent's other languages with a probability of at least "
            "`stt.switch_min_probability`, in a question or request, never a short reply, the "
            "call moves to it, and a switch request or the talker moves it too; on a provider "
            "that gives no language probability, every one but elevenlabs, it runs as session, "
            "which the runtime's start logs). A registered measurement sets the default (GP-18)."
        ),
    )
    detect_from_s: float = Field(
        default=1.2,
        gt=0,
        le=30,
        allow_inf_nan=False,
        description=(
            "Under live_language detected, the seconds of voiced speech a turn needs, from "
            "where the speech detector heard it begin to where it last heard it stop (never "
            "the silence after), for its second request naming no language; a shorter turn "
            "keeps the call's current language. 1.2, registered for run H (D-038's amendment)."
        ),
    )
    switch_min_probability: float = Field(
        default=0.8,
        gt=0,
        le=1,
        allow_inf_nan=False,
        description=(
            "Under live_language hinted, the least probability the provider must give the "
            "language it heard, one of the agent's other languages, for the turn to move the "
            "call (with a question or request, never a short reply); under it the call keeps "
            "its language. 0.8, a placeholder until run H's Scribe arms are measured (GP-18)."
        ),
    )
    classifier: Classifier = Field(
        default="silero",
        description=(
            "The spoken-language classifier under live_language classified: silero (Silero's "
            "95 languages, on onnxruntime) or ecapa (ECAPA on VoxLingua107, on torch through "
            "SpeechBrain, which needs the library's ecapa extra: uv sync --group language-id "
            "in this workspace)."
        ),
    )
    classifier_dir: Path | None = Field(
        default=None,
        description=(
            "The folder of the classifier's model files, fetched once by hand as the guide's "
            "languages page says and each checked against its pinned SHA-256 at every start and "
            "by t2v doctor; never under a repository or var/. No default: live_language "
            "classified is refused at start without it."
        ),
    )
    classifier_from_s: float = Field(
        default=2.0,
        gt=0,
        le=30,
        allow_inf_nan=False,
        description=(
            "The seconds of a turn's audio, from where the speech detector heard its speech "
            "begin, that the classifier hears; pauses inside the turn count. A turn whose "
            "request goes with less keeps the current language (short). 2.0, registered for "
            "run H (plan 007, Q20)."
        ),
    )
    classifier_min_share: float = Field(
        default=0.7,
        gt=0,
        le=1,
        allow_inf_nan=False,
        description=(
            "The best share of the agent's languages the classifier must give a turn to move "
            "the call's current language; under it the turn keeps it (unsure). 0.7, registered "
            "for run H (plan 007, Q20)."
        ),
    )
    classifier_threads: int = Field(
        default=2,
        ge=1,
        le=64,
        description=(
            "The CPU threads the classifier's model runs on; one classification runs at a time "
            "a process, and a turn that finds it busy keeps the current language (busy)."
        ),
    )
    no_speech_max: float | None = Field(
        default=0.55,
        ge=0,
        le=1,
        allow_inf_nan=False,
        description=(
            "The no-speech probability Whisper reports above which a transcript counts as no "
            "words (text from silence), for a turn and for speech over a reply, from 0 to 1; "
            "unset, the threshold is off. 0.55 by the registered rule F and its one revision "
            "(plan 005), which changes only on another registered measurement (GP-18)."
        ),
    )
    caption_filter: bool = Field(
        default=True,
        description=(
            "Whether a transcript that is one of the captions Whisper invents for silence or "
            "noise counts as no words; on by the registered rule F (plan 005), which changes "
            "only on another registered measurement (GP-18)."
        ),
    )
    send_prompt: bool = Field(
        default=True,
        description=(
            "Whether each speech-to-text request of a call sends Whisper the prompt of the "
            "language it names: the agent's vocabulary, then the command words as they should "
            "be written. On since run W's arm W1 (plan 006), which on the golden set raised "
            "Whisper's right count beyond the noise on dev (stop words 0.69 to 0.92, repeat "
            "requests 0.32 to 0.53) and on held-out (accuracy 0.382 to 0.420, word errors "
            "0.254 to 0.218, stop words 0.778 to 0.889); it changes only on another registered "
            "measurement (GP-18)."
        ),
    )

    def hints(self) -> bool:
        """Whether `live_language = "hinted"` holds on this provider: it gives the language it
        heard with its probability (`REPORTS_PROBABILITY`); on any other, hinted runs as
        `session` (D-115)."""
        return self.live_language == "hinted" and self.provider in REPORTS_PROBABILITY

    def language_moves(self) -> bool:
        """Whether a call's language may move within the call (D-103): under `detected`, and
        under `hinted` where it holds (`hints`); never under any other setting."""
        return self.live_language == "detected" or self.hints()
