"""The language each clause of a reply is said in, under `tts.voice_by_script` (off by default,
GP-18; the flight app turns it on): a net for a reply the model wrote in a language its tag does
not say, which the clause gate reads (agent/clause_gate.py).

- **One way.** In a reply tagged `en`, a clause with more words in Arabic letters than in Latin
  ones (agent/language.py's `script_words`) is said in the agent's Arabic tag (`arabic_tag`:
  language.py's `tag_of`, the call's own when it is Arabic, `ar-SA` for the flight agent), with
  the caller's register, so its numbers are said in Saudi or MSA words as the call's are. A reply
  tagged Arabic is never moved: a Latin product name inside Arabic («flynas XY 299»,
  "Saudia Business Class") must never change the speaker.
- **Sticky.** A clause with no letter, or with as many words in each script, keeps the tag of
  the clause before it, so "14:00." after an Arabic sentence stays in the Arabic voice; a
  reply's first clause takes the reply's tag. Once the `switch_language` tool moved the reply
  (agent/turn.py), its clauses start again from the moved tag.
- **What follows it.** Each clause's `SpokenClause.language` and `caller_register`, and a
  blocked one's `ClauseBlocked.language`, so the failure notice is said in the clause's
  language; the session plays, counts, caches and says again each clause by that tag already
  (voice/session/talker_play.py, open_reply.py). The clause splitter, the leak check and the
  guard's rules stay on the reply's tag. An agent with no Arabic tag is unchanged.

Why: the owner's calls of 2026-11-22, where two Arabic replies to an English "How's it going with
you?" in an Arabic call went to orpheus-v1-english (109 characters in the call's usage): Arabic
letters for the English voice, its numbers said in English words. The line naming the reply's
language at the end of every request (`llm.reply_line_always`, agent/turn_request.py) cures
most of it; this catches the slip it does not prevent, at the cost of a word count a clause and
no model request. One way only: an English voice cannot say Arabic letters at all, while a Latin
name inside an Arabic sentence is part of that sentence, which one speaker says whole.
"""

from __future__ import annotations

from collections.abc import Sequence

from t2_agentic_voice.agent.language import script_words, tag_of
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import primary_code


def arabic_tag(on: bool, *, call: LanguageTag, spoken: Sequence[LanguageTag]) -> LanguageTag | None:
    """The tag an Arabic clause of an English reply is said in, in a call held in `call` by an
    agent that speaks `spoken`, when the setting is `on` (the module's docstring); None when it
    is off or the agent speaks no Arabic."""
    if not on:
        return None
    tag = tag_of("ar", call=call, spoken=spoken)
    return tag if primary_code(tag) == "ar" else None


class ClauseVoice:
    """The tag each clause of one reply in `language` is said in (the module's docstring);
    `arabic` is the tag an Arabic clause of an English reply moves to (`arabic_tag`), None for
    every clause in `language`."""

    def __init__(self, language: LanguageTag, arabic: LanguageTag | None = None) -> None:
        self.arabic = arabic
        self.language = self.last = language

    def moved(self, language: LanguageTag) -> None:
        """The reply goes on in `language`, which the `switch_language` tool moved it to: its
        next clause starts again from it."""
        self.language = self.last = language

    def of(self, clause: str) -> LanguageTag:
        """The tag `clause`, the reply's next, is said in."""
        if self.arabic is None or self.language != "en":
            return self.language
        arabic, latin = script_words(clause)
        if arabic != latin:
            self.last = self.arabic if arabic > latin else self.language
        return self.last
