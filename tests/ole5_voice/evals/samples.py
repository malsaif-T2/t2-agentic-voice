"""Made-up, valid instances of the golden set's models (plan 002, Block 0), for any track's
tests: an item with one variant, a run, and its history line. Fixed values, no clock (GP-12)."""

from __future__ import annotations

from datetime import UTC, datetime

from ole5_voice.evals.models import AudioRef, HistoryLine, Item, RunInfo, Variant

SHA = "0123456789abcdef" * 4
WHEN = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


def variant(variant_id: str = "v1", reference: str = "stop now") -> Variant:
    return Variant(
        id=variant_id,
        segments=(AudioRef(root="owner", path=f"laptop/{variant_id}.wav", sha256=SHA),),
        device="laptop",
        session="laptop-1",
        reference=reference,
        reference_source="script",
    )


def item(item_id: str = "i1", text: str = "stop now") -> Item:
    return Item(
        id=item_id,
        source="script",
        kind="stop_word",
        language="english",
        text=text,
        variants=(variant(reference=text),),
    )


def run(name: str = "r1") -> RunInfo:
    return RunInfo(
        name=name,
        started_at=WHEN,
        commit="0f44056",
        answerer="reference",
        split="dev",
        settings={"stt.model": "whisper-large-v3", "groq.api_key": "not set"},
        data_digest=SHA,
        note="a made-up run",
    )


def history_line(name: str = "r1") -> HistoryLine:
    return HistoryLine(
        time=WHEN,
        commit="0f44056",
        run=name,
        answerer="reference",
        settings={},
        split="dev",
        items=1,
        variants=1,
        accuracy=1.0,
        violations=0,
        billed_seconds=0.0,
        cost_usd=0.0,
        latency_median_ms=None,
        breakdowns={},
        scorecard="scorecard.json",
        data_digest=SHA,
        note="a made-up run",
        complete=True,
    )
