"""One variant's answer from the transcripts of its segments, as the speech-to-text answerer of
`poe eval` (`groq_answerer.py`) joins them: `combined`, with `by_length`, the length-weighted
mean of a value the segments give."""

from __future__ import annotations

from collections.abc import Sequence

from t2_agentic_voice.ports import Transcript

from ole5_voice.evals.runs import Answer, Request, SegmentAnswer


def combined(
    variant: str, parts: Sequence[tuple[float, Transcript]], requests: tuple[Request, ...]
) -> Answer:
    """One variant's answer from its segments' transcripts, joined with a space; for a variant
    of several, each segment's own answer too, and the language of the longest."""
    text = " ".join(t.text.strip() for _, t in parts if t.text.strip())
    if len(parts) == 1:
        only = parts[0][1]
        return Answer(
            variant=variant,
            text=text,
            language=only.language,
            confidence=only.confidence,
            no_speech_prob=only.no_speech_prob,
            requests=requests,
        )
    return Answer(
        variant=variant,
        text=text,
        language=max(parts, key=lambda part: part[0])[1].language,
        confidence=by_length([(s, t.confidence) for s, t in parts]),
        no_speech_prob=by_length([(s, t.no_speech_prob) for s, t in parts]),
        segments=tuple(
            SegmentAnswer(
                text=t.text,
                language=t.language,
                confidence=t.confidence,
                no_speech_prob=t.no_speech_prob,
            )
            for _, t in parts
        ),
        requests=requests,
    )


def by_length(values: Sequence[tuple[float, float | None]]) -> float | None:
    """The mean of a value over the segments that have one, each weighted by its length, as the
    prototype weighs Whisper's segments (`Ole5-chatbot/src/ole5_chat/voice/stt.py`, lines
    249-252); None when none has one."""
    known = [(seconds, value) for seconds, value in values if value is not None]
    total = sum(seconds for seconds, _ in known)
    return sum(seconds * value for seconds, value in known) / total if total else None
