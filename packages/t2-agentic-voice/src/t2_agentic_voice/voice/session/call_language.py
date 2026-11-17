"""The call's current language (`CallLanguage`, a call's `CallSetup.now`): the join's at first
(`CallSetup.language`) and, under `stt.live_language = "detected"` (D-038's amendment), the one
the caller moved the call to, in three ways:

- a turn the detecting request heard in the agent's other language, a question or request
  (`Transcribed.switched`): the speech-to-text bridge moved itself already
  (voice/stt_requests.py), and the session follows it;
- a spoken switch request (domain/language_switch.py's `asked_language`), the fast path;
- the talker's `switch_language` tool, for any other wording (actions/language_tool.py; the
  talker's `LanguageMoved`).

A move the bridge did not make itself is named to it after the step (`untold`, call.py). A
read-back said before a move is read again in the new language before it can be confirmed
(`moved_on`; read_back_moved.py).

The session's notices, its fixed phrases, the echo, the overlap words and a reply's fallback
tag read it; a reply follows each turn's heard language (agent/language.py), and a turn that asked
for the move is answered in the language it asked for (`TalkerTurn.asked`). Under `hinted` or
`single` where it holds (D-115, D-117) the call moves in the same three ways, the first by the
answer of the turn's one request (voice/stt_requests.py). Under any other `stt.live_language`
the call never moves, as D-038 holds."""

from __future__ import annotations

from collections.abc import Sequence

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.declaration import Language
from t2_agentic_voice.domain.language_switch import asked_language


class CallLanguage:
    """The call's current language, `language`, among `languages` (the agent's), the first of
    them at join; it moves only when `moves` (the module's docstring)."""

    def __init__(self, language: Language, languages: Sequence[Language], *, moves: bool) -> None:
        self.language, self.moves = language, moves
        self._languages = tuple(languages)
        self._told = language  # the language the speech-to-text bridge was last named
        self.moved_on: TurnId | None = None  # the turn the call last moved on

    @property
    def tag(self) -> LanguageTag:
        """The current language's tag."""
        return self.language.tag

    @property
    def primary(self) -> LanguageCode:
        """The current language's primary code."""
        return self.language.primary

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

    def move(self, language: str | None, *, on: TurnId, told: bool = False) -> Language | None:
        """Move the call, on the turn `on` (its words, or the reply to it), to the agent's
        language of `language` (a tag or a code): that language when the call moved, None when
        it may not move, the agent speaks no such language, or the call is held in it already.
        `told`: the speech-to-text bridge moved to it already (`untold`)."""
        found = self.of(language) if self.moves else None
        if found is None or found.primary == self.language.primary:
            return None
        self.language, self.moved_on = found, on
        self._told = found if told else self._told
        return found

    def untold(self) -> LanguageCode | None:
        """The code to name to the speech-to-text bridge (`ListenIn`) when the call moved since
        the bridge was last named its language, which it then is; None when it knows it."""
        if self._told.primary == self.language.primary:
            return None
        self._told = self.language
        return self.language.primary
