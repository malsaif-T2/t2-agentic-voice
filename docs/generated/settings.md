# Settings reference

Written by `uv run poe settings-ref` from the library's `VoiceSettings`
(`packages/t2-agentic-voice/src/t2_agentic_voice/core/config.py`), each description the field's
own; never edit it by hand (`tests/t2_agentic_voice/core/test_settings_ref.py` fails when it is
stale). The same command writes [.env.example](../../.env.example).

`VoiceSettings(env=..., ...)` built in code takes its defaults and the arguments given, and
nothing else. `VoiceSettings.from_env()` reads the environment variables below, under the prefix
`T2V_` unless `prefix=` gives another, and a `.env` file only when `env_file=` names one; the
environment wins over the file, and code values given to `from_env` win over both: a group given
as a dict (`server={"dev_page": True}`) changes only the keys it names, keeping the others the
environment and the file gave, while a group given as its object replaces the group whole. A
group's settings nest with `__`, a list or a map is given as JSON, and a blank value counts as
unset. A variable under the prefix that names no setting is an error, so the prefix belongs to
the library's settings alone. Each secret also takes a `_FILE` setting naming a file that holds
it, and never shows in a repr, a log line or an error. A unit is read from the name: `_ms` is
milliseconds, `_s` seconds, `_words` a count of words.

## The top level

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_ENV` | one of dev, test, staging, prod | required | — | Where the library runs: dev, test, staging or prod; required, with no default. Outside dev the dev page and logged call content are refused, and staging and prod refuse DEBUG. |

## `groq`

Groq, the provider of every model for now (D-004). The library reads only these names, never GROQ_API_KEY or GROQ_BASE_URL. The SDKs under it read a few variables of their own whatever is passed: leave unset those the guide lists (docs/guide/README.md, "Variables to leave unset").

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_GROQ__API_KEY` | secret, or unset | unset | — | The API key, required by the Groq adapters; or give api_key_file instead. |
| `T2V_GROQ__API_KEY_FILE` | path, or unset | unset | — | Or the full path of a file outside the repository that holds only the key, so the key can live outside .env. |
| `T2V_GROQ__BASE_URL` | text | `https://api.groq.com` | — | Groq's API address, always passed to the SDK so it never falls back to GROQ_BASE_URL. HTTPS only, since the key travels with every request. |

## `elevenlabs`

ElevenLabs: speech-to-text (Scribe) now, voices later; measured beside Groq (D-100).

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_ELEVENLABS__API_KEY` | secret, or unset | unset | — | The provider's API key; unset, its adapters are unavailable and say so when chosen. Or give api_key_file instead. |
| `T2V_ELEVENLABS__API_KEY_FILE` | path, or unset | unset | — | Or the full path of a file outside the repository that holds only the key, so the key can live outside .env. |

## `speechmatics`

Speechmatics: speech-to-text, its Arabic-English pack; measured beside Groq (D-100).

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_SPEECHMATICS__API_KEY` | secret, or unset | unset | — | The provider's API key; unset, its adapters are unavailable and say so when chosen. Or give api_key_file instead. |
| `T2V_SPEECHMATICS__API_KEY_FILE` | path, or unset | unset | — | Or the full path of a file outside the repository that holds only the key, so the key can live outside .env. |
| `T2V_SPEECHMATICS__REGION` | one of eu, us | `eu` | — | Where Speechmatics processes the audio: eu (its eu1 endpoints) or us (us1). eu by default, the region its data terms were read for (D-100). |
| `T2V_SPEECHMATICS__JOB_TIMEOUT_S` | number | `60` | seconds | The longest one batch transcription may take, from the job's upload to its transcript: a batch job queues and polls, so it takes longer than stt.timeout_s allows one request, and its time is measured, never assumed. |

## `cohere`

Cohere: speech-to-text (Transcribe Arabic); measured beside Groq (D-100).

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_COHERE__API_KEY` | secret, or unset | unset | — | The provider's API key; unset, its adapters are unavailable and say so when chosen. Or give api_key_file instead. |
| `T2V_COHERE__API_KEY_FILE` | path, or unset | unset | — | Or the full path of a file outside the repository that holds only the key, so the key can live outside .env. |

## `soniox`

Soniox: speech-to-text, batch and streaming; measured beside Groq (D-100).

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_SONIOX__API_KEY` | secret, or unset | unset | — | The provider's API key; unset, its adapters are unavailable and say so when chosen. Or give api_key_file instead. |
| `T2V_SONIOX__API_KEY_FILE` | path, or unset | unset | — | Or the full path of a file outside the repository that holds only the key, so the key can live outside .env. |
| `T2V_SONIOX__JOB_TIMEOUT_S` | number | `60` | seconds | The longest one async transcription may take, from the file's upload to its transcript: the job queues and polls, so its time is measured, never assumed. |

## `openai`

OpenAI: a talker and speech-to-text to measure beside Groq (D-100).

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_OPENAI__API_KEY` | secret, or unset | unset | — | The provider's API key; unset, its adapters are unavailable and say so when chosen. Or give api_key_file instead. |
| `T2V_OPENAI__API_KEY_FILE` | path, or unset | unset | — | Or the full path of a file outside the repository that holds only the key, so the key can live outside .env. |
| `T2V_OPENAI__BASE_URL` | text | `https://api.openai.com/v1` | — | OpenAI's API address; another only for a regional route OpenAI gives the account. HTTPS only, since the key travels with every request. |

## `inworld`

Inworld: voices to measure beside Groq's (D-100); the key in the Base64 form the portal copies.

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_INWORLD__API_KEY` | secret, or unset | unset | — | The provider's API key; unset, its adapters are unavailable and say so when chosen. Or give api_key_file instead. |
| `T2V_INWORLD__API_KEY_FILE` | path, or unset | unset | — | Or the full path of a file outside the repository that holds only the key, so the key can live outside .env. |

## `telnyx`

Telnyx: speech-to-text through its engines, HUMAIN's Arabic engine among them; measured beside Groq (D-100).

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_TELNYX__API_KEY` | secret, or unset | unset | — | The provider's API key; unset, its adapters are unavailable and say so when chosen. Or give api_key_file instead. |
| `T2V_TELNYX__API_KEY_FILE` | path, or unset | unset | — | Or the full path of a file outside the repository that holds only the key, so the key can live outside .env. |
| `T2V_TELNYX__TURN_TIMEOUT_S` | number | `30` | seconds | The longest one turn may take over the provider's WebSocket, from the connection to its last transcript; its time is measured, never assumed. |
| `T2V_TELNYX__FINAL_WAIT_S` | number | `3` | seconds | Once the turn's audio is sent, the longest the adapter waits for the provider's first final transcript; none by then, the turn heard no words. Part of the turn's measured time. |
| `T2V_TELNYX__QUIET_S` | number | `0.5` | seconds | Once a final transcript has come and the audio is sent, how long a quiet socket (no message) means the provider has said all it heard, when it does not close the socket itself; part of the turn's measured time. |
| `T2V_TELNYX__STT_MODEL` | one of humain/realtime, deepgram/nova-3, openai/whisper-large-v3-turbo | `humain/realtime` | — | The Telnyx speech-to-text model: humain/realtime (HUMAIN's Arabic engine with Arabic-English code-switching, on Telnyx's streaming WebSocket, the default), or deepgram/nova-3 or openai/whisper-large-v3-turbo (its batch endpoint). |
| `T2V_TELNYX__CHUNK_GAP_MS` | integer | `50` | milliseconds | The wait between two 100 ms chunks of a turn's audio sent to a streamed model, in milliseconds: 100 is real time, 50 (the default) twice as fast. HUMAIN's engine dropped most of a turn sent all at once and the end of one sent four times as fast (25), and heard two 5 s turns whole at 50 and 33 (probed 2026-11-16). A turn's time grows by its length times this gap over 100. |

## `humain`

HUMAIN: its own key, kept for its speech, voice and chat APIs once their reference is given; no adapter reads it yet (D-100).

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_HUMAIN__API_KEY` | secret, or unset | unset | — | The provider's API key; unset, its adapters are unavailable and say so when chosen. Or give api_key_file instead. |
| `T2V_HUMAIN__API_KEY_FILE` | path, or unset | unset | — | Or the full path of a file outside the repository that holds only the key, so the key can live outside .env. |

## `nabrah`

Nabrah: Saudi Arabic speech-to-text on its streaming WebSocket; measured beside Groq (D-100).

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_NABRAH__API_KEY` | secret, or unset | unset | — | The provider's API key; unset, its adapters are unavailable and say so when chosen. Or give api_key_file instead. |
| `T2V_NABRAH__API_KEY_FILE` | path, or unset | unset | — | Or the full path of a file outside the repository that holds only the key, so the key can live outside .env. |
| `T2V_NABRAH__TURN_TIMEOUT_S` | number | `30` | seconds | The longest one turn may take over the provider's WebSocket, from the connection to its last transcript; its time is measured, never assumed. |
| `T2V_NABRAH__FINAL_WAIT_S` | number | `3` | seconds | Once the turn's audio is sent, the longest the adapter waits for the provider's first final transcript; none by then, the turn heard no words. Part of the turn's measured time. |
| `T2V_NABRAH__QUIET_S` | number | `0.5` | seconds | Once a final transcript has come and the audio is sent, how long a quiet socket (no message) means the provider has said all it heard, when it does not close the socket itself; part of the turn's measured time. |

## `stt`

Speech-to-text: the adapter, the Whisper model, how long a request may take, the language and the prompt a call sends, the classifier of each turn's language, and the filter for text from silence.

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_STT__PROVIDER` | one of groq, elevenlabs, speechmatics, cohere, soniox, telnyx, nabrah | `elevenlabs` | — | Which adapter turns speech into text: elevenlabs (Scribe v3, the default, D-105; it needs T2V_ELEVENLABS__API_KEY), groq (Whisper, the fallback, on the Groq key alone), or one measured beside them (D-100): speechmatics (its ar_en pack, a batch job), cohere (Transcribe Arabic, the language always named), soniox (stt-async-v6, a batch job), telnyx (the model telnyx.stt_model names, HUMAIN's Arabic engine by default, a turn on its WebSocket) or nabrah (its Saudi Arabic model, a turn on its WebSocket); a provider with no key set is refused when chosen, naming its key's setting. |
| `T2V_STT__MODEL` | one of whisper-large-v3, whisper-large-v3-turbo | `whisper-large-v3` | — | The Whisper model: whisper-large-v3 or whisper-large-v3-turbo. The default stayed large-v3 on a registered measurement (D-025), and changes only on another (GP-18). |
| `T2V_STT__TIMEOUT_S` | number | `6` | seconds | The longest one transcription request may take before it is a timeout. |
| `T2V_STT__LIVE_LANGUAGE` | one of session, auto, classified, detected, hinted, single | `session` | — | The language a live call sends Whisper: session (the call's language, fixed when it joins from the caller's pick or the join token's locale), auto (none, so Whisper detects it) or classified (each turn's, chosen among the agent's languages by the classifier `stt.classifier` names from the turn's first `stt.classifier_from_s` seconds; a short, unsure, late, busy or failed turn keeps the language last classified, the call's until one is) or detected (each request names the call's current language, and a turn with `stt.detect_from_s` seconds of voiced speech or more is also sent naming none, at the same time: when Whisper hears the agent's other language in a question or request, never a short reply, that transcript is the turn's and the call moves to that language; on speechmatics, cohere, telnyx or nabrah, which report no language heard, no second request goes, and only a switch request or the talker moves the call) or hinted (each turn's one request names the call's current language as a hint and the agent's other languages beside it, which Scribe v3 takes as secondary languages; when the answer gives one of the agent's other languages with a probability of at least `stt.switch_min_probability`, in a question or request, never a short reply, the call moves to it, and a switch request or the talker moves it too; on a provider that gives no language probability, every one but elevenlabs, it runs as session, which the runtime's start logs) or single (each turn sends one request: a turn with `stt.detect_from_s` seconds of voiced speech or more names no language, and its answer is the turn's words, moving the call by hinted's rule; a shorter turn names the call's current language and never moves it; on a provider that gives no language probability it runs as session, which the runtime's start logs). A registered measurement sets the default (GP-18). |
| `T2V_STT__DETECT_FROM_S` | number | `1.2` | seconds | Under live_language detected or single, the seconds of voiced speech a turn needs, from where the speech detector heard it begin to where it last heard it stop (never the silence after), for its request naming no language (detected's second, single's one); a shorter turn keeps the call's current language. 1.2, registered for run H (D-038's amendment). |
| `T2V_STT__SWITCH_MIN_PROBABILITY` | number | `0.8` | — | Under live_language hinted or single, the least probability the provider must give the language it heard, one of the agent's other languages, for the turn to move the call (with a question or request, never a short reply); under it the call keeps its language. 0.8, a placeholder until run H's Scribe arms are measured (GP-18). |
| `T2V_STT__CLASSIFIER` | one of silero, ecapa | `silero` | — | The spoken-language classifier under live_language classified: silero (Silero's 95 languages, on onnxruntime) or ecapa (ECAPA on VoxLingua107, on torch through SpeechBrain, which needs the library's ecapa extra: uv sync --group language-id in this workspace). |
| `T2V_STT__CLASSIFIER_DIR` | path, or unset | unset | — | The folder of the classifier's model files, fetched once by hand as the guide's languages page says and each checked against its pinned SHA-256 at every start and by t2v doctor; never under a repository or var/. No default: live_language classified is refused at start without it. |
| `T2V_STT__CLASSIFIER_FROM_S` | number | `2` | seconds | The seconds of a turn's audio, from where the speech detector heard its speech begin, that the classifier hears; pauses inside the turn count. A turn whose request goes with less keeps the current language (short). 2.0, registered for run H (plan 007, Q20). |
| `T2V_STT__CLASSIFIER_MIN_SHARE` | number | `0.7` | — | The best share of the agent's languages the classifier must give a turn to move the call's current language; under it the turn keeps it (unsure). 0.7, registered for run H (plan 007, Q20). |
| `T2V_STT__CLASSIFIER_THREADS` | integer | `2` | — | The CPU threads the classifier's model runs on; one classification runs at a time a process, and a turn that finds it busy keeps the current language (busy). |
| `T2V_STT__NO_SPEECH_MAX` | number, or unset | `0.55` | — | The no-speech probability Whisper reports above which a transcript counts as no words (text from silence), for a turn and for speech over a reply, from 0 to 1; unset, the threshold is off. 0.55 by the registered rule F and its one revision (plan 005), which changes only on another registered measurement (GP-18). |
| `T2V_STT__CAPTION_FILTER` | true or false | `true` | — | Whether a transcript that is one of the captions Whisper invents for silence or noise counts as no words; on by the registered rule F (plan 005), which changes only on another registered measurement (GP-18). |
| `T2V_STT__STREAMING` | true or false | `false` | — | Whether a call hears the caller over one stream of the provider's for the whole call (elevenlabs: Scribe v3 Live, plan 010's 5.1) rather than one request a turn: each turn's audio goes as it comes, from its pre-roll, silence in place of the rest of the call, and each turn's end commits it, its words back 249.9 ms later at the median (the probe of 2026-11-18 on dev, against 567.5 ms for a request). Only under live_language session, or a mode that runs as session, on a provider that streams; an overlap's parts still go as requests, and a stream that fails leaves the rest of the call to requests. The provider bills every second of the stream, silence included. Off until a live check keeps it (GP-18). |
| `T2V_STT__SEND_PROMPT` | true or false | `true` | — | Whether each speech-to-text request of a call sends Whisper the prompt of the language it names: the agent's vocabulary, then the command words as they should be written. On since run W's arm W1 (plan 006), which on the golden set raised Whisper's right count beyond the noise on dev (stop words 0.69 to 0.92, repeat requests 0.32 to 0.53) and on held-out (accuracy 0.382 to 0.420, word errors 0.254 to 0.218, stop words 0.778 to 0.889); it changes only on another registered measurement (GP-18). |

## `llm`

The chat model the talker writes its replies with: the adapter, the model, how much it reasons, the most it may write, how long a request may take, whether each request opens with a line of its own, the most requests a turn, whether a rejected request is sent once more, and whether every request ends with a line naming the reply's language.

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_LLM__PROVIDER` | one of groq, openai | `groq` | — | Which adapter reaches the talker's chat model: groq (D-004), or openai, OpenAI's own API with the openai group's key (D-112), off by default. Under openai the yes rule's check and the uncertain overlap's request stay on Groq's gpt-oss-120b, so the Groq key is needed too. |
| `T2V_LLM__MODEL` | one of openai/gpt-oss-120b, openai/gpt-oss-20b, llama-3.3-70b-versatile, llama-3.1-8b-instant, qwen/qwen3.8-27b, minimaxai/minimax-m2.7, gpt-6-luna, gpt-5.6-luna, gpt-5.4-mini, gpt-6.1-terra, gpt-5.5, gpt-4.1 | `openai/gpt-oss-120b` | — | The chat model: on groq openai/gpt-oss-120b, openai/gpt-oss-20b, llama-3.3-70b-versatile, llama-3.1-8b-instant, qwen/qwen3.8-27b or minimaxai/minimax-m2.7; on openai gpt-6-luna, gpt-5.6-luna, gpt-5.4-mini, gpt-6.1-terra, gpt-5.5 or gpt-4.1. The default changes only on a registered measurement (GP-18). |
| `T2V_LLM__REASONING_EFFORT` | one of none, low, medium, high | `medium` | — | How much a reasoning model thinks before it answers: none, low, medium or high, as its model takes them (the gpt-oss models low to high; qwen3.8-27b none to high; OpenAI's only none, the one its Chat Completions take with tools). Sent only to a model that takes it. Medium, as the owner ruled on run K's dev pass (plan 006, Q26): gpt-oss-120b invented 6 answers of 136 against 18 at low, for about 0.33 s more to the first clause. |
| `T2V_LLM__MAX_OUTPUT_TOKENS` | integer | `1024` | — | The most tokens one model request may write, its reasoning included: a spoken reply is one to three short sentences, or every step of a procedure. |
| `T2V_LLM__TIMEOUT_S` | number | `8` | seconds | The longest one model request may take before it is a timeout. |
| `T2V_LLM__VARY_FIRST_LINE` | true or false | `true` | — | Whether each request's system message opens with a line new on every request, so no two requests share a prefix the provider has cached. Groq's cache can be slow: on openai/gpt-oss-120b with one app's system prompt, 3 of the 8 requests it served from its cache took 1.03, 1.25 and 5.71 s to the first token, while 12 requests with a first line of their own all took 0.15 to 0.30 s (2026-11-07, D-072). |
| `T2V_LLM__MAX_REQUESTS_PER_TURN` | integer | `3` | — | The most model requests one turn makes: each but the last offers the agent's tools, the last none, so the turn ends in words. |
| `T2V_LLM__RETRY_REJECTED` | true or false | `false` | — | Whether a request of a turn the provider rejects (a rejected error, such as Groq's tool_use_failed when the model wrote a malformed tool call) is sent once more, with a new first line and nothing of the first kept, when nothing of it was said yet and neither a leak nor the question limit stopped the reply (D-132): never twice for one request, and not counted in max_requests_per_turn. Off: the reply ends with the error notice, as before. |
| `T2V_LLM__REPLY_LINE_ALWAYS` | true or false | `false` | — | Whether every request of a turn ends with the short system line naming the reply's language, as a request after a tool result does: with no tool result before it, the line names the language alone, saying nothing of results. The owner's calls of 2026-11-22 had English small talk in an Arabic call, which calls no tool, answered in Arabic and read by the English voice; 15 plays of 5 switch dialogues had 8 of 30 switched turns in the wrong language without the line and 0 of 30 with it, with no measurable change in time. Off: only a request after a tool result ends with it, as before. |

## `tts`

Text-to-speech: the adapter, a model and a voice for each language, what is done with the audio, and which voice a clause written in the other script is said in.

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_TTS__PROVIDER` | one of groq, elevenlabs, telnyx | `elevenlabs` | — | Which adapter turns text into speech: elevenlabs (v4 Turbo in the owner's voice for Saad, the default, D-114; it needs T2V_ELEVENLABS__API_KEY, as Scribe does), groq (Orpheus, the fallback, on the Groq key alone) or telnyx (Bayan, measured beside them; it needs T2V_TELNYX__API_KEY). With tts.languages unset, each language is spoken in the chosen provider's default model and voice. |
| `T2V_TTS__LANGUAGES` | JSON object from one of ar-SA, ar, en to {model, voice} | `{"ar-SA": {"model": "eleven_v4_turbo", "voice": "nhJWWCFdNdusuVUT3x19"}, "ar": {"model": "eleven_v4_turbo", "voice": "nhJWWCFdNdusuVUT3x19"}, "en": {"model": "eleven_v4_turbo", "voice": "nhJWWCFdNdusuVUT3x19"}}` | — | The model and voice of each language preset (ar-SA, ar, en), in tts.provider's own names, as a JSON object: {"en": {"model": "canopylabs/orpheus-v1-english", "voice": "troy"}}. A value replaces the whole map; unset, it is the provider's default map. |
| `T2V_TTS__TIMEOUT_S` | number | `6` | seconds | The longest one synthesis request may take before it is a timeout. |
| `T2V_TTS__CACHE_PHRASES` | true or false | `true` | — | Whether the fixed phrases declared at start (greetings, notices) are synthesized once and cached under the storage folder. |
| `T2V_TTS__CACHE_CLAUSES` | true or false | `true` | — | Whether every clause the agent speaks in a call with a talker is kept on disk under the storage folder by its exact text, its language, its voice and the adapter that made it, so the same clause plays again with no request; the echo's words said back are never kept. On by default, as the owner ruled: it costs only disk, bounded by clause_cache_mb. |
| `T2V_TTS__CLAUSE_CACHE_MB` | integer | `512` | — | The most disk the clause cache keeps, in megabytes; past it, the clauses played longest ago are removed. |
| `T2V_TTS__SPOKEN_NUMBERS` | one of as_written, by_register | `as_written` | — | How a reply's numbers, times and dates are said: as_written reads each run of digits as a number (num2words' MSA in Arabic) or an ID; by_register says them in the caller's register, Saudi or MSA words in Arabic, a time as a clock says it with its part of the day, an ISO date with its weekday and month. |
| `T2V_TTS__SPOKEN_KEY_COMBINATIONS` | true or false | `false` | — | Whether a key combination in a reply is said as its keys, its plus signs left out ("Ctrl + Shift + R" is said "Control Shift R"; in Arabic, by the Arabic names of its keys); off, it is said as written. |
| `T2V_TTS__TRIM_SILENCE` | true or false | `false` | — | Whether the silence the model puts before its speech is trimmed; off, the audio plays as it comes. |
| `T2V_TTS__STREAM_REPLIES` | true or false | `false` | — | Whether the talker's replies are spoken on the provider's streaming socket, one a call, each clause sent as the talker writes it and each reply one turn of the voice (ElevenLabs' Text-to-Dialogue socket, for its v3 and v4 models; D-121). Fixed lines, an action's lines and the clause cache's takes keep to one request a clause, as does a provider or model with no socket; a socket's failure turns it off for the rest of the call. Off by default until it is measured. |
| `T2V_TTS__VOICE_BY_SCRIPT` | true or false | `false` | — | Whether a clause of an English reply with more words in Arabic letters than in Latin ones is said in the agent's Arabic voice, its numbers in the caller's register: a clause with no letters, or as many of each, keeps the voice of the clause before it, and an Arabic reply never changes voice, so a Latin product name in it keeps the Arabic one. The owner's calls of 2026-11-22 had two Arabic replies to English small talk read by orpheus-v1-english. Off: every clause is said in its reply's language, whatever its letters, as before. |

## `turns`

Turn-taking: the speech detector (Silero VAD) and the end-of-turn model (Smart Turn).

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_TURNS__VAD_CONFIDENCE` | number | `0.7` | — | How sure the speech detector must be that a frame is speech, from 0 to 1. |
| `T2V_TURNS__VAD_START_MS` | integer | `200` | milliseconds | How long speech must last before the detector says the caller started. |
| `T2V_TURNS__VAD_STOP_MS` | integer | `200` | milliseconds | How long a silence must last before the detector says the caller paused. |
| `T2V_TURNS__VAD_MIN_VOLUME` | number | `0.6` | — | The quietest a frame may be and still count as speech, from 0 to 1. |
| `T2V_TURNS__SMART_TURN` | true or false | `true` | — | Whether Smart Turn decides, at each pause, if the caller has finished; off, every pause the detector hears ends the turn. |
| `T2V_TURNS__SMART_TURN_THRESHOLD` | number | `0.5` | — | How sure Smart Turn must be that the caller has finished, from 0 to 1: a pause ends the turn when its probability is above this. 0.5, Smart Turn's own, leaves a turn's end as it was. |
| `T2V_TURNS__COMPLETE_HOLD_MS` | integer | `600` | milliseconds | How long a turn Smart Turn judged finished waits before it ends: speech that resumes within it cancels the end, and the turn goes on. 600 by plan 005's registered E (its arm Ec, the owner's ruling), which changes only on another registered measurement (GP-18); 0 ends the turn at Smart Turn's verdict. The speech detector's pause, which an interruption waits on, is never delayed. |
| `T2V_TURNS__EARLY_AT_STOP` | true or false | `false` | — | Whether, in a call with a talker, a turn's speech so far goes to speech-to-text as the speech detector hears it stop, Smart Turn's time before its verdict: kept only when Smart Turn calls the turn finished, dropped when it calls the pause unfinished or the caller speaks again, the next pause sending again. Needs complete_hold_ms above 0. Off: the request goes at Smart Turn's verdict. |
| `T2V_TURNS__SMART_TURN_STOP_MS` | integer | `3000` | milliseconds | The silence after which Smart Turn ends the turn whatever it heard. |
| `T2V_TURNS__SMART_TURN_PRE_SPEECH_MS` | integer | `500` | milliseconds | How much audio before the speech started Smart Turn hears with it. |
| `T2V_TURNS__SMART_TURN_THREADS` | integer | `1` | — | How many CPU threads Smart Turn's model runs on at each pause: more judge sooner on a laptop with cores to spare, the same verdicts. |
| `T2V_TURNS__SMART_TURN_MAX_DURATION_S` | number | `8` | seconds | The most audio of a turn Smart Turn hears, its latest part. |
| `T2V_TURNS__MAX_SILENCE_MS` | integer | `3000` | milliseconds | The fallback end of a turn: a silence this long ends it, whatever decides. |
| `T2V_TURNS__READ_BACK_SILENCE_MS` | integer, or unset | unset | milliseconds | The fallback end of a turn said while an action's read-back awaits its answer, in place of max_silence_ms, so a pause after a yes ("yes, but change ...") is not taken for its end; Smart Turn's own smart_turn_stop_ms still ends it, and it needs complete_hold_ms above 0. Unset: max_silence_ms for every turn. |

## `interruptions`

Interruptions: how the caller's speech over the agent's reply is taken, and the bounds of the rule that decides whether it stops the agent.

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_INTERRUPTIONS__MODE` | one of drop, two_step | `two_step` | — | How the caller's speech over the agent's reply is taken: two_step, the default by the owner's ruling (plan 005), lowers the agent's voice, transcribes the speech, and stops the agent only when the rule says so; drop keeps the half-duplex behaviour from before plan 005 (the turn is not answered, so the agent never answers its own voice). |
| `T2V_INTERRUPTIONS__DUCK_LEVEL` | number | `0.25` | — | How loud the agent's reply plays while the caller speaks over it, until the speech is judged, from 0 (silent) to 1 (unchanged). |
| `T2V_INTERRUPTIONS__FIRST_WINDOW_MS` | integer | `750` | milliseconds | The first part of the speech over a reply sent to speech-to-text before the caller has finished, counted from 300 ms before the speech detector heard it begin. |
| `T2V_INTERRUPTIONS__MIN_WORDS` | integer | `2` | words | The fewest words over a reply that stop the agent when none is a listed word. |
| `T2V_INTERRUPTIONS__SHORT_WORDS` | integer | `2` | words | The most words a short output holds: at most this many, under short_s of speech, and none a stop, repeat or no word, the agent goes on (a listening sound misheard). |
| `T2V_INTERRUPTIONS__SHORT_S` | number | `1.2` | seconds | The speech a short output stays under, for the agent to go on; 1.2 by the rule's one revision (plan 005). |
| `T2V_INTERRUPTIONS__OWN_WORDS_S` | number | `5` | seconds | How far back the agent's own words count: speech over a reply whose words are those of the clauses played this long before is its own voice, heard back. |
| `T2V_INTERRUPTIONS__YES_OVER_READ_BACK` | true or false | `false` | — | Whether a yes said over an action's read-back books once its summary has played whole, with no other words said after it (the closing question then cut), and a bare yes over the closing question books too, as khalas beside a yes or a send word does: the owner's 'Any yes books' (D-108). Off: a yes over the summary counts for nothing, and over the closing question a yes needs a send word. |
| `T2V_INTERRUPTIONS__ANSWER_YES_OVER_QUESTION` | true or false | `false` | — | Whether a yes said over the question that ends any reply of the agent's (a yes or a send word among only yes words, send words and fillers, never the agent's own words heard back, begun once every clause before the question played, or in the 0.3 s after the reply ended), which the agent's voice goes on over, is answered as the caller's next turn once the reply's tail and the speech detector's lag have passed, never when the reply was stopped or other words were said after it: the owner's 'Any yes books' for agents with no read-back (D-116). An action's read-back keeps its own rule (yes_over_read_back). Off: such a yes is not answered. |

## `words`

Words: what a team adds to each language's lists, which the interruption rule reads.

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_WORDS__STOP` | JSON object from one of ar, en to JSON list of text | `{}` | — | Words added to each language's stop words, which stop the agent at once, as a JSON object from a language's code (ar, en) to a list: {"ar": ["..."]}. A value replaces the map. |
| `T2V_WORDS__WAIT` | JSON object from one of ar, en to JSON list of text | `{}` | — | Words added to each language's words asking the agent to pause, which stop it as a stop word, as a JSON object from a language's code (ar, en) to a list: {"ar": ["..."]}. A value replaces the map. |
| `T2V_WORDS__REPEAT` | JSON object from one of ar, en to JSON list of text | `{}` | — | Words added to each language's repeat words, which stop the agent and say its last reply again, as a JSON object from a language's code (ar, en) to a list: {"ar": ["..."]}. A value replaces the map. |
| `T2V_WORDS__BACKCHANNEL` | JSON object from one of ar, en to JSON list of text | `{}` | — | Words added to each language's listening sounds, after which the agent goes on, as a JSON object from a language's code (ar, en) to a list: {"ar": ["..."]}. A value replaces the map. |
| `T2V_WORDS__NO` | JSON object from one of ar, en to JSON list of text | `{}` | — | Words added to each language's no words, which a short output never holds, as a JSON object from a language's code (ar, en) to a list: {"ar": ["..."]}. A value replaces the map. |
| `T2V_WORDS__YES` | JSON object from one of ar, en to JSON list of text | `{}` | — | Words added to each language's yes words, which the yes rule reads, as a JSON object from a language's code (ar, en) to a list: {"ar": ["..."]}. A value replaces the map. |
| `T2V_WORDS__SEND` | JSON object from one of ar, en to JSON list of text | `{}` | — | Words added to each language's send words, which a yes over the closing question needs, and which a yes over any reply's question may be (interruptions.answer_yes_over_question), as a JSON object from a language's code (ar, en) to a list: {"ar": ["..."]}. A value replaces the map. |
| `T2V_WORDS__VOCABULARY` | JSON list of text | `[]` | — | Product terms added to the declaration's vocabulary, which becomes the Whisper prompt, as a JSON list: ["VPN", "Outlook"]. A value replaces the list. |
| `T2V_WORDS__DIALECT` | JSON list of text | `[]` | — | Saudi forms added to the library's list the register of the caller's Arabic is read by, as a JSON list of Arabic words or phrases; a phrase of several words is one of them heard as those words in a row. A value replaces the list. |
| `T2V_WORDS__FIXED_REGISTER` | one of saudi, msa, or unset | unset | — | The register every ar-SA call is held in from its start to its end, whatever the caller says: saudi (the Saudi spoken register) or msa; unset (the default), it is read from the caller's words as dialect and saudi_first say. |
| `T2V_WORDS__SAUDI_FIRST` | true or false | `false` | — | Whether an ar-SA call reads the caller as Saudi unless they plainly speak MSA: a turn with no Saudi form is MSA only when it holds one of the library's few forms only MSA says (ureed, awadd, hal, matha, al-aan, sawfa and the like), and a turn with neither keeps the call's register, Saudi until an MSA one is heard; a Saudi form makes the call Saudi from then on. Off: a turn with no Saudi form is MSA. |
| `T2V_WORDS__HOLD_REPLY_LANGUAGE` | true or false | `false` | — | Whether a short turn keeps the caller's language in a call whose language never moves (stt.live_language session, auto or classified, or hinted or single where they run as session): a turn of under 3 words in each script is answered in the language of the caller's most recent earlier turn that plainly said one, so a caller who switched to English and says yes please is answered in English, in the English voice. A longer turn, one that mixes the two included, and a turn that asked for a language are answered as before. Off: a short turn is answered in the language it was heard in, the call's under session, as before. |

## `guard`

The output guard: what counts as an ID, and what a clause that speaks one with no evidence drops.

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_GUARD__ID_PATTERNS` | JSON list of text | `[]` | — | More ID shapes, beside runs of min_id_digits digits, as a JSON list of regular expressions, such as ["LT-\\d{5}"]. A pattern that matches no text at all (the empty text) is refused. Unset: none. |
| `T2V_GUARD__DAY_MONTH_APART` | true or false | `false` | — | Whether a day and a month alone with one hyphen between them in a clause (26-11), no third number joined to it, are read as two numbers, not one ID of their digits (D-134); off, they are one group as before. |
| `T2V_GUARD__MIN_ID_DIGITS` | integer | `3` | — | The fewest digits in a row, after digit words and Arabic-Indic digits are made digits, that count as an ID, which passes only with evidence from this call. |
| `T2V_GUARD__ON_BLOCK` | one of drop_rest, drop_clause | `drop_rest` | — | What a blocked clause drops: drop_rest, it and the rest of the reply, or drop_clause, only it. A fixed phrase is spoken in its place either way. |
| `T2V_GUARD__CLAIMS` | JSON object from one of ar, en to JSON list of text | `{}` | — | Phrases added to each language's default list of what claims any action, as a JSON object from a language's code to a list: {"ar": ["..."]}. A value replaces the map. An agent that declares no action, only tools that declare claims, reads these alone, without the defaults. |
| `T2V_GUARD__REMOVE_STRAY_SCRIPT` | true or false | `true` | — | Whether each character of a script none of the agent's languages writes (a Chinese character in an Arabic reply), and each pictograph, is taken out of what the talker writes, its tool calls' arguments included, before the guard reads it, and a digit of another script written as its ASCII digit; the voice, the captions, the history, the trace and the events then hold the text without it. Off: kept as written. |
| `T2V_GUARD__QUESTIONS_PER_REPLY` | integer, or unset | `1` | — | The most questions one spoken reply of the talker's may ask the caller: the reply stops before the next one, which is not said, nor anything after it. A question is a clause that ends with a question mark. None, given in code: no limit. |
| `T2V_GUARD__QUESTION_STOP_DROPS_CALLS` | true or false | `false` | — | Whether a reply the question limit stopped also drops the tool calls of the request it stopped in: on, none of them runs, so the question the caller heard ends the turn; off, they run and are kept, as before. |
| `T2V_GUARD__DROP_STAGE_NOTES` | true or false | `false` | — | Whether a stage note or a tag the model writes into its answer counts as its reasoning, so nothing of that request is said from it on and none of its tools runs: in a reply in Arabic script, a parenthesis or bracket glued to a sentence's end with a capital Latin letter after it; in any language, one that opens a stage word ("(Waiting", "[No output"); and a "<" that opens a tag ("<action", "<data", or a tool's or an action's name). Arabic in parentheses never counts. In a reply in Arabic script, a word that opens as the reasoning does ("We need", "The user") after text written in Arabic script counts wherever a word starts (after a space, a parenthesis, an ellipsis or any mark), not only glued to a sentence's end; an English reply keeps the glued rule alone. Off: none counts. |
| `T2V_GUARD__PLAIN_SPEECH` | true or false | `false` | — | Whether only plain speech is said (D-111): a run of dots after a sentence's mark is taken out, and one after a word made one ellipsis; a clause whose characters, spaces aside, are less than half letters or digits, or that holds a bracket, a brace or a tag's opening, is not said, nor anything after it of its request, and none of that request's tools runs; a request that said nothing so is sent once more while the turn has a request left; and zero-width spaces, word joiners, byte order marks, asterisks and backticks are taken out of every clause. Off: said as written. |
| `T2V_GUARD__RETRY_CLAIMS` | true or false | `false` | — | Whether a reply whose clause the claim rule blocked (it said an action or a tool's write was done, and no result of the call says so) asks the model once more, as many times a turn as retries_per_turn allows: neither the clause nor the error notice in its place is said, nor anything of its request after it, none of that request's tools runs, and the request is sent again with what it said before the clause and a note that the claim was held back, one request past llm.max_requests_per_turn. A claim blocked once those are spent is dropped as on_block says. Off: as on_block says, the error notice said in its place. |
| `T2V_GUARD__RETRY_IDS` | true or false | `false` | — | Whether a reply whose clause the ID rule blocked (it held an ID-shaped number that no result of the call nor the caller's words give, such as a sum the model worked out itself) asks the model once more, as retry_claims does a claim and counted with it in retries_per_turn: neither the clause nor the error notice in its place is said, nor anything of its request after it, none of that request's tools runs, and the request is sent again with what it said before the clause and a note to say only the numbers the results give, one request past llm.max_requests_per_turn. Off: as on_block says, the error notice said in its place. |
| `T2V_GUARD__RETRIES_PER_TURN` | integer | `1` | — | How many times one turn's request may be sent again for a clause the guard blocked (a claim under retry_claims, a number under retry_ids), each one request past llm.max_requests_per_turn; a clause blocked once they are spent goes as on_block says. 1: once a turn. |

## `session`

The voice session: what answers the caller.

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_SESSION__MODE` | one of echo, talker, or unset | unset | — | What answers each turn: echo, which says back what it heard, or talker, which answers with the chat model and the agent's tools. Unset: the declaration's, talker for an agent that declares instructions and echo for one that does not. |
| `T2V_SESSION__PROGRESS_BEAT_MS` | integer, or unset | unset | milliseconds | The silence after a tool's progress line before the answer, in ms, counted from the end of the line's speech: the take's own silence after it is cut first. Unset: the take as it is, then 400 ms, the beat around every fixed line said next to other speech. |
| `T2V_SESSION__EARLY_OVER_REPLY` | true or false | `false` | — | Whether a turn held while a reply to an earlier turn is still in progress (nothing of it playing as the turn began) starts the talker early too: that reply is stopped as the turn's held words come, as the turn's answer would stop it, so the talker reads it as cut. Off: such a turn starts the talker once it has ended. |

## `server`

Serving: the backend's address, the pages that may call it, how media finds a path, and the dev page with the test console's dev caller.

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_SERVER__PUBLIC_URL` | text, or unset | unset | — | The address callers reach the backend at, such as https://voice.example. |
| `T2V_SERVER__ALLOWED_ORIGINS` | JSON list of text | `[]` | — | The pages allowed to call the backend from a browser, as a JSON list of origins (scheme, host and port only, written as a browser sends them: lowercase; a host name of letters, digits and hyphens, in its xn-- form, or an IP address in its shortest form; no default port), such as ["https://www.example.com"]. Unset: none. |
| `T2V_SERVER__ICE_SERVERS` | JSON list of text | `[]` | — | The STUN and TURN servers a call is given, as a JSON list of stun:, turn: or turns: URLs with no credentials (TURN's are minted per call from turn_secret). |
| `T2V_SERVER__TURN_SECRET` | secret, or unset | unset | — | The secret shared with the TURN server, which signs each call's credentials: at least 32 bytes. Or give turn_secret_file instead. |
| `T2V_SERVER__TURN_SECRET_FILE` | path, or unset | unset | — | Or the full path of a file that holds only the TURN secret. |
| `T2V_SERVER__TURN_TTL_S` | integer | `3600` | seconds | How long each call's TURN credentials last, at most 86400 (a day). |
| `T2V_SERVER__DEV_PAGE` | true or false | `false` | — | Whether the router serves its /dev page, to loopback clients; dev only. |
| `T2V_SERVER__DEV_CALLER` | {subject, display_name, locale, attributes}, or unset | unset | — | The caller the test console's Start makes a signed join token for, under env dev with the dev page on: a JSON object, such as {"subject": "owner", "attributes": {"customer_email": "demo@example.com"}}, read as the library's Caller. An app usually sets it in code. Unset: the console makes none and joins as dev. |
| `T2V_SERVER__FORWARDED_ALLOW_IPS` | JSON list of text | `[]` | — | The proxies whose X-Forwarded-For headers are trusted, as a JSON list of IP addresses or networks, such as ["127.0.0.1"], a network by its own address (10.0.0.0/24): an entry is no wider than /8 for IPv4 or /32 for IPv6, and no wider than /104 where it overlaps ::ffff:0:0/96, ::ffff:0:0:0/96, 64:ff9b::/96, 64:ff9b:1::/48 or ::/96, or /24 where it overlaps 2002::/16, the IPv6 ranges that carry IPv4 addresses; "*" is refused. Unset: none. |

## `join`

Join tokens: the keys that sign and verify them, and how long one lives.

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_JOIN__KEYS` | JSON object from text to secret | `{}` | — | The keys that verify join tokens, as a JSON object from key ID to secret, each secret at least 32 bytes. Or give keys_file instead. |
| `T2V_JOIN__KEYS_FILE` | path, or unset | unset | — | Or the full path of a file that holds the key map, the same JSON object as keys. |
| `T2V_JOIN__CURRENT_KID` | text, or unset | unset | — | The ID of the key that signs new tokens; one of the map's. |
| `T2V_JOIN__TTL_S` | integer | `60` | seconds | How long a join token lives, at most 120. |
| `T2V_JOIN__MAX_CLOCK_SKEW_S` | integer | `30` | seconds | How far a token's times may be off this machine's clock and still verify, at most 60: a token verifies until its expiry plus this. |

## `privacy`

Privacy: whether a call's audio may be recorded, and the consent version callers agree to (docs/SECURITY.md, invariant 8).

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_PRIVACY__RECORD_AUDIO` | true or false | `false` | — | Whether a call's audio may be recorded under the storage folder: only when this is on and the caller's signed join token says they consented. |
| `T2V_PRIVACY__CONSENT_VERSION` | text, or unset | unset | — | The version of the consent text callers agree to (1 to 64 printable characters, no space); when set, a signed join token holding another version is refused (a consent no signed token gave, as the dev identity's, keeps no audio and is not compared). Unset: any. |

## `logging`

Logging: the level and format of the library's lines, and what they may hold.

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_LOGGING__LEVEL` | one of DEBUG, INFO, WARNING, ERROR | `INFO` | — | DEBUG, INFO, WARNING or ERROR; staging and prod refuse DEBUG. |
| `T2V_LOGGING__FORMAT` | one of console, json | `console` | — | console (human-readable) or json (machine-queryable). |
| `T2V_LOGGING__CONTENT` | true or false | `false` | — | Whether log lines may hold what was said in a call; refused outside dev (docs/SECURITY.md, invariant 8). |
| `T2V_LOGGING__PIPECAT` | one of off | `off` | — | What becomes of the voice framework's own log lines: off, the only value. |

## `tracing`

Tracing, as plain OTLP over HTTP to Phoenix or any OpenTelemetry backend (D-023).

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_TRACING__ENDPOINT` | text, or unset | unset | — | Where spans are sent: an OTLP/HTTP traces endpoint, such as a local Phoenix's http://127.0.0.1:6006/v1/traces. Unset: no span leaves the process, unless the app passes its own tracer provider. |
| `T2V_TRACING__PROJECT` | text, or unset | unset | — | The project the spans are filed under in Phoenix. Unset: the default one. |
| `T2V_TRACING__INCLUDE_TRANSCRIPTS` | true or false | `true` | — | Whether spans carry what was said: what the caller was heard to say, the agent's replies and its tool calls with their results are the only call content a trace holds (docs/SECURITY.md, invariant 8). |
| `T2V_TRACING__REDACT` | JSON list of text | `[]` | — | Regular expressions; every match is replaced in each text attribute before it is exported. A JSON list, such as ["\\d{10}"]. Unset: none. |

## `limits`

Limits on one call.

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_LIMITS__MAX_CALL_S` | number | `600` | seconds | The longest a call may last; the library ends it then. |
| `T2V_LIMITS__IDLE_S` | number | `120` | seconds | The longest a call may go with nothing heard from the caller; then it ends. |
| `T2V_LIMITS__ACTIONS_PER_CALLER_PER_DAY` | integer | `20` | — | How many of one kind of action one caller may have done in a day, counted from the outbox: every write that may have reached the system, none refused or never sent. Beyond it the action is refused before its read-back. The agent's starting value. |

## `storage`

Storage: one folder for everything the library keeps.

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_STORAGE__VAR_DIR` | path | `var` | — | Local runtime data (git-ignored): databases, run outputs, caches. Every path under it comes from here, so one setting moves a whole run, a test session included. |

## `warmup`

The warm-up: what the server's start and each call's join ready for the turns to come.

| Variable | Type | Default | Unit | Description |
| --- | --- | --- | --- | --- |
| `T2V_WARMUP__AT_START` | true or false | `false` | — | Whether the server's start imports the modules a call's offer needs (Pipecat's pipeline, aiortc's peer) in a thread, and keeps one call's speech detector and turn analyzer made ahead, the next made in the background as each call takes one. Off: the first offer imports them on the event loop, and each call makes its own. |
| `T2V_WARMUP__AT_JOIN` | true or false | `false` | — | Whether each call, as it joins, sends one request that costs nothing to the call's speech-to-text and its text-to-speech (and to the chat model when its connection is not warm), in the background, so their connections are open before the first turn. A failed one is logged and never fails the call. |
| `T2V_WARMUP__AFTER_CANCEL` | true or false | `false` | — | Whether the Groq chat adapter opens a fresh connection in the background after a cancelled or closed stream, which closes its connection, so the next request does not pay a new handshake. |
