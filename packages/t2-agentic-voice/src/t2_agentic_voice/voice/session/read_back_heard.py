"""What the caller says over an action's read-back that lets it play on (read_back.py's "What is
heard over it"; D-081; D-108), for overlap.py, which takes such a transcript as a listening
sound, whatever the interruption rule would say, so the read-back plays on (`plays_on`).

- **Ignored** (D-081, amended 2026-11-11): yes words, send words, fillers and listening sounds
  whose speech began over the summary, with no stop or wait word of the call's (as the rule
  reads them: domain/interruptions.py's `holds_stop`), a word on both lists included (khalas,
  enough, an Arabic stop word and a filler to the yes rule, which the rule judges as any stop
  word): the summary plays on, and the words count for nothing.
- **Under `interruptions.yes_over_read_back`** (D-108), off by default, for speech begun once
  the summary could first be heard (`since_summary`; read_back_times.py's `began`), whose turn
  is then the yes rule's (`takes`):
  - khalas beside a yes or a send word, with only yes words, send words, fillers and listening
    sounds else (`okay`), over the summary or the closing question, is no stop: it plays on,
    and its turn is the yes rule's (held_yes.py over the summary, yes_turns.py over the
    question); khalas alone still stops it;
  - for an agent that asks (`Confirming.asks`), words over the summary that the lists leave
    unplaced (`unplaced`: a word on none of them, and no no word, question mark, change marker
    or command said whole, so a repeat request is said again as before) play on too, and the
    turn's own words go to a chat model (held_yes.py).
"""

from __future__ import annotations

from t2_agentic_voice.core.events import ReplyId
from t2_agentic_voice.domain.interruption_words import QUESTION_MARKS
from t2_agentic_voice.domain.interruptions import holds_stop, whole_command
from t2_agentic_voice.domain.words import Words, rule_form
from t2_agentic_voice.domain.yes_kinds import OKAY_STOPS, holds_okay, kinds, marked
from t2_agentic_voice.domain.yes_words import ConsentWords, covered
from t2_agentic_voice.voice.session.read_back import Confirming


def takes(confirming: Confirming, speech_at: float | None, *, over: ReplyId | None) -> bool:
    """Whether a turn begun at `speech_at` that the agent's voice went on over is the yes rule's:
    it answers the current read-back (`Confirming.answering`), or is an overlap of its reply
    (`over`) begun over its summary (`since_summary`)."""
    read_back = confirming.read_back
    if read_back is None or speech_at is None or confirming.answering(speech_at):
        return confirming.answering(speech_at)
    return over == read_back.reply_id and since_summary(confirming, speech_at)


def since_summary(confirming: Confirming, speech_at: float) -> bool:
    """Under `interruptions.yes_over_read_back` only (D-108; held_yes.py): whether speech begun
    at `speech_at` began once the current read-back's summary could first be heard."""
    began = confirming.summary_began_at() if confirming.holds_yes else None
    return began is not None and began < speech_at


def plays_on(
    confirming: Confirming, reply_id: ReplyId, speech_at: float, text: str, *, words: Words
) -> bool:
    """Whether `text`, said over reply `reply_id` from `speech_at`, lets the current read-back
    play on (the module's docstring), `words` the call's, as the interruption rule reads them."""
    read_back = confirming.read_back
    if read_back is None or reply_id != read_back.reply_id:
        return False
    consent, listening = confirming.words(read_back.plan), words.backchannel
    since = since_summary(confirming, speech_at)
    if holds_stop(text, words=words):  # a stop or wait word is the rule's, but khalas (D-108)
        return since and okay(text, consent, words=words, listening=listening)
    if confirming.answering(speech_at):  # once the summary played: the yes rule's
        return False
    if covered(text, (*consent.yes, *consent.send, *consent.fillers, *listening)):
        return True
    return since and confirming.asks and unplaced(text, consent, words=words)


def okay(text: str, consent: ConsentWords, *, words: Words, listening: tuple[str, ...]) -> bool:
    """Whether `text` holds khalas (`OKAY_STOPS`) beside a yes or a send word of `consent`, no
    other stop or wait word of `words`, and only yes words, send words, fillers and `listening`
    sounds else."""
    form = rule_form(text)
    if not holds_okay(form):
        return False
    rest = " ".join(word for word in form.split() if word not in OKAY_STOPS)
    if holds_stop(rest, words=words):
        return False
    if not covered(form, (*consent.yes, *consent.send, *consent.fillers, *listening)):
        return False
    return bool(kinds(form, consent) & {"yes", "send"})


def unplaced(text: str, consent: ConsentWords, *, words: Words) -> bool:
    """Whether `text` holds a word on none of `consent`'s lists, and no no word, question mark
    or change marker of them, and is no command said whole (`whole_command`, `words` the call's):
    words a chat model judges (held_yes.py)."""
    form = rule_form(text)
    if not form or any(mark in text for mark in QUESTION_MARKS):
        return False
    if whole_command(text, words=words) is not None:
        return False
    found = kinds(form, consent)
    return "content" in found and "no" not in found and not marked(form, consent.change)
