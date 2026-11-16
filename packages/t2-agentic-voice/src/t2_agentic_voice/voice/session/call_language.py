"""The call's current language (`CallLanguage`, a call's `CallSetup.now`): the join's at first
(`CallSetup.language`) and, under `stt.live_language = "detected"` (D-038's amendment), the one
the caller moved the call to, in three ways:

- a turn the detecting request heard in the agent's other language, a question or request
  (`Transcribed.switched`): the speech-to-text bridge moved itself already
  (voice/stt_requests.py), and the session follows it;
- a spoken switch request (domain/language_switch.py's `asked_language`), the fast path;
- the talker's `switch_language` tool, for any other wording (actions/).

The session's notices, its fixed phrases, the echo, the overlap words and a reply's fallback
tag read it; a reply follows each turn's heard language (agent/language.py), and a turn that asked
for the move is answered in the language it asked for (`TalkerTurn.asked`). Under any other
`stt.live_language` the call never moves, as D-038 holds."""

from __future__ import annotations

from collections.abc import Sequence

from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import Language
from t2_agentic_voice.domain.language_switch import asked_language


class CallLanguage:
    """The call's current language, `language`, among `languages` (the agent's), the first of
    them at join; it moves only when `moves` (the module's docstring)."""

    def __init__(self, language: Language, languages: Sequence[Language], *, moves: bool) -> None:
        self.language, self.moves = language, moves
        self._languages = tuple(languages)

    @property
    def tag(self) -> LanguageTag:
        """The current language's tag."""
        return self.language.tag

    @property
    def spoken(self) -> list[LanguageTag]:
        """The tags of the agent's languages, in the agent's order."""
        return [each.tag for each in self._languages]

    def of(self, language: str | None) -> Language | None:
        """The agent's language of `language` (a tag or its primary code); None when the agent
        speaks no such language."""
        found = [each for each in self._languages if language in (each.tag, each.primary)]
        return found[0] if found else None

    def asked(self, text: str) -> Language | None:
        """The agent's language a spoken switch request in `text` asks for, when the call may
        move; None for a turn that asks for none (domain/language_switch.py's `asked_language`)."""
        return self.of(asked_language(text)) if self.moves else None

    def asked_tag(self, text: str) -> LanguageTag | None:
        """The tag of the language `text` asks for (`asked`); None for none."""
        asked = self.asked(text)
        return None if asked is None else asked.tag

    def move(self, language: str | None) -> Language | None:
        """Move the call to the agent's language of `language` (a tag or a code): that
        language when the call moved, None when it may not move, the agent speaks no such
        language, or the call is held in it already."""
        found = self.of(language) if self.moves else None
        if found is None or found.primary == self.language.primary:
            return None
        self.language = found
        return found
