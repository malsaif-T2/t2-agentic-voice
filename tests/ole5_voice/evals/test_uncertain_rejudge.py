"""The stored overlaps judged again (uncertain_rejudge.py): the speech-to-text that answers each
request with the stored run's transcript of it, and when a replay reproduced the stored run."""

from __future__ import annotations

import asyncio

from ole5_voice.evals.overlap_score import Heard, Part, Verdict
from ole5_voice.evals.uncertain_rejudge import StoredSpeech, reproduced
from t2_agentic_voice.ports import AudioClip


def _heard(part: Part, turn: int = 0, text: str | None = "made-up words") -> Heard:
    return Heard(turn_id=turn, part=part, sent_ms=500.0, audio_s=0.75, text=text)


def _verdict(*asked: Heard, by: Part | None = "window", turn: int | None = 0) -> Verdict:
    return Verdict(opened=True, decided_by=by, decided_turn=turn, requests=asked)


def test_the_stored_speech_answers_each_request_in_order_and_then_with_no_words() -> None:
    speech = StoredSpeech()
    speech.heard = [_heard("window", text="وقف"), _heard("overlap", text=None)]
    clip = AudioClip(pcm16=b"\x00\x00" * 160)

    async def asked() -> list[tuple[str, str | None]]:
        found = [await speech.transcribe(clip, language="ar", prompt=None) for _ in range(3)]
        await speech.aclose()
        return [(each.text, each.language) for each in found]

    assert asyncio.run(asked()) == [("وقف", "ar"), ("", "ar"), ("", "ar")]
    assert speech.name == "stored" and speech.data_flow.stored_in == "nowhere"


def test_a_replay_is_reproduced_when_its_requests_to_the_deciding_one_are_the_stored_runs() -> None:
    stored = (_heard("window"), _heard("overlap"), _heard("turn"))
    assert reproduced(_verdict(_heard("window"), _heard("turn")), stored)  # after it: no matter
    assert reproduced(_verdict(*stored, by="overlap"), stored)
    assert not reproduced(_verdict(_heard("overlap"), _heard("window"), by="overlap"), stored)
    assert not reproduced(_verdict(_heard("window"), turn=1), stored)  # decided by none asked
    assert reproduced(_verdict(_heard("window"), by=None, turn=None), stored)  # none decided
    extra = (*stored, _heard("window", turn=1))
    assert not reproduced(_verdict(*extra, by=None, turn=None), stored)
