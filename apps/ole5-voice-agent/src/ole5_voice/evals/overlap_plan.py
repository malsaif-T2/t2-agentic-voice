"""What a `poe overlap` run plays (`overlap.py`; plan 005's registration, the arm O): the overlap
clips of its split, each with the reply it is played over and the language its call is held in;
and the settings it runs under, every one given on its command line.

**The clips**: the checked variants of the split that overlap_score.py's `in_set` takes, each
with what its kind should do and its labelled word end (the first of `turn_ends_ms`); and the
smoke test's, the plan's smoke variant, played over its reply as they are (`overlap_of`).

**The reply** each is played over: the texts that played over it when it was recorded, where
they are known (the registration's "where they are known"): a script line's reply, by its ID in
the lab's `replies.json` (its `spoken` text, or its `text`; `--replies` names its folder), and an
imported call's overlap, from `overlap_replies.json` (import_calls.py); otherwise
`DEFAULT_REPLY` in its language, a text no clip holds. A run of the replay refuses a script line
whose reply `--replies` does not hold, so no clip known to have been said over a reply is
measured over another; the reference reads no reply. The call is held in the item's language
(Saudi and mixed in Saudi Arabic, MSA in Modern Standard Arabic, English in English, as plan
003's T1 sends it), or for an item with no speech, its reply's, Saudi Arabic when that is not
known.

**The settings** (`with_set`): each `--set GROUP.NAME=VALUE` on top of the settings `poe eval`
loads, its value read as JSON where it is JSON (`0.5`, `true`, `null`) and as text otherwise,
and `interruptions.mode` `two_step` whatever was given, since the arm measures that rule.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, TypeAdapter
from t2_agentic_voice import ConfigurationError, VoiceSettings

from ole5_voice.evals.files import read_model
from ole5_voice.evals.models import Name
from ole5_voice.evals.overlap_run import Overlap, Tag
from ole5_voice.evals.overlap_score import EXPECTED, in_set
from ole5_voice.evals.run_parts import Todo
from ole5_voice.evals.takes import ScriptLine
from ole5_voice.evals.timing_run import TAGS
from ole5_voice.evals.worktree import refused

# The reply a clip whose own is not known is played over, by the language its call is held in:
# a text no clip holds, of words no listed word is within one edit of (the agent's).
DEFAULT_REPLY: Final[Mapping[Tag, str]] = {
    "ar-SA": "تتغير ألوان الحقول الشمالية ببطء تحت سحب الخريف الرمادية",
    "ar": "تتغير ألوان الحقول الشمالية ببطء تحت سحب الخريف الرمادية",
    "en": "Northern orchards ripen slowly beneath grey autumn clouds every season.",
}
REPLIES_JSON: Final = "replies.json"


class LabReply(BaseModel):
    """One reply of the lab's `replies.json`: the fields a run reads; it ignores the rest."""

    model_config = ConfigDict(frozen=True, extra="ignore", hide_input_in_errors=True)

    id: Name
    lang: str = ""
    spoken: str = ""  # the text as the agent said it
    text: str = ""  # as it was written

    @property
    def said(self) -> str:
        return " ".join((self.spoken or self.text).split())


_LAB: Final = TypeAdapter(list[LabReply])


def read_lab_replies(folder: Path) -> dict[str, LabReply]:
    """The lab's replies in `folder`'s `replies.json`, by ID, or the run's refusal."""
    found = read_model(
        folder / REPLIES_JSON,
        _LAB,
        lambda problem: refused(f"{REPLIES_JSON}: {problem}", "give --replies the lab's folder"),
    )
    return {reply.id: reply for reply in found}


def overlaps_of(
    todo: Sequence[Todo],
    lines: Mapping[str, ScriptLine],
    lab: Mapping[str, LabReply] | None,
    called: Mapping[str, tuple[str, ...]],
) -> list[Overlap]:
    """The overlap clips among `todo`, each with its reply (`overlap_of`)."""
    return [
        overlap_of(each, lines, lab, called)
        for each in todo
        if in_set(each.item.kind, each.variant.tags)
    ]


def overlap_of(
    each: Todo,
    lines: Mapping[str, ScriptLine],
    lab: Mapping[str, LabReply] | None,
    called: Mapping[str, tuple[str, ...]],
) -> Overlap:
    """`each` as a clip over a reply, with its reply and its call's language; `lab` None for the
    reference answerer, which reads no reply. A smoke variant of a kind outside the set, whose
    verdict is never judged, is given `go_on`. The run's refusal for a script line whose reply
    `lab` does not hold, or holds with no text."""
    item, variant = each.item, each.variant
    reply: tuple[str, ...] = ()
    reply_lang = ""
    line = lines.get(item.id) if item.source == "script" else None
    if line is not None and line.reply is not None and lab is not None:
        known = lab.get(line.reply)
        if known is None or not known.said:
            raise refused(
                f"{REPLIES_JSON} holds no text of the reply {line.reply}",
                "give --replies the lab's folder whose replies.json names it",
            )
        reply, reply_lang = (known.said,), known.lang
    elif called.get(variant.id):
        reply = called[variant.id]
    tag: Tag = TAGS.get(item.language) or ("en" if reply_lang == "en" else "ar-SA")
    return Overlap(
        todo=each,
        expected=EXPECTED.get(item.kind, "go_on"),
        reply=reply or (DEFAULT_REPLY[tag],),
        reply_known=bool(reply),
        tag=tag,
        word_end_ms=float(variant.turn_ends_ms[0]) if variant.turn_ends_ms else None,
    )


def setting(text: str) -> tuple[str, object]:
    """An argparse type: `--set GROUP.NAME=VALUE`, its value read as JSON where it is JSON."""
    name, equals, value = text.partition("=")
    group, dot, field = name.partition(".")
    if not (equals and dot and group and field):
        raise argparse.ArgumentTypeError("give a setting as GROUP.NAME=VALUE")
    try:
        parsed: object = json.loads(value)
    except ValueError:
        parsed = value
    return name, parsed


def with_set(loaded: VoiceSettings, given: Sequence[tuple[str, object]]) -> VoiceSettings:
    """`loaded` with each `--set` on top and `interruptions.mode` `two_step`; the run's refusal,
    naming the setting and never its value, for a name or a value the settings do not take."""
    data = loaded.model_dump()
    for name, value in given:
        group, _, field = name.partition(".")
        values = data.get(group)
        if not isinstance(values, dict) or field not in values:
            raise refused(
                f"--set {name} names no setting", "name one of docs/generated/settings.md"
            )
        values[field] = value
    data["interruptions"]["mode"] = "two_step"
    try:
        checked = VoiceSettings.model_validate(data, context={"prefix": loaded.prefix})
    except ConfigurationError:
        named = ", ".join(name for name, _ in given)
        raise refused(
            f"a value of --set {named} is not one the settings take", "give one"
        ) from None
    return loaded.model_copy(update=dict(checked))
