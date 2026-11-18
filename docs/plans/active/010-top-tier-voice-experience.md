# 010 · The voice experience at the level of top-tier voice agents

Status: active · Milestone: M9 · Started: 2026-11-15

*Drafted on 2026-11-15 at the owner's request of that day, from 13 studies, two skeptics per
decision-driving claim and three reviews; built on today's main, as the owner ruled. Approved by
the owner on 2026-11-16 with their amendments ("The owner's decisions"): no dates, the language
switched by any question or request in the other language, the providers' keys offered at once,
and the work ordered by gain per hour of work. Each open question is asked, explained, when the
work first needs it. Every number describes
the calls of 2026-11-11, 11-12 and 11-15 on the owner's laptop, or the owner's own voice on the
golden set (D-006), unless it names another source. Builders read "Notes for the builders" first.*

## In short

- **The first question is not weighted more; old search results drown the new one.** Each search's
  seven passages stay in every later request until four newer tool turns push them out, and every
  search returns much the same passages, because the model adds "Ole5" to each query and the index
  holds title-only stubs. By turn 6 of call FSMRkwf about 61% of what the model read was old
  results, the caller's new words about 10 tokens of 8,600; a passage that answered the same
  question in a fresh call (WfTe t0) was in the result, and refused.
- **It gives up and repeats because nothing stops it.** No rule makes it search before "I don't
  have that information", and nothing notices a sentence said twice. On 11-15, 13 of 43 replies
  refused, 8 with no search (6 once two right refusals about how the agent itself was built are
  left out), and 5 copied an earlier reply word for word.
- **Nobody can change language mid-call today.** The language is fixed at join (D-038), and
  Whisper, told the wrong language, translates into fluent wrong text, so no check of the text can
  catch it. The owner ruled that any question or request in the other language switches the call,
  both ways (2026-11-16), so each turn's language is detected, Arabic or English only: Whisper's
  own detection works on longer turns today, and the providers' language scores and a classifier
  held to the two languages are measured beside it (2.5).
- **Much of what sounds slow or broken is not a model.** 1 turn in 7 waits for a 3-second silence
  timer (24 of 168): about half of them short finished turns such as "hello", most of the rest
  finished sentences. The first call after a restart took 24 s to connect (TD-089). The "let me
  check" line holds answers back. "Ole5" is said "Ole five" in replies; a ticket number takes 12 s.
- **Arabic is behind first in hearing.** Whisper hears the owner's Saudi speech about 7 times worse
  than English (WER 0.344 against 0.048); «إي نعم» was heard right 0 of 4 times live, "Ole5" 0 of
  9. On a public Saudi TV test the best 2026 models make roughly 40% fewer errors than open Whisper
  (other parties' runs, not our setup), so a bake-off on our own voices decides.
- **The talker is weak in Arabic too; the voice is not the wait.** `gpt-oss-120b` scores 5.98 of 10
  on a public Arabic answer-from-passages test, against 7.29 for Qwen3.6-27B (the Groq Qwen model's
  predecessor) and 9.29 for Gemini 3.5 Flash; the knowledge base is Arabic, so English answers feel
  it too. Orpheus starts in 0.24 s; its gaps are pronunciation, pauses, and two speakers.
- **Speech-to-speech cannot be the product while invariant 2 holds** (every sentence is checked
  before it is spoken): a model that speaks directly speaks before our guard reads its text. In two
  calls the guard blocked two replies, a reply leaked the talker's reasoning and one ran on into a
  dozen questions, all caught in text first. Audio in, text out keeps the guard: a trial at the end.
- **Two lines of work at once.** Without a new provider: measuring (Phase 0); Phase 1's fixes (the search, the answers' rules, the repeats, how "Ole5" and symbols
  are said, the silence timer, the first connect, the widget's quick fixes, a short line as the
  search starts); then turn-taking and the language switch (2) and the widget's redesign (3).
  Beside it, on the keys the owner offered (2026-11-16) and the listeners: the STT, voice and
  talker bake-offs (4), then streaming STT (5) and the speech-to-speech trial (6). No dates are
  set: the work goes by gain per hour of work, the obvious wins first, as the owner asked.
- **The owner's time:** about 4-5 hours of the owner's own, two tester days, the knowledge base's
  source files, and an hour each from 5-10 native Saudi listeners ("What the owner does").

## What happens first

The owner approved the plan on 2026-11-16 and asked for the best improvement per hour of work and
the obvious wins first, with no dates; the same day they put the STT model and the language switch
first, and a flight-booking demo agent beside Ole5. So each step starts as soon as what it needs is
done, never more than two building at once (the laptop froze under five):

1. **The STT model and the language switch.** The provider guide, then the keys' settings and the
   candidates' adapters (Phase 4's Block 0, written before any key is pasted, since an unknown `T2V_`
   name stops the app), then the STT bake-off on the dev split, 0.6's items added once recorded. The
   switch (2.5) built now with Whisper's own detection on Groq, each STT candidate's own language
   measured beside it on H.
2. **The flight-booking demo agent** (Phase F) once Q23 is answered: the app, its mock airline, its
   scenarios as the main set.
3. **The obvious wins already half built,** finished one at a time: the calls report (0.1), "Ole5"
   said the owner's way (1.7), "OTP" no longer taken for the agent's echo (1.12), the warm-up (1.13),
   the widget's quick fixes and feedback (1.14); then the line at the search (1.15).
4. **Then wave 1's search and answer fixes** in L's registered order (1.1, 1.4, 1.2 with 1.3, 1.5
   with 1.6), each kept on its rule, with 1.11 and 1.8 beside them, on the flight set and Ole5's.
5. **The tester days** on wave 1, then on wave 2 and Phase 2; the voice bake-off once Q14 picks the
   voice's gender; the Qwen arm (Groq) in Phase 1; the redesign after 1.14.

## Words used here

- **STT** (speech-to-text) writes down what the caller said; **TTS** (text-to-speech) speaks the
  agent's text. **VAD** (Silero) says when sound is speech. **End of turn**: deciding the caller has
  finished; **Smart Turn** guesses it from the audio, **the hold** is the 600 ms we wait after its
  "complete" (D-067), and **the 3 s fallback** ends a turn after 3 s of silence when it never says so.
- **First audio** (`ttfa_ms`): from the caller's last sound to the agent's first useful sound,
  progress lines left out. **p50 / p90**: the median, and the value 9 in 10 stay under. **WER /
  CER**: the share of words / characters written wrong. **Confidence**: Whisper's own score.
- **The talker** writes the replies (`gpt-oss-120b` on Groq at reasoning medium, D-074).
  **The guard** checks each sentence before it is spoken (invariant 2); **the read-back** reads an
  action aloud before the caller's yes (invariant 1), and **the receipt** proves it played in full.
  **A clause**: one piece of a reply sent to the voice. **A function word**: «في», "with", "my".
- **Speech-to-speech** (S2S): one model hears and speaks audio; a **half-cascade** hears audio but
  writes text for our guard and TTS. **Streaming STT** gives words while the caller speaks.
  **Keyterms**: words a STT is told to expect. **Code-switching**: two languages in a sentence.
- **Runs**: K0 (search only), K (answers scored by a model, **the judge**), S (scripted calls), A
  (scripted ticket calls, zero violations required), T (first audio through the real voice), H
  (each turn's language); `poe eot` (end of turn), `poe overlap` (speech over the agent). **Dev /
  held-out**: items tuned on, and items measured once. **The sign test by item**: whether one arm won
  more items than chance explains. **An arm**: one version in a comparison; **a bake-off** compares
  candidates on the same items. **MOS**: a 1-to-5 listener score.
- **The team's-agent branch**: `plan-009-integration` and its six track branches, where voice for a
  team's own agent (LangChain, LangGraph) is built; its plan file exists only there, so this plan
  never cites it by number. **To port**: to copy one of its pieces to main, adapted.

## What the owner asked

- 2026-11-15: "Ok, since we finished the pure voice agent, I want to polish the voice experience to
  be at the level of top-tier voice agents. I believe we are still behind in Arabic and we can also
  improve the English and the overall experience. I have let some people try it today and they
  indicate that there are still improvements to do. What I have gathered from the feedback: *
  Caller first question has so much weight, the agent refuse to change topics easily. So we might
  need to add weight to later messages. while also preserving reasonable context * Find a reliable
  way to detect and change the language mid conversation * Find better Arabic/English STT models *
  Find better Arabic/English TTS models * investigate Speech-to-Speech models * Improve the UI/UX
  of the voice agent for better presentation * We want a seamless more natural voice experience *
  sometimes the model give up before searching and less repeated messages is wanted. This what I
  gathered, but I want you also to investigate ways to improve our system in ways that I might not
  be aware of (You have better context of this repo). We can see how top-tier voice agents do it
  and start from their or do our own way if it is better. So help me achieve the top-tier
  experience we are striving for."

## What we found

25 calls with 168 timed turns over 2026-11-11 (3 calls), 11-12 (12) and 11-15 (10, 49 turns), all
on the owner's laptop, counted once by hand from the raw logs; Phase 0's calls report replaces it (C).

### "The first question has so much weight"

- **Seen.** FSMRkwf (11-15): after "how can I reset my password?" (t0), every later question (OTB,
  OTP, change email, sign-up, "check the knowledge base") ended in "I'm sorry, I don't have that
  information." At t6 the answering passage («إضافة مستخدم جديد») was in the result at rank 7 and
  was refused; in WfTe the same passage answered the same question at t0. LTLrFU (11-12) t5-t6
  ("what tickets submitted with my" / "email") got t0's steps, six turns later.
- **Cause 1, kept results.** `Memory.keep` keeps each turn's tool calls and results whole and drops
  the oldest only when more than `KEPT_TURNS = 4` turns hold something (`agent/tool_calls.py:54`);
  plain turns never age it, though the docs say "the last 4 turns". FSMRkwf t6's second request
  held 35 passages from 5 searches, 14 of them distinct.
- **Cause 2, the same passages every time.** All 34 live queries contain "Ole5". A title-only stub
  is rank 1 in 30 of 31 results; title-only passages fill 62 of 217 slots, the documents' header
  passages 81 (37%); the sign-in passage came back in 25 of 31 searches, whatever was asked. In run
  K, queries with "Ole5" put a stub first in 73-79% of searches, without it in none. Steps are read
  from the first passage, so they were given in 1 of 31.
- **Cause 3, the rules.** The tool says "Call it once for any question" (`ole5_voice/agent.py:89`);
  nothing says a new question needs a new search, and with its own refusals in view the model
  refuses again, as research on multi-turn chat finds (Laban et al., ICLR 2026: an average 39% drop).

### "Sometimes the model gives up before searching, and fewer repeated messages"

- **Seen (11-15, 43 replies).** 13 refused, 8 with no search in their turn (FSMRkwf t4 "what does
  OTP stand for?", t7 "check the knowledge base, you will find some information"); 2 of the 8 rightly
  refused questions about how the agent was built (1n4W t0-t1), but t2 then refused Ole5's own
  technology, which a passage answers. Of the 5 refusals after a search, the knowledge base held an
  answer for 4. 5 replies copied an earlier one word for word; "Let me check the guide." opened 3
  turns in a row (MoIyy7). FSMRkwf had 6 refusals running and no ticket offered.
- **Causes.** The instructions allow "no information" without a search and say to give up when a
  search fails; an earlier refusal decides the next question; the search is dense only, so a term
  inside a long Arabic list (OTP) is missed; nothing detects a repeated sentence.
- **The repeat request is a different failure.** bYJ1 t0's 12-item list was 11% heard; "one more
  time" twice got "I can help you with Ole5." The talker holds only the cut reply's first clause
  with its cut mark (D-064); nothing tells it the rest.

### "Find a reliable way to detect and change the language mid conversation"

- **Seen.** No tester switched on 11-15: 7 of the 8 calls with heard words were English, every turn
  sent in the call's language. The one live switch on record (BNCyE1eV t27, 11-12): Arabic said in an
  English call was written "Wallahi laa", and the reply stayed English.
- **Today.** The caller picks the language before the call; the widget's buttons are disabled
  during it (`widget.js:116`), and D-038 fixes the language at join, so Whisper is told one language
  for the whole call.
- **Why no text check can catch it.** Told the wrong language, Whisper translates: an English
  question sent as Arabic came back as fluent, wrong Arabic; «لحظة» sent as English came back "one
  moment". English items sent as Arabic were right 0.080 of the time, 0.813 sent as English.
- **The classifier fails; Whisper's own detection works on longer turns.** The ECAPA classifier
  (D-086) wrongly switched 4 items in an ordinary call (its length gate counts silence), so it stays
  off. Whisper told no language, on turns of 1.2 s or more of voiced speech, found 37 of 37 English
  turns in an Arabic call and 104 of 121 Arabic turns in an English one, 0 wrong in an ordinary
  call (a replay of 222 variants: in-sample, one speaker, an older commit). Short turns ("yes",
  "okay") are where it fails, so they stay in the call's language.
- **The voice.** A switch already changes Orpheus's speaker (abdullah to troy), so it sounds like a
  transfer; and `en.md:4` and `ar-SA.md:4` tell the model to answer in the caller's language while
  the reply tag and the voice follow the call's.

### "Find better Arabic/English STT models"

- **Today.** Golden set dev (98 items, one speaker, the W1 prompt): Saudi WER 0.344 (0.430 of
  variants right), MSA 0.285, English 0.048, mixed sentences 0.077 right, product terms 0.333
  recalled. Live: "Ole5" heard right 0 of 9 times (Oly5, Oli5, ODI5, OTI5, "only five"); «كلمة
  المرور» 1 of 4 («كلمة المنور»); «إي نعم» 0 of 4, so xiM1 t3's yes was judged unclear; misheard words
  were read back in ticket drafts. About 8 of 49 Arabic turns (16%) were misheard in a way that
  changed what the agent did. The request takes 280 ms at the median, so it is not the wait.
- **The field (as the skeptics corrected it).** On SADA (Saudi TV): open whisper-large-v3 55.96% WER;
  ElevenLabs Scribe v2 33.96% and Speechmatics Melia 1 34.74%; open Audar-ASR-V1-Turbo 28.92% and
  Jais-ASR 30.85% (different parties' runs; none measures Groq's Whisper with our prompt). On Perle's
  300 Saudi Arabic-English sentences (its own staff, scripted), Scribe v2 21.3% against
  gpt-4o-transcribe 43.7%. Unmeasured on Arabic by anyone: Scribe v3 and v3 Live (2026-11-10),
  Soniox stt-rt-v6, Speechmatics' agent endpoint.
- **Cause.** Whisper has no Saudi mode, its prompt does not boost words, and a call holds one
  language (D-066). No gain can be shown yet on the voices that failed: the golden set has one
  speaker, no «إي نعم» item and 4 variants with "Ole5", and no tester audio was kept (no call of
  11-15 carried a signed consent). Whisper's confidence is read nowhere.

### "Find better Arabic/English TTS models"

- **Today.** Orpheus's first audio: median 237 ms (p90 300 ms English, 604 ms Arabic).
- **What callers hear.** "Ole5" said "Ole five" / «Ole خمسة» in every talker clause and read-back
  field that names it: `speech_of` speaks digits (`voice/session/open_reply.py:78`) before the
  pronunciation map runs (`echo.py:106-107`). Symbols are sent raw: "Ctrl + Shift + R" takes run at
  9-11 characters a second against an Arabic median of 15.8. `en.md:8`'s Latin-letter Arabic names
  gave a 16.8 s take, cut at 43% (FSMRkwf t0). English sentences are 0.48 s apart at the median, each
  its own request; Arabic goes comma by comma. A ticket number is 16 MSA digits (TD-058), about
  12 s. Two languages, two speakers.
- **The field.** No listening test compares vendors on Saudi speech; the one independent number is
  the Habibi paper's Eleven v3 alpha, dialect MOS 3.70, naturalness 3.45. ElevenLabs lists "Arabic
  (Saudi Arabia, UAE)" for Multilingual v2 (Flash v2.5 inherits it); v3 and v4 list "ar", the accent
  from the voice. Inworld TTS-2 lists Najdi and Hijazi codes (untested); SILMA offers a Najdi model
  (vendor figures only). OpenAI's text-to-speech models (tts-1, tts-1-hd, gpt-4o-mini-tts) shut down
  on 2027-01-06 and Hume's on 2026-11-13.

### "Investigate speech-to-speech models"

- **What the text checks caught.** _Hdmiy0 (11-12): at t8 and t9 the guard blocked two replies as
  claims; their text was not kept, and D-089 read them as an honest «ما فتحت التذكرة» blocked, since
  fixed. At t5 the talker's reasoning leaked into a reply. StIlp (11-11) t2 ran on into more than a
  dozen questions. Each is now caught or fixed in text before any sound (D-084, D-085, D-089).
  Invariant 2 needs that text before the sound; a model that speaks directly gives none.
- **The field.** Gemini 3.8 Live answers in audio only; GPT-Live-1 has no text mode; Grok Voice 3.0
  lists Saudi Arabic, but no page says how to switch audio off. OpenAI's gpt-realtime-2.1 and
  2.1-mini can answer in text only, which keeps every invariant. No S2S model has Saudi evidence; a
  trial is our own adapter (ARCH-BAN keeps Pipecat's realtime services out of the library). Much of
  the speed credited to S2S is our own end of turn: the 3 s fallback makes most of the slow tail.

### "Improve the UI/UX of the voice agent"

- The widget was built as a test page for the protocol (an access-code form, a recording box, Start,
  a greyed Stop and End, one line of state text); nothing reacts to voice. It hurt today: Arabic is
  the default whatever the browser (9cnu hung up on the Arabic greeting and restarted in English); a
  24 s connect showed a static "Connecting" (mrhy left); captions never scroll; a red error stays;
  Stop sits beside End; testers' feedback was gathered by hand, apart from the calls' events.
- The page's security rules allow an orb that follows both voices, and the library client already
  measures the agent's level. Nothing may become something the caller must read (D-075).

### "We want a seamless, more natural voice experience"

- **First audio, 11-15.** Plain turns p50 2,261 ms, p90 4,669 ms (32 turns); search turns p50 2,844
  ms, p90 5,437 ms (11 turns), against targets of 1.6 / 2.4 s and 3.0 / 4.0 s (latency.md). Silence
  before any sound: median 2.25 s, over 4 s in 21 of 144 turns.
- **Where a plain turn's time goes** (medians): 200 ms for the VAD to stop; about 225 ms more for
  Smart Turn's verdict; the transcript about 300 ms later; the model's first token about 680 ms
  after it (about 100 reasoning tokens); about 440 ms to the first audio frame; 190 ms in the
  browser. The 600 ms hold delayed nothing yet: in 73 early-start turns the first token never came
  150 ms or more before it ended.
- **The 3 s fallback.** 24 of 168 turns (14%; 9 of 49 on 11-15) ended about 3.19 s after the
  caller's last sound: about half short finished turns ("hello" four times, "thank you", "yes
  please"), most of the rest long finished sentences ("I think I have a problem, I cannot sign in");
  their first audio about 4.55 s against 2.08 s for the rest; 6 of the 14 English first turns. jAJT
  said "hello", heard the reply 5.2 s later and hung up.
- **The rest.** The progress line fired in 65% of searches, on a 2.6 s timer (D-073), always the
  same words, and the English answer waits behind 1.84 s of it plus a 0.4 s beat. About 0.43 s of
  silence between clauses; 13 of 168 replies dropped because a pause split the caller's sentence; 18
  of 30 replies over 30 words were cut.

### What you may not be aware of

- **The first call after a restart takes 10-24 s to connect** (the other 21 calls 235-2,745 ms);
  TD-089 names the cause and its fix, and each first turn is cold too. → 1.13.
- **The closing moment.** The 11 outcome lines ended 10.7-17.2 s after their actions; then nothing
  is asked (WcO4 sat silent 111 s), and the agent twice said "Okay, ending the call now." though it
  cannot end one. → 1.19, Q13.
- **A guard block or an unclear yes is spoken as a fault** («صار عندنا خلل بسيط، تكلم مرة ثانية لو
  سمحت»); the yes rule's model check gave up on 8 of 24 asks in run A (plan 007). → 1.20, Q15.
- **The greeting sets no expectations** (3 of 7 English calls began by greeting back), **the
  read-back sounds like a form** ("type issue, priority high: User cannot sign in..."), and **every
  fixed line addresses a man** («تبيني أرسلها؟»). → 1.18, Q14.
- **A correction can be taken for the agent's own echo**: "OTP, OTP" said over "...what OTB means"
  was judged the agent's words (`domain/interruptions.py:299-308`). → 1.12.
- **Short garbled turns are answered as if clear**: "shift the day any" got "Sure." → 1.21.
- **The talker forgets its reasoning between a search and its answer**, while OpenAI's guidance for
  gpt-oss keeps it across a turn's tool calls. → R3 in 1.22.
- **The judge is not trusted**: an agent blind to its verdicts disagreed on 7 of 24 answers, the
  limit 3 (plan 006). → 0.5, Q4.
- **No call explains itself**: no trace since 2026-11-01, no span for the talker's requests, no
  event saying why a notice played or why a turn waited, no record of the microphone. → 0.7.
- **Not in this plan:** real devices and networks (the deployment's own plan, the owner's ruling of
  2026-11-03, the roadmap's M6; a phone's browser joins Q5 if it can); several testers at once
  (TD-064); phone audio, only a reported arm; fine-tuning Smart Turn, which needs 0.6's recordings.

### How top-tier agents do it, and what we do

The owner asked how top-tier agents do it, to follow them or do better. From the practices study
(33 practices, each with its sources):

| Practice | Who does it | What we do | Same, or our own way |
| --- | --- | --- | --- |
| End of turn read from the words as well as the sound | LiveKit's turn detector, Deepgram Flux, Pipecat's model turn check | 2.1: at Smart Turn's "incomplete", lists, then `gpt-oss-20b` on Groq | Our own build of theirs: Flux and the other "eager" turn ends have no Arabic, Krisp's needs a licence, and ARCH-BAN keeps model-judged turn ends out of the library's Pipecat layer |
| A wait that adapts: short after a finished question, longer mid-phrase | LiveKit, ElevenLabs, Retell | 2.3, the hold set by the words | Same |
| The reply started before the turn is confirmed, dropped if the caller goes on | LiveKit (preemptive generation, on by default), Pipecat | already during the hold; 2.2 moves it to the detector's stop | Same |
| Low reasoning by default, more only when needed | OpenAI's voice prompting guide, Agora | 1.22's arms | Our own way: measured first, since D-074 found more invented answers at low |
| A progress line only when the wait is real, short, varied, never implying success | LiveKit (a 0.5 s timer), OpenAI's preamble rules, ElevenLabs | 1.15: a short rotated line as the search starts; 1.17: the model's own line, played only when every word came from the caller | Same, with a check theirs lack: the line can claim nothing |
| Search before "I don't know", retry once with other words; a variety rule and a loop breaker | OpenAI's and ElevenLabs' prompting guides, Decagon | 1.2, 1.3, 1.6 | Same |
| The latest turn over the first; old tool results trimmed | Laban et al.; Pipecat's summaries | 1.4 | Same |
| "Say that again" replays the last answer word for word | OpenAI's guide | 1.5, with the unheard rest after a cut | Same, and more |
| A switch tool the model calls, most permissive early in the call, moving voice, instructions and retrieval together | ElevenLabs (`language_detection`), Deepgram, Retell | 2.5: each turn's language detected, any question or request in the other language switching the call (the owner's ruling) | Same, held to Arabic and English |
| Text normalized for speech after the model | ElevenLabs, Vapi | 1.7, 1.8 | Same |
| One voice for both languages | ElevenLabs' and Inworld's voices | a criterion in Phase 4; 1.9 until then | Same goal |
| An audio-reactive orb and a live transcript | ElevenLabs UI, ChatGPT voice | Phase 3, subtitles by default | Same, captions optional: no caller must read (D-075) |
| Backchannels ("mm-hm") and a thinking sound | GPT-Live, Retell (off by default) | not now: echo and the interruption rule are at risk; revisited after 2.1 | Our own way, deliberately later |
| Whole calls simulated with personas and topic switches | Sierra (tau-voice), Coval, Cekura | 0.2, 0.4 | Same |
| Speech-to-speech in production | OpenAI Realtime, Gemini Live; Decagon keeps a cascade for its guardrails | a guarded cascade; Phase 6's half-cascade trial | Our own way, as Decagon's: invariant 2 needs the text before the sound |

## Goal

A caller, Saudi, MSA or English, gets a call that feels like a top-tier agent's: it hears them right
the first time, answers each new question on its own, searches before it says it does not know,
never says the same thing twice unless asked, starts speaking about as fast as a person would, says
Ole5 and its numbers the way the owner chose, ends a call gracefully, and follows the caller into
the other language as soon as they ask a question in it. Every invariant holds as written, the library and app stay split, and nothing
relies on a screen. Each gain is measured by a rule registered before its result, each provider or
model change kept only when it wins on our own calls and voices. The plan builds on today's main and
takes from the team's-agent branch only what improves the voice on its own.

## Acceptance criteria

**Phase 0**
- [ ] `uv run poe calls-report <day>` reproduces C's baselines for 11-11, 11-12 and 11-15, recomputed
  by the registered script and printed here before any change.
- [ ] The long-call scenarios registered (dev and held-out by scenario) and run once at be1a588;
  today's 25 calls replay through `TextCall`; the recordings imported, W1 run twice on the final split.
- [ ] Each turn's log, report and dev console carry its confidence, Smart Turn's end probability and
  its end reason; an event names why each notice played.

**Phase 1 (no new provider)**
- [ ] Every target check of the dev long scenarios holds in every play, the held-out ones (read once)
  are not worse, and run A dev has zero violations, its action targets no worse than `a5-dev`.
- [ ] K0: header passages under 1 in 20 slots (today 81 of 217); "Ole5" said the owner's way in
  every clause (a test on the talker path and a read-back).
- [ ] On a tester day of at least 10 calls and 50 turns: turns ended by the silence timeout end at a
  median of 2.1 s or less, first audio about 3.5 s or less (today 3.19 and 4.55 s); the first call
  after a restart connects in under 2 s (today up to 24 s); refusals with no search 0 outside
  off-topic turns (today 6); identical replies at most 1 in 50 (today 5 of 43); a feedback row a call.
- [ ] Run T on its fixed items: plain first audio p50 at most 1.6 s and p90 at most 2.4 s, search p50
  at most 3.0 s and p90 at most 4.0 s; live ones by outcome with each n, a p90 only on 20 or more.
- [ ] Each ported piece names its source commit; the team's-agent branch is unchanged.

**Phase 2 (turn-taking and the language switch)**
- [ ] Turns ended by the silence timeout under 2% live (today 14%); cut-offs not up on `poe eot`, its
  long-pause items among them; zero sends on the "yes, [pause] but" items; splits judged on its
  pause items. A question or request in the other language switches the call in that turn, both
  ways; no switch on the dev split's ordinary turns or on short replies ("yes", "okay").

**Phases 3 to 6**
- [ ] The widget's redesign reviewed by the owner, with no rise in false stops.
- [ ] Each bake-off decided by its registered rule and the owner's ruling, Orpheus, Whisper and
  `gpt-oss-120b` staying the baselines and fallbacks; no audio or text reaches a new provider before
  its trust-boundary row, data flow and secret setting exist.
- [ ] Streaming STT only if a candidate keeps its batch accuracy; a provider's language scores only
  on run H's rule; the
  speech-to-speech trial reported, every hard metric at zero.

**Every phase**
- [ ] `uv run poe check` passes, the docs it touched are updated (concepts.md's "last 4 turns"
  first), and each lasting ruling is a decision entry.

## The owner's decisions

The owner's ruling of 2026-11-15, given while the first draft was being written:

- 2026-11-15: "No I want to build on todays main, while only getting voice improvements from
  plan-9, I am not interested by integrating Langchain/Langgraph agents now. I just want to elevate
  the voice experience"

The owner's approval of 2026-11-16, given with replies to the draft's report (their answers to Q1,
Q2, Q16 and Q20 are under those questions):

- 2026-11-16, on the draft's "Days 1-2: four quick fixes": "Lets not set timelines, we will work at
  our pace"
- 2026-11-16: "Ok, I approve the plan. Lets start implementing, focus on what brings the best
  improvements by hour of work and obvious wins first."

So the plan sets no dates and orders its work by gain per hour ("What happens first").

The owner's request of 2026-11-16, after the laptop froze under the first build:

- 2026-11-16: "Also I have found a really good demo of an excellent Voice agent in
  "https://humain-air.share.sanad.ink/" I made an agent tear it down and analyze it (I have provided
  the file). For the sake of comparison, lets make our voice agent do a similar use-case (flight
  booking), and let make the ole5 as a reference or an assurance that both benefit from the
  improvements and a prove that the improvements are general, but lets make the demo and testing and
  comparing using the flight booking agent. Lets do the most important improvements now like the
  (STT model and language switching). Continue"

So a flight-booking agent joins Ole5 as a second app on the library (Phase F, Q23), and becomes the
main agent, the demo, the main test set and the comparison; Ole5 stays as the check that each change is general;
the STT bake-off and the language switch go first ("What happens first"). The teardown the owner
gave (a cascade of an Arabic-first in-house ASR, Gemma 4 and an in-house Gulf voice on LiveKit,
tools run in the page, a filler line at about 1.2 s and slow tools moved to the background at
about 4 s, its voice ducked before it stops, a typed code to confirm a booking) is read as a list of
practices, each one taken only through this plan's rows and rules.

So this plan builds on main at be1a588, does not wait for the team's-agent branch or build on it,
and takes none of its team's-agent work (LangChain, LangGraph, the relay, the talker front, the
board, the agent shapes); it ports only "What we take", and that branch stays untouched. Two
standing rulings settle what the draft asked: under time over money (2026-11-10), requests made only
to save time (a tiny request to the chat model, Whisper and Orpheus as a call joins; a Whisper
request at a pause; a duplicate chat request when the first token is late) are made, each behind a
setting and measured; and real devices and networks wait for the deployment's own plan (2026-11-03).

Each question carries the agent's recommendation; each answer is added under it in the owner's
words (`- YYYY-MM-DD: "..."`).

- **Q1. This plan as M9, now; M6 and M7 after.** A roadmap row "M9 · The voice experience at the
  level of top-tier voice agents" (the number before it is the team's-agent branch's), linking this plan, as the owner said on 2026-11-12 ("I want to
  skip M6 and M7 for now"); a new decision on main, since that order's entry exists only on the
  team's-agent branch. **Recommended:** approve.
  - 2026-11-16: "Ok, I approve the plan." Recorded as D-099.
- **Q2. The five pieces from the team's-agent branch**, each commit naming its source: (1) the check
  that lets a short "looking up X" line play only if every word came from the caller (1.17); (2) the
  rules for sending several sentences to the voice in one request, for fewer pauses (wiring them in
  changes how the history marks what was heard, D-064, so only on your yes, behind a setting, 1.10);
  (3) the chat connection kept warm, so the first reply is not slow (1.13); (4) a longer wait when
  the caller stops on a word like "with" or «في» (2.3); (5) each turn's record of how sure the STT
  and the end-of-turn model were (0.7, 1.21). **Recommended:** these five; nothing else.
  - 2026-11-16: "Ok, I approve the plan." So the five, each by path, the packing behind a setting.
- **Q3. Recordings, and what testers are told.** No tester audio was kept on 11-15. (a) A 30-minute
  recording session (0.6): you and any tester who agrees read a list of today's failures. (b)
  Testers' live calls recorded: the widget's signed token, the box ticked, `privacy.record_audio` on.
  (c) What testers are told, the decision D-076 leaves to a person before other callers use Ole5:
  their voice goes to Groq, an outside company, and in a bake-off to Q16's providers; the box's text
  says so. (d) The new long-call scenarios and today's missed questions (OTP, changing the email,
  Ole5's technology, sign-up) added as dev items to the registered sets. **Recommended:** all four.
  - 2026-11-16: "All four (Recommended)". So the recording session, testers' calls recorded with
    the box ticked, the box's text naming Groq and the bake-off's providers, and the new dev items.
- **Q4. One person who knows Ole5, about 1.5 hours** (answered: the agent reads, see below). (a) The judge's check (24 answers from the
  baseline's run and the first answer change's, partial answers and unanswerable questions among
  them); (b) if the judge fails again, a blind read of about 40-60 such answers, about an hour; (c)
  the facts the agent drafts for the long scenarios, about 30 minutes. Until (a) or (b), no change
  whose risk is invented answers moves a default. **Recommended:** yes.
  - 2026-11-16: "Can you judge it yourself? I have the files the knowledge-base is made from and
    they are not many. I can give them to you to judge."
  - 2026-11-16, on the agent's proposal (two readers that never see which version wrote an answer,
    each with the full source files, a third on disagreements, the owner spot-checking 5 verdicts):
    "Yes please." And on where the files go: "Yes, just create the folder and tell me to put them
    there". So the files go in `kb-source`, beside the repository and outside git; they are read
    only on this laptop; 0.5 is that read, and no person who knows Ole5 is needed.
- **Q5. The tester protocol.** About 10 tasks (guide questions, one not in the guide, a ticket, a
  repeat, a correction, a topic change, a language switch once 2.5 exists), half on a headset, both
  languages, a phone's browser if the laptop can serve it, the feedback button after each call; the
  browser reports its device kind and echo settings, a small `t2v/1` change (closed values, never a
  device's name). **Recommended:** as listed.
- **Q6. The search clean-up.** The app drops "Ole5" from a query when two words remain and skips a
  document's header passage (its title alone, or its title and one sentence about the file), asking
  for 10 passages and keeping 7; the knowledge-base owners are asked to fix the stubs.
  **Recommended:** app-only now, the owners asked.
  - 2026-11-16: "App fix only". So the clean-up is in the app, and the knowledge-base owners are not
    asked.
- **Q7. Honest misses.** A partial answer says what the guide does say; two misses offer a ticket.
  May the agent explain a common term the guide uses but never defines (OTP)? A question about how
  the agent was built gets one short line saying it cannot share that. **Recommended:** partial
  answers; general terms only when the guide uses them; the short line.
  - 2026-11-16: "All three (Recommended)".
- **Q8. The line at the search** (reversing part of D-073's 2.6 s timer). (a) Now: as the search
  starts, a short fixed line («لحظة، أشوف لك», "One moment, I'm checking") from 3-4 wordings, never
  the one said last, the pause after it cut to 0.1 s: first sound at about 1.4 s instead of 3.0 s
  (1.15). (b) Then, measured: the model's own line ("Resetting your password, one moment"), played
  only if every word came from the caller, so it cannot say anything wrong; about 1 in 5 pass (1.17).
  **Recommended:** (a) now; (b) only on its measurement.
  - 2026-11-16: "(a) now, (b) if measured (Recommended)".
- **Q9. The 3 s fallback.** Lowered to 1,800 ms, except while the caller answers a read-back ("yes,
  but change ..." must not be cut after "yes"), kept only if it cuts no more long pauses (E); then a
  word check at each pause (2.1). **Recommended:** both, in order.
  - 2026-11-16: "Both, in order (Recommended)".
- **Q10. The repeat after a cut.** After a cut reply, the talker knows only that its first sentence
  was partly heard. We propose the unheard rest as a note marked "not heard" (amending D-064), and
  "one more time", "pardon" and "what did you say" among the English repeat words (amending D-062's
  lists, the notices' words kept out). **Recommended:** yes.
  - 2026-11-16: "Yes, both (Recommended)". D-064's and D-062's amendments are written when 1.5
    lands.
- **Q11. How terms are said.** As you chose "Ole5", choose among 2-3 spoken forms each for Ctrl +
  Shift + R, IP, OTP and the Arabic menu names English replies write in Latin letters (`en.md:8`).
  **Recommended:** "Control Shift R", "I P", "O T P"; «كنترول شفت آر», «آي بي», «أو تي بي»; menu names
  by their English meaning.
  - 2026-11-16: "As proposed (Recommended)".
- **Q12. Steps per reply.** D-075 keeps every step in one reply; 18 of 30 replies over 30 words were
  cut. **Recommended:** keep it, but lead with how many steps there are, say at most three list items
  in a sentence, and offer the steps for another role rather than read them (FSMRkwf t0 read out how
  an administrator resets someone else's password); "the first three, then 'want the rest?'" only as
  a measured arm if you want it.
  - 2026-11-16: "Keep as is". So replies keep every step as today; 1.2 adds no step rule.
- **Q13. The ending.** The ticket number said shorter, as its last four digits and "saved under your
  name" (reversing plan 007's Q6, so the whole number stays sayable on request; a card on a screen
  never counts as the way to get it), or four groups in Saudi number words; "Anything else I can
  help with?" after an outcome; a short goodbye, then the call ends, with nothing pending; "Are you
  still there?" after about 25 s of silence. **Recommended:** the last four digits, and all three.
- **Q14. The persona and the greeting.** A name or none; the voice's gender (it ties the voice
  bake-off); tone; how it names itself; whether it says it is an AI; a greeting that holds the scope
  and, once 2.5 exists, offers the other language; fixed lines in forms that fit both genders.
  **Recommended:** a one-page persona written together, about 30 minutes.
- **Q15. After a block or an unclear yes,** the caller hears a fault notice today. We propose: after
  a claim block, the talker asked once more; if blocked again, an honest line from the call's record
  ("There's no ticket from this call yet. Want me to open one?"), whose yes goes through the normal
  read-back; after an unclear yes, a short re-ask. And the yes check, which gave up at 2.5 s on 8 of
  24 asks in run A, given a faster Groq model or a wait set by how often it is needed (the amendment
  of D-082 plan 007 left open). **Recommended:** as said.
- **Q16. D-004, for measurement.** As with Groq today (its data is kept in the US), these vendors
  process in the US or EU; what changes is who receives callers' audio or text and how long they
  keep it, listed before each run: ElevenLabs (STT, TTS); Soniox, Speechmatics, Cohere (STT); OpenAI
  (STT, the speech-to-speech trial, a listening sample); Inworld, SILMA, optionally Voho (TTS);
  Google (a Gemini Flash talker arm, a Gemini Live sample); xAI (a Grok Voice sample).
  **Recommended:** amend it for measurement on the owner's and testers' calls; production stays Groq.
  - 2026-11-16, on the draft's "Arabic speech-to-text is the biggest gap": "I can provide some new
    models providers for you if you make a search and give the best ones to test"
  - 2026-11-16, on the draft's "Once you allow other providers and send keys: Side-by-side
    comparisons of speech-to-text, voice and talker models": "I can provide this today if you
    guide me to the best options we can have"
  - So other providers are measured on the owner's and testers' calls, after a guide to the best
    ones to sign up for; a provider becomes a default only on its bake-off and the owner's ruling.
    The amendment of D-004 is written when the first provider's adapter lands (Phase 4's Block 0).
- **Q17. The cost cap and the listeners.** $10 a spending run after a dry estimate; 5-10 native Saudi
  listeners, about an hour each, rating about 40 lines from at most three candidates and Orpheus,
  blind. **Recommended:** as said.
- **Q18. A preview talker model.** `qwen/qwen3.8-27b` is on Groq but a preview that "may be
  discontinued at short notice". **Recommended:** measure it; a default only with `gpt-oss-120b` as
  its fallback.
- **Q19. Streaming STT and the early search.** A new port and bridge (large), only if a streaming
  candidate keeps its batch accuracy; a search started on the heard words as the turn ends, amending
  invariant 4 (a transcript never selects a tool by itself) for the read-only knowledge search only.
  **Recommended:** decide after Phase 4's STT result.
- **Q20. Changing language.** By voice in both directions, now (Phase 2, amending D-038); later, on a
  long turn in the other language, switch the reply at once, only in the first two turns, or after
  two such turns; the classifiers (D-086) retired if unused. **Recommended:** on request at once; on
  detection in the first two turns or after two long turns.
  - 2026-11-16, on the draft's "Switching when the caller asks ("English please") is reliable and
    needs no new provider": "No, any English question or request should be enough to change the
    language and vice versa. We can achieve this be trying other providers STT, maybe they have
    auto-detection, they give probabilities or we use a language classifier to lock the language
    between Arabic and English."
  - So any question or request in the other language switches the call in that turn, both ways;
    short replies ("yes", "okay", "thanks"), names and product words keep the call's language.
    Each turn's language is detected, held to Arabic and English: Whisper's own detection first
    (Groq), then each STT candidate's language and score and a two-language classifier, kept on H
    (2.5). D-038's amendment is written when 2.5 lands.
- **Q21. The widget.** Who it is for (testers here, or the website later); captions off, a subtitle
  line or the full transcript; a card with the ticket number (opt-in, an extra D-075 allows); a
  "caller speaking" message in `t2v/1`. **Recommended:** subtitles and the card; the message proposed.
- **Q22. The speech-to-speech trial.** A time-boxed half-cascade arm (gpt-realtime-2.1-mini, text
  out, our guard and TTS), never the product path while invariant 2 stands. Would the owner ever
  accept a false claim caught after it is spoken? **Recommended:** the trial; no to that.

- **Q23. The flight-booking demo agent** (the owner's request of 2026-11-16, Phase F). A second app
  on the library's public API, `apps/flight-voice-agent/`, beside Ole5: a mock airline (about a dozen
  airports in the Kingdom and the region, each with its Arabic and English names, a fixed seed of
  daily flights, fares and cabins over a booking window, a demo traveler with a home airport and past
  trips); read-only tools (flights searched, a month's cheapest days, cabins compared, the trip so
  far, the traveler's profile), each result saying plainly what failed when it fails; and one
  action, booking the trip, read back in full and confirmed by a spoken yes (invariant 1). Its run S
  and run A scenarios (booking calls in Saudi Arabic, MSA and English, mid-call switches,
  corrections such as "no, the 14th", "the cheaper one", relative dates) become the plan's demo and
  main test set; Ole5's sets stay as the check that each improvement is general. To decide: (a)
  voice only, or the spoken options plus a card list on the page that mirrors what was said and is
  never needed (D-075's opt-in extra); (b) the read-back and the spoken yes, or also a typed code as
  the public demo does; (c) the persona's name and voice (with Q14); (d) its own page served by the
  app, or a switch on Ole5's page. **Recommended:** (a) spoken, with the optional cards; (b) the
  spoken yes; (c) chosen with Q14; (d) its own page.
  - 2026-11-16: "I want the flight agent to be our main agent we show and work on. You can
    investigate "https://humain-air.share.sanad.ink/" to see how they did it"
  - 2026-11-16: (a) "Spoken + optional cards (Recommended)"; (b) "Read-back + spoken yes
    (Recommended)"; (c) "A male Saudi voice, name later (Recommended)"; (d) "Its own page
    (Recommended)". So the flight agent is the main agent shown and worked on; the agent proposes
    2-3 names for the persona and the airline.
  - 2026-11-16, the names: "Saad / سعد (Recommended)" and "T2 Air / طيران تي تو (Recommended)".

### When each question comes

- **At approval:** Q1, Q2, Q16 and Q20, answered on 2026-11-16; Q3 and Q4 answered the same day;
  Q17 before the voice bake-off. **Before Phase F:** Q23.
- **Before wave 1:** Q6 to Q12, all answered on 2026-11-16. **Before the
  first tester day:** Q5.
- **Before wave 2:** Q13, Q15, and Q14 (sooner if the voice bake-off is ready); Q18 before the
  talker arm, which may run during Phase 1.
- **Before Phase 3:** Q21. **After Phase 4's STT result:** Q19. **Before
  Phase 6:** Q22. **Not scheduled:** whether the team's-agent branch is ever merged after this.

## What we take from the team's-agent branch

That branch started at main's be1a588 and by design changes almost nothing in today's call: 23
pure-move splits, seams for a team's agent, a test pinning the native request, and six tracks that
build for a team's agent. Five pieces work on their own and improve a normal call. Each is ported
**by path only** (`git show <sha> -- <paths>` applied, or `git checkout <sha> -- <paths>`), never a
whole cherry-pick, which would bring that branch's plan file and its relay and front modules; each
commit carries the trailer "Ported from <sha> (plan-009-integration)"; each ported docstring drops
its plan citation and its team's-agent framing ("their agent", "the team's system_name", "the fronts").

| # | Piece | Source commits and paths | What lands on main | Worth, from the branch's spikes | Row |
| --- | --- | --- | --- | --- | --- |
| P1 | A spoken line at the search, checked against the caller's words | 2ed31de (`domain/heard_match.py`, `domain/text/function_words.py`, `test_heard_match.py`); 664bd08 (those files' hunks only); 40fa334 (the `say` field's wording, as data); spike S7 in e3a8f9d | the check (`check_acknowledgement`, `echo_words`) as new files; used in `actions/knowledge.py`, `agent/tool_calls.py`, `agent/clause_gate.py`, `voice/session/talker_progress.py`, Ole5's `agent.py` | gpt-oss filled `say` in all 263 decisions (p50 0.55 s); only 33 of 155 lines kept every content word (S7.3), so about four searches in five fall back to 1.15's line | 1.17 |
| P2 | Packing rules for speech requests | 0da23da (`voice/tts_packing.py` and `test_tts_packing.py` only) | the pure rules (the first piece alone; a greedy join up to `max_chars`; a line of ours alone), `ClauseMark` a local Literal (heard, cut, unsaid), not the board's; the wiring is new work (1.10) | the first clause still goes alone, so first audio does not move; fewer cache hits | 1.10 |
| P3 | A warm chat connection | 4d75e3e (`adapters/groq_chat.py`'s hunk, which applies as is, and `test_groq_chat_warmth.py`); 1ca5fbe (`domain/ports/connection_warmth.py` alone); spike S6b in 48a19d0 | `GroqChat.warm()`, the port, its test; used at the call's join and as a per-request flag in the turn's metrics | first requests on a new connection 0.62-1.58 s against a warm p90 of 0.42-0.93 s | 1.13 |
| P4 | A hold that reads the words | 2ed31de, 664bd08 (`ends_on_function_word`, in P1's files) | used in `voice/turn_hold.py`, `voice/session/talking.py`, `core/settings/turns.py`; the please words («لو سمحت», "please") left out, since in Saudi speech they end a finished request | 8 of 51 paused requests split at a 0.66-0.78 s pause and a 0.3 s grace joined them all; Smart Turn cannot tell such a pause from an end (S9) | 2.3 |
| P5 | Each turn's confidence and Smart Turn's end probability | a1c6b08 (the hunks of `voice/smart_turn.py`, `stt_bridge.py`, `voice/session/turn_book.py`, `session_events.py`; `test_stt_end_probability.py`; `heard_turn.py`, adapted for 1.21); b1906bc (only the fake session's `confidence`) | the probability in the turn's metrics and log; new on main: both numbers in `core/call_report.py`, `voice/session/report.py`, the dev console | on turns of four words or fewer a -0.65 floor caught 4 of 11 garbled turns and asked again on 0 of 21 clear ones (S9.5, in-sample) | 0.7, 1.21 |

**Left on the branch:** the LangGraph and LangChain adapters, extras and sample agents (ruled out);
the talker and relay fronts, the turn judge, chat turns, the board, agent mode, their seams and
decisions; speaking a team's answer (`answer_requests.py`, `answer_speech.py`, `ClauseReports`),
built for an answer that arrives whole (its symbol names may serve 1.8 as data); the 23 splits,
redone here by hand only when a block needs one; the native baseline pin; LoopLag, ported only if
2.2 needs it; the validator typed by `Self` (its lesson stays: the last gate with `.mypy_cache`
removed). If that branch is ever merged after this plan, its splits will conflict with this plan's
edits in `agent/` and `voice/`: a later decision, only if the owner wants it.

## Plan

Built as the plans README says: small blocks in their own worktrees, each reviewed by an agent that
did not write it and gated by `uv run poe check`. A change to a measured outcome lands behind a
setting with a characterization test of the default (GP-18); a security change ships with
adversarial tests (GP-08); a module grown past 300 lines is split first, as a pure move. Effort:
small is under a day of the agent's work, medium a few days, large a week or more. **Line one, no
new provider:** Phases 0 to 3. **Line two, on the owner's answers and keys:** Phases 4 to 6.

### Phase 0 · Measure first

| # | Change | Where | Effort | Gain | Measured by | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| 0.1 | The calls report: per call and day, abandoned calls, each turn's outcome, refusals with no search, identical and near repeats, the caller's repair words ("one more time", "wait wait", "I said"), the share of turns by end reason, first audio p50/p90 by language and kind, played share and cuts, progress lines, notices and their causes, questions left unanswered (a list for the knowledge-base owners), device and feedback once recorded | app `ole5_voice.evals`, a new `poe calls-report`, reading `var/dev-console` and `var/ole5/feedback` only | small | one baseline for every block, rerun free after each change | C, checked by hand on 3 calls in both languages | a definition tuned to a result: registered once, here |
| 0.2 | Long-call scenarios, 6-8 turns, split dev and held-out by scenario before any run. Dev: FSMRkwf replayed in English and Saudi; a miss then two answerable questions; off-topic then an Ole5 question; a repeat after an early cut; "check again"; a correction that widens the problem (_Hdmiy0's outage); a return to an earlier topic; a ticket call ending with thanks. Held-out: 3-4 written apart, on other topics, both languages, the same checks | app `evals/scenarios/` (run S), `evals/actions/` (run A) | small | the testers' failures (turns 4 to 7) measurable; today's longest scenario has 3 turns | L | facts drafted by the agent from the knowledge base, checked by Q4's tester |
| 0.3 | Today's 25 calls replayed by their heard words | the testing kit's `TextCall` | small | a free regression of the exact failures | L's checks | none |
| 0.4 | A simulated caller: `gpt-oss-120b` on Groq with a persona (Saudi, MSA, English), 3-5 topic changes, repairs, product names misheard as today (Oli5, OTB, «كلمة المنور»), an out-of-scope ask; it drives `TextCall`, a few through Orpheus into `AudioCall`. Not a gate | library `testing/` (the caller's protocol), app persona files | medium | long calls between tester days | judge-free checks, scenarios registered before results | a model caller drifts: scripted goals, a turn cap |
| 0.5 | The trusted check of answers (Q4): the judge's check on 24 answers drawn from the baseline's run and the first answer change's, or the blind read of 40-60 none-item and partial answers | `poe judge-check`; two agent readers blind to the arms, holding the knowledge base's source files, a third on disagreements, the owner's spot-check of 5 (Q4) | small | the invented-answer risk of 1.2, 1.22 and the talker arms readable | the judge's rule (at most 3 of 24 disagreements), or the blind read | if neither is done, those defaults wait |
| 0.6 | The recording session (Q3), through `poe record`, you and any tester who agrees reading a scripted list: «إي نعم», «ايه نعم»; Ole5 and OTP in both languages; «كلمة المرور», «تسجيل الدخول», «معلّق»; at least 10 term items a language; mixed sentences; about 10 long-pause items, 2-3 variants each in Saudi and English, with pauses of 1.2-2.8 s (a ticket number read in groups, "I want to ... change my email", a list); "yes, [pause] but ..." items; switch requests. Testers' live calls recorded once Q3 allows | `poe record`, `import_calls`, `evals/golden/`, `split --keep` | small | every STT, turn and language candidate judged on the failures and on more voices than the owner's | `poe golden --check`; W1 run twice on the final split for the noise | held-out must take the new voices evenly |
| 0.7 | Each call explains itself: each turn's confidence and Smart Turn's end probability (P5); each turn's end reason (Smart Turn's "complete" and the hold, the silence timeout, the longest silence); the longest silence after an "incomplete" the caller resumed from; an event naming why each notice played; a span per chat request (effort, input, cached, reasoning and output tokens, first token, how it ended); the chat model's rate-limit headers; Q5's device fields; Phoenix on 127.0.0.1 on tester days | library `voice/stt_bridge.py`, `voice/smart_turn.py`, `voice/session/turn_book.py`, `session_events.py`, `report.py`, `core/call_report.py`, `adapters/groq_chat.py`, `voice/protocol.py`, `api/static/dev-console.js`, `t2v-client.js` | small | false stops traced to speakers; the fallback counted by its mechanism; no hand-rebuilt diagnoses | the calls report reads them | `stt_bridge.py` (367) and `report.py` (364) split first; the protocol fields closed values only |

Phase 0 has no gate of its own: wave 1 starts after Block 0, read against the baselines run at
be1a588 and the last kept arm; the trusted check (0.5) holds back only defaults that risk invention.

### Phase F · The flight-booking demo agent (the owner's request of 2026-11-16, Q23)

The main agent shown and worked on (Q23). Its build spec, the mock airline, the tools, the booking
action, the page, run F and the build order, is [flight-voice-agent.md](../../design/flight-voice-agent.md),
written and reviewed on 2026-11-16 (D-101).

| # | Change | Where | Effort | Gain | Measured by | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| F.1 | The app: its settings, server, page and persona, on the library's public API only (ARCH-PUBLIC), registered in `harness.toml` beside Ole5 | `apps/flight-voice-agent/`, `harness.toml`, the root `pyproject.toml` | medium | a second app proving the library general | the gate; a call through the page | the harness's app rules |
| F.2 | The mock airline: airports with Arabic and English names, a seeded schedule and fares, cabins, a demo traveler; read-only tools whose failures say so; the booking action with its read-back | the app's `airline/`, `tools/`, `actions` | medium | booking calls end to end, in both languages | unit tests; run A's booking scenarios at zero violations | a tool failure read as "nothing found": each failure result says what failed |
| F.3 | The flight set: run F's scripted flight calls (the flight spec's 7.1; rule F below), dev and held-out, with switches, corrections and relative dates; 0.6's recording list gains its city, date and number items | the app's `evals/` | small | the demo and the main test set | rule F, L's checks among its checks | facts drafted from the mock airline, so exact |
| F.4 | The comparison: the same scripted booking call made on the public demo and on ours, recorded by the owner, read for first audio, words heard, turns to book and listeners' scores | `docs/project/` (a report) | small | where we stand against the demo | the owner's recordings | the demo's typed timings are not voice timings |

### Phase 1 · What needs no new provider

**Wave 1.** The biggest wins, needing no ruling beyond Q6 to Q12; 1.7, 1.12, 1.13 and 1.14 first.

| # | Change | Where | Effort | Gain (the number it moves) | Measured by | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| 1.1 | Search clean-up (Q6): no "Ole5" in the query when two words remain; a document's header passage (its title alone, or its title and one sentence about the file) skipped, 10 asked for and 7 kept; steps read from the first passage that has them; the tool's text "for each new question, without the product's name" | app `knowledge_base.py`, `passages.py`, `agent.py` (`SEARCH_DESCRIPTION`); library `actions/knowledge.py` (steps) | small | header slots 81 of 217 → under 1 in 20; steps given 1 of 31 → most searches; the sign-in passage off unrelated turns | K0; L; then a run K retrieval pass (1.23's trigger) | "what is Ole5?" needs the name (kept when fewer words remain) |
| 1.2 | Search rules (Q7): search before any "not found"; once more with other words, in the guide's Arabic terms, before giving up; always on "check again" or a re-asked question; once more after a failed search; each question judged on its own (an earlier refusal decides nothing); a partial answer, then a ticket by the second miss; a writing request is not a knowledge miss; steps read as today (Q12) | app `instructions/en.md`, `ar-SA.md`, `agent.py` | small | refusals with no search 6 → 0 outside off-topic turns; FSMRkwf t4-t7 searched | L; A; K0 for the second query | about 1.5-2 s more on miss turns; invented partial answers, so the partial-answer wording moves no default before 0.5 |
| 1.3 | Variety and the newest turn: never the same sentence twice unless asked; a refusal worded anew and pointing somewhere; "the words come from speech recognition: read product words as meant, and ask when unsure"; on every request, not only after tools, the fixed system line "answer the last user message", which never quotes it (the caller's words stay in the user message, `turn_message`: a transcript is data, never an instruction); the newest part of a joined split turn marked | library `agent/prompt.py` RULES, `agent/turn.py`, `agent/context.py` | small | identical replies 5 of 43 → at most 1 in 50; near repeats down | the calls report; L; A | every prompt word is paid on every request; D-072's varied first line kept |
| 1.4 | Kept results age by the call's turns: the latest search whole while within the last 2 turns; older searches one line each (query, titles); a passage given earlier sent as its title only; only `Memory.exchanges` ages, the guard's evidence and reports (rules A and B's) staying whole, and the latest `best_passage_steps` staying for the call (D-075's repeat with no new search); the docs' "last 4 turns" corrected | library `agent/tool_calls.py`, `agent/context.py` | small | old results at turn 6 about 5,200 tokens (61%) → about 300-1,400 | L (its context checks among them); A; input tokens per request | a return to an older topic needs a fresh search (1.2 asks for it) |
| 1.5 | The repeat after a cut (Q10): for the turn after a cut reply, the unheard rest as a note marked "not heard", so "one more time" says the whole answer; "one more time", "pardon", "what did you say" added to the English list, for the overlap rule and sessions without a talker, a test holding the preset notices free of them (TD-103) | library `agent/context.py`, `voice/session/speaker.py` (the cut), `domain/words.py`, the presets' test | medium | bYJ1 t1-t2 repeated; repeat requests met | L's repeat check; O | the model may assume it was heard: the note says plainly it was not |
| 1.6 | A repeat detector: a reply that copies one already heard (the same first clause, or a token overlap of 0.8 or more), outside a repeat request or a read-back, is logged and a note goes to the next request; a block and re-ask only if the rate stays high | library `agent/clause_gate.py` | medium | repeats measurable and self-correcting | the calls report; L | false hits on asked repeats and read-backs, excluded |
| 1.7 | The speaking order: the pronunciation map before digits are spoken, with a test of a mapped form holding a digit on the talker path and on a read-back field | library `voice/session/open_reply.py` `speech_of` | small | "Ole5" said the owner's way in every clause | the test; the clause cache's new takes | none: the cache keys on the text sent, so old takes stop playing |
| 1.8 | Speech shaping, by rules: key combinations, IP and OTP as Q11 chose; brackets, parentheses, quotes, U+2011; an abbreviation guard (Mr., Mrs., Dr.) so a sentence does not end there; URLs, emails, dates, times, "%" and "/"; Ole5's map gains OTP, IP, Ctrl; `en.md:8`'s Latin transliteration dropped; no parentheses, quotes or key symbols asked of the model; `en.md:4` and `ar-SA.md:4` made to say "answer in the call's language", which the reply tag and the voice follow | library `domain/text/speaking.py`, `clauses.py`; app `agent.py` `PRONOUNCE`, instructions | small | affected takes from 9-13 to about 16-17 characters a second; no bracketed text spoken; no Arabic letters sent to the English voice | unit tests per form; the probe over the logs; the owner's listen | a term the caller needs verbatim rewritten (captions keep the written form) |
| 1.9 | The English voice nearest abdullah, picked by the owner's ear among Orpheus's English voices, so a switch does not sound like a transfer | app settings (`tts.languages`) | small | the persona's feel across languages until one voice speaks both | the owner's listen | none |
| 1.10 | Joins: TD-061 paid first (the phrase cache keys the trim setting and the adapter); each take's trailing silence trimmed, and its leading silence after the first, to about 0.1 s; then, behind a setting (Q2), packed requests: after the first clause, sentences the guard passed joined up to 200 characters, Arabic by sentence, a cut's heard share spread by characters (D-064's amendment); each read-back part and each outcome line always its own request | library `adapters/phrase_cache.py`, `wav_stream.py`, `groq_tts.py`, `voice/tts_packing.py` (P2), `open_reply.py`, `echo.py`, `tts_bridge.py`, `history.py`, `speaker.py` | medium | English joins 0.48 s median → 0.2-0.3 s; Arabic said in sentences; fewer requests a minute (a call peaked at 25.9) | J; tests that a packed request never holds a read-back part and that the receipt still follows the summary's own `ClausePlayed` | a soft ending clipped (the first take untrimmed); a gap if the model is slow; fewer cache hits |
| 1.11 | The 3 s fallback lowered to 1,800 ms (Q9), except on a turn answering a read-back, which keeps today's 3 s | library `core/settings/turns.py`, `voice/session/talking.py` | small | turns ended by the timeout at about 2.0 s instead of 3.19; their first audio about 3.2 s instead of 4.55 | E | more cut-offs of real pauses (what D-067's hold was for): E's long-pause items |
| 1.12 | Own words: a word written all in capitals one letter from the agent's is not echo when the caller says it ("OTP" against "OTB"), as a new parameter of `judge()`'s step 4 that takes the raw transcript; `own_words`, which the yes rule's echo rail reads, unchanged | library `domain/interruptions.py` (308: a split first) | small | FSMRkwf t2 answered | O; `test_yes_ask_echo.py` and `test_yes_ask_tail.py` unchanged; a new test that such an echo of a read-back stays the agent's for the yes rule | real echo of an acronym let through (step 2's echo rule still covers it) |
| 1.13 | The warm-up: Pipecat and aiortc imported, Silero and Smart Turn sessions made, in `VoiceCalls.start` at the server's start (TD-089's fix; `api/runtime.py` only calls it); the warm connection (P3) checked as a call joins, a fresh one opened in the background after a cancelled stream (TD-115); one tiny request each to Whisper and Orpheus at join; the connect's server steps logged as timings only, never addresses or candidates | library `voice/calls.py` (310: a split first), `api/runtime.py`, `adapters/groq_chat.py`, `domain/ports/connection_warmth.py` (P3) | small | first-call connect 24.3 s → under 2 s; first-turn transcript 733 → about 490 ms | W; the per-request warm flag | longer start-up, more memory |
| 1.14 | The widget's quick fixes: the language from the browser and remembered; Enter starts the call; captions follow the newest line; notices as a toast that clears; ended reasons in plain words; an animated connect, "still connecting" at 5 s and "try again" at 20 s; Stop shown only while the agent speaks, as "Interrupt"; End a red hang-up; "Waiting for your yes"; a guard against reload during a call; captions not read aloud by screen readers. And a thumbs and a comment after each call, posted to a new app route that needs a signed, single-use token the server gives the page for that call (the offer secret dies with the call), takes a strictly parsed, bounded body, and writes under `var/ole5/feedback/` by the server's own call ID | app `web/widget.js`, `index.html`, `widget.css`, `server.py` and the feedback route, their tests | small | no Arabic-by-default restarts (9cnu), no silent 24 s connects (mrhy); a feedback row per call, tied to its events | the calls report (calls with 0 turns, ended by leaving, restarted in the other language); widget tests | invariant 7 (the call ID is never a credential), held by the route's token |
| 1.15 | The line at the search (Q8 (a)): a fixed line of about 0.8 s or less as the search starts, from 3-4 wordings a language, never the last one said, holding no stop, repeat, yes or send word (a test reads them); the beat after it 0.1 s | library `voice/session/talker_progress.py`, `agent/tool_calls.py` (`ProgressDue`), `echo.py` `BEAT_S`; app `agent.py` `PROGRESS` | small | a search turn's first sound about 3.0 s → about 1.4 s on every search; English answers 1.5-2 s sooner where today's line plays | P | a line in front of a fast answer: kept shorter than the gap from the tool call to the answer (about 1.1 s) |
| 1.16 | A term fix after STT: near forms of the agent's vocabulary (Oli5, Oly5, ODI5, OTI5 → Ole5) mapped by a list in code, letters only, never adding or changing a digit, given to the talker as an added note and to the search query; the raw transcript stays in the heard words, rule B's evidence, the history and the report; no note on a turn the yes rule takes; the model's part is the talker's own reading under 1.3's line, no extra request; and an Arabic domain vocabulary in the Arabic Whisper prompt (arm W2) | library: a pure `domain/` function at the seam where the heard words reach the talker (Block 0); app `VOCABULARY` | small | "Ole5" 0 of 9 heard right; misheard terms in queries | W2; the list fitted on stored results, then fresh; an adversarial test that a correction adding a number gives the guard no evidence | "only five" corrected when meant: only next to the agent's own words |

**Gate:** each change kept or dropped on its rule, in L's registered order; run A dev with zero
violations; the held-out long scenarios read once; then the first tester day (Q5), read by C.

**Wave 2.** What needs a ruling or a measured arm, built behind settings while the tester day is set.

| # | Change | Where | Effort | Gain | Measured by | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| 1.17 | The model's own line at the search (Q8 (b), P1): the knowledge tool alone (never an action's tool) gets a `say` field, a pydantic field with a length bound (600 characters, as the branch has it); the line plays as the tool call arrives only if code finds every content word among this turn's heard words (Ole5 as the system name, the vocabulary as terms), it holds no stop, wait, repeat, yes or send word, and it passes the clause gate exactly as a clause does (the stray-script filter, the leak check, the question limit, rules A and B); it obeys D-070's kept reply and D-073's conditions, and is recorded as a played clause in the heard history; otherwise 1.15's line plays | library `domain/heard_match.py`, `domain/text/function_words.py` (P1), `actions/knowledge.py`, `agent/tool_calls.py`, `agent/clause_gate.py`, `voice/session/talker_progress.py`; app `agent.py`, instructions | medium | the caller's own topic in the line where it passes (about 1 in 5 by S7.3); otherwise 1.15's gain | P | a stray model line: the gate, the check and the bound together |
| 1.18 | The lines: the read-back's summary as the caller's problem in plain words, no "User" or «مستخدم»; each ticket type said as a phrase ("a ticket about a sign-in problem"); the greeting and persona (Q14); fixed lines in forms that fit both genders | app `tickets/lines.py`, `agent.py`, instructions; library `domain/presets.py` notices | small | read-backs that sound spoken; fewer re-greets (3 of 7 English calls) | A (right fields, zero violations); the owner's listen; C | the read-back stays a template, so invariant 1's receipt is unchanged |
| 1.19 | The ending (Q13): the number said shorter, the whole number on request; "Anything else I can help with?"; a goodbye, then the call ends, only with nothing pending (no read-back waiting, no yes being asked, no action job whose outcome is unsaid), lists first and the talker's judgement for the rest; "Are you still there?" after about 25 s; never saying it is ending, transferring or calling back unless it can | app `tickets/lines.py`, instructions; library session (a new module for the check-in and the hang-up) | medium | outcome lines of 10.7-17.2 s → about 4 s; no 111 s silent endings | C (silence after the outcome, who ended the call); A | a goodbye heard where none was meant: the pending rule blocks it |
| 1.20 | Recovery (Q15): after a claim block, one more request with the block's note; if blocked again, an honest line from the call's record, in actions' `Say` templates, holding no claim phrase (the lines' existing test checks it, since the guard's negation rule is Arabic-only), a yes to it going to the talker, which calls the action's tool and reads back; after an unclear yes, a short re-ask; the yes check's model or wait (D-082's amendment) | library `agent/clause_gate.py`, `agent/turn.py`, `voice/session/yes_turns.py`, `domain/action_lines.py`; app `tickets/lines.py` | medium | the honest answer said instead of a fake fault (_Hdmiy0 t8-t9, xiM1 t3) | A and L: zero violations; blocks and unclear answers per call | one more request on blocked turns |
| 1.21 | Short unclear turns (P5's rule): a turn of four words or fewer heard below -0.65 gets "sorry, I didn't catch that" from a fixed phrase instead of an answer, never on a turn the yes rule takes or a whole stop, wait or repeat command; the talker judges the rest (1.3's line) | library: a new module beside `voice/session/talking.py`, adapted from a1c6b08's `heard_turn.py`; a fixed phrase per language | small | "shift the day any" → "Sure." no more | G | asking again on a clear turn; English barely in the fit |
| 1.22 | Reasoning: low effort on the first (decision) request, then also on the answer after a search, each an arm; and gpt-oss's reasoning sent back across a turn's tool calls, an arm of its own | library `agent/turn.py`, `adapters/groq_chat.py`, `core/settings/llm.py` | small | about 0.33 s off the first clause (D-074's measure); answers after a search that keep their reasoning | R | more skipped searches (the "gives up" feedback): read on L's checks |
| 1.23 | A sparse query beside the dense one, fused, only if run K's retrieval stays under 0.90 after 1.1 (plan 006's first named amendment) | app `knowledge_base.py` | medium | term questions (OTP) and Arabic wording found | K0, then run K's retrieval | the stored sparse vectors may need an encoder package (a download, asked then) |

**Gate:** each wave 2 change kept or dropped on its own rule; then the second tester day.

### Phase 2 · Turn-taking and the language switch (no new provider first)

Built after wave 1, beside wave 2; its rules (E2, E3, 2.4's, H) registered at its Block 0.

| # | Change | Where | Effort | Gain | Measured by | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| 2.1 | The words at every pause: when Smart Turn says "incomplete", the speech so far sent to Whisper and judged: lists for greetings, thanks, yes and no, whole commands and a question mark; `gpt-oss-20b` on Groq for the rest, mostly finished full sentences ("I think I have a problem, I cannot sign in"); a finished turn ends after about 300 ms; a turn answering a read-back keeps Smart Turn's hold and the 3 s fallback | library `voice/turn_hold.py`, `voice/stt_bridge.py`, a pure rule in `domain/` | medium | turns ended by the timeout 14% → under 2%; a first "hello" answered in about 2 s | E2 | cut real pauses; one more Whisper request a pause |
| 2.2 | Start at the detector's stop, about 225 ms before Smart Turn's verdict, kept or dropped by it; an early start for turns said over a reply (TD-117) | library `voice/turn_hold.py`, `voice/session/talking.py` | medium | about 225 ms off every turn; about 370 ms off turns said over a reply | E's cut-offs unchanged; live first audio by kind, with each n | races in the early-start logic |
| 2.3 | The hold set by the words (P4): a longer grace when the held transcript ends on a function word (0.6 s, as the branch settled), a short one after a finished question | library `voice/turn_hold.py`, `talking.py`, `core/settings/turns.py`, `domain/heard_match.py` (P4) | medium | fewer split turns; 300-400 ms off once the model is faster | E3 on the long-pause and new function-word pause items | text judged from a possibly wrong transcript |
| 2.4 | A duplicate chat request when no first token arrives by about 900 ms: no tool of either request runs until one is chosen; the loser is cancelled in its own cancel scope (D-060) and leaves nothing in the history or `Memory` | library `adapters/groq_chat.py`, `agent/turn.py` | medium | the first token's tail (p90 1,072 ms after the transcript, max 2,719) | run K's model's own time, p90 over two passes; requests per call | double requests on a slow minute |
| 2.5 | The language switch, both ways (Q20, the owner's ruling): each turn's language detected, Arabic or English only; first arm, Whisper told no language on turns of at least 1.2 s of voiced speech (from where the speech stopped), sent beside the call-language request so no time is lost; later arms, each STT candidate's own language and score (Phase 4) and a classifier held to the two languages (D-086's, its length gate counting voiced speech only); a question or request in the other language switches the call at once, short replies (yes, okay, thanks), names and product words keeping the call's language; a short list of switch requests in both scripts, including how Whisper writes them when told the other language («الإنجليزية من فضلك»), and a library `switch_language` tool for every other wording; one call-language value then moves the STT language, the reply, the voice, the fixed phrases and the knowledge query's language together, and the talker answers that turn in the new language; a switch while a read-back waits drops it unconfirmed and reads it again in the new language, a new receipt required; TD-011 paid (Whisper's names mapped to codes exactly) | library `agent/language.py`, `voice/stt_language.py`, `domain/turn_language.py`, `voice/session/call.py` (360: a split first), `domain/words.py`, the tool in `actions/` (amending D-038) | medium | a caller who asks in the other language is answered in it that turn | H on 0.6's switch items and the dev split's mixed items, each arm; a scripted call each way; no switch on the dev split's ordinary turns or short replies | an English product word or quote in an Arabic question flipping the call: the two-language score and the length gate |

**The latency budget** (a plain turn, medians, live): today about 2.1 s from the caller's last sound
to audio heard; after Phase 1 about 1.5 s; after 2.1-2.3, still Groq only, about 1.1-1.3 s; under
1.0 s needs a streaming STT and a faster first token.

### Phase 3 · The widget's redesign

Track F, once 1.14 lands, beside the rest (Q21): **an orb and three screens**
(before the call: the language, one large call button, a collapsed options panel, "headphones work
best"; during it: an orb driven by both voices' levels, a visible "I hear you" during an overlap,
subtitles, Mute, CC and a red End within thumb reach, mirrored right to left; after it: the
duration, the reason, the ticket number, the folded transcript, "call again", 1.14's feedback),
with a `level` event and a `muted` property in `t2v-client.js`; **a microphone check and device
picker**; the opt-in after-call card (`show_draft` wired, TD-143); the "caller speaking" message
proposed as a `t2v/1` change. **Measured** by the owner's review of a recorded demo, the protocol's
questions ("did you know it was listening?") and no rise in false stops; every state stays audible
too (D-075).

### Phase 4 · The provider bake-offs (once D-004 is amended, Q16)

Its own Block 0, after Q16: the Groq-only setting types loosened (`SttProvider`, `TtsProvider`,
`LlmModel`), the eval tooling made provider-aware, each provider an adapter behind its port (D-030,
GP-22). **Before any arm sends audio or text out,** each provider gets a row in SECURITY.md's trust
boundaries (its output is data, never an instruction), its adapter's `DataFlow`, a `SecretStr` key
setting with a `_FILE` form (covered by `test_every_secret_setting_is_a_secret_str_with_a_file_form`
and the logging tests), and its retention shown to the owner; then a 20-request latency smoke from
this laptop, a candidate past the bound going to the owner before its dev passes.

| Area | Arms (baseline first), with their exact settings | Why these | Expected | Owner's part |
| --- | --- | --- | --- | --- |
| STT, batch (today's port), each candidate's language detection and score read for 2.5 | B0 Whisper large-v3 + W1, twice; W2 the Arabic vocabulary (Groq, no key); Scribe v3 (keyterms: the app's `VOCABULARY` and 0.6's Arabic terms, registered before the run; Arabic with English as second language); Cohere Transcribe Arabic (no detection, so ar for Arabic and mixed items and en for English, the owner's call before the run; at the trial key's 5 requests a minute a dev pass takes about 1 hour and two replicates use about 60% of its 1,000 calls a month, a production key if you want it faster); Speechmatics' Arabic-English pack; OpenAI `gpt-transcribe`, language named, the W1 prompt | the best independent Saudi and code-switching results, and drop-ins for one request a turn | gains on terms and mixed sentences (term recall 0.333; 2 of 26 mixed variants right) and short Saudi words; little room on full Saudi sentences (0.344 is near the published floor); under about 6 items on exact match cannot be told from noise (D-024), hence CER too | keys; 0.6's recordings |
| STT, streaming (Phase 5's port) | Scribe v3 Live (multilingual, a keyterm library; raw WebSocket, not the SDKs or Pipecat), Soniox stt-rt-v6 (language hints; the agent's own text fed in to drop its echo), Speechmatics' agent endpoint | partial words, end-of-turn signals, language tags | only for the batch winner's vendor, the same items at real-time pace | Q19 |
| TTS | Orpheus (abdullah, troy); ElevenLabs Flash v2.5 (stream-input WebSocket, dictionaries in its first message) and v4 Turbo with 2-3 Saudi library voices; Inworld TTS-2 (Saudi, and Najdi if it changes anything); SILMA's Najdi model (250 characters a request on its simple WebSocket, no cap on its streaming-input one); Voho optional | one voice for both languages, pronunciation dictionaries, streaming input, Saudi voices | a gain only where listeners judge a voice Saudi; the one independent number (dialect MOS 3.70) proves nothing for ours | keys; Q14's voice; Q17's listeners |
| Talker | `gpt-oss-120b` at medium (today); `qwen/qwen3.8-27b` with no reasoning (Groq, Q18, may run during Phase 1); Gemini 3.5 or 3.7 Flash at its lowest thinking (Q16) | the Arabic answer-from-passages scores (5.98; 7.29 for Qwen's predecessor; 9.29; judged by GPT-4.1); an English 30-turn agent benchmark gives qwen3.8 96.0% on another host against gpt-oss-120b's archived 86.3% | more long scenarios passing every check; faithful Arabic answers, read by the trusted check | Q16, Q18 |

If hosting in the Kingdom becomes a rule, the open models (Cohere, Jais-ASR, Audar, Voxtral Arabic;
Fasee7-Najdi) and Speechmatics' containers are the routes, in M6.

### Phase 5 · Streaming STT and the early search

After Phase 4's STT result (Q19). The classifiers (D-086) retire if 2.5 keeps another arm.

| # | Change | Where | Effort | Gain | Measured by | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| 5.1 | A streaming STT port and bridge, partial words feeding the overlap rule and the end of turn | library `domain/ports/`, `voice/stt_bridge.py` | large | 150-300 ms a turn; overlap decisions without window requests | the streaming arm; `poe eot`, `poe overlap`, run T | the largest rewrite here; streaming accuracy below batch |
| 5.2 | A search on the heard words started as the turn ends, its passages given to the first request as data (the model may search again): an amendment of invariant 4 limited to the read-only knowledge search, no action's tool by this path, no result recorded as the model's own call | library `agent/turn.py`, `agent/tool_calls.py` | large | most knowledge turns skip a round trip | run T, L, K's retrieval | a design change, proposed first; noise in small talk |
| 5.3 | The streaming STT's own language: its segment language and score replace 2.5's detection if Phase 4 picks a code-switching or language-scoring streaming candidate and it is better on H; the switch rule unchanged | library `domain/turn_language.py`, `voice/stt_language.py`, `voice/stt_bridge.py` | small | the switch decided on partial words, before the turn ends | H | a partial word flipping the reply: the rule reads the whole turn |

### Phase 6 · Speech-to-speech, a measured trial

- **Why full speech-to-speech is not adopted:** a model that speaks directly gives the guard nothing
  to block before the caller hears it, so the claim rule, the stray-script filter (D-084), the leak
  check (D-089), the one-question limit (D-085) and our digit rules would be lost (invariant 2).
- **The trial (Q22):** gpt-realtime-2.1-mini through our own adapter behind a new port: the turn's
  audio in, text out into today's gate, guard and TTS; our turn-taking unchanged; Whisper still
  writing the heard words for the yes rule, rule B and the history. Only the final-phase text item
  is spoken, its commentary dropped as D-089 drops reasoning; unplayed and blocked items are deleted
  from the server's conversation, so its context matches what was heard (D-064); its tool calls are
  parsed and run by our runner (invariant 4); after an action's call it is muted until the outcome
  is spoken. If Phase 4 opened Google, a second arm gives the turn's audio to the Gemini Flash
  talker. A pass (S2S below) makes it worth a plan, never a default; a listening-only sample may hear
  Gemini 3.8 Live, Grok Voice 3.0 and gpt-realtime-2.1.

## The measurement, registered before any result

As [evaluation.md](../../design/evaluation.md) asks: each arm at one commit, run alone in a clean
worktree, its settings pinned in its scorecard; a candidate compared only with a baseline at the same
commit and, for latency, in the same session; every spending run prints a dry estimate and stops
before $10 (Q17). Open items are "the owner's call before the run". Judged scores are reported, never
used, until the trusted check (0.5) passes; and a change whose known risk is invented answers (1.2's
partial answers, R1, R2, T1, T2) moves no default until invented answers on run K's none items (30
dev variants; `k1-dev-spoken` had 7) are read by that check for the arm and its baseline. **Latency
noise:** each latency rule is read against the spread of a repeated baseline pass (or each arm run
twice); a median inside it counts as unchanged, and a p90 is read only on paths of 40 turns or more.
**Held-out at M9, at most eight reads:** L (at wave 1's close), P, E (at Phase 2's close), STT, T, H
and F, each once, the kept arm and its baseline; none for TTS (the panel's lines are fresh) or the trial.

- **C · The calls report's definitions.** *Abandoned:* 0 turns, ended by leaving, or a hang-up within
  10 s of the greeting's end. *A refusal:* a reply on the refusal lists (both languages), or
  `gpt-oss-20b`'s yes to a frozen question ("does this reply say the agent cannot answer or help?"),
  hand-checked on 3 calls in both languages; the same model, given the turn's words, flags off-topic
  turns, which the acceptance exempts; *no search:* no `search_knowledge` started in that turn. *An
  identical repeat:* the same normalized text as an earlier reply; *a near repeat:* the same first
  clause (of 3 words or more as written, amended 2026-11-17 before any result: a shorter one,
  such as "Sure," or «تمام،», is an opener, read by the overlap alone), or a token overlap of
  0.8 or more; both leave out asked repeats and read-backs said again.
  *A fallback turn:* one ended by the silence timeout (0.7's end reason; in the old logs,
  `end_of_turn_ms` 100-300 ms over the configured stop with no `turn_complete_ms`), reported with
  those turns' median `end_of_turn_ms` and first audio. *Baselines* (hand counts, recomputed by the
  script and printed here before any change): 2026-11-15, 10 calls, 49 timed turns, 43 replies, 13
  refusals (8 with no search, 6 outside off-topic turns), 7 identical replies (5 under the
  exclusions), 9 fallback turns, first audio p50 2,563 ms and p90 5,007 ms; the three days, 25 calls,
  168 turns, 24 fallback turns at a median of about 3.19 s, their first audio about 4.55 s.
- **L · The long-call scenarios** (run S's machinery, three plays each). Checks per turn, each a
  keyword check with registered variants in both languages: a new Ole5 question searched; no refusal
  without a search (off-topic exempt); no identical or near repeat unless asked; a ticket offered by
  the second refusal; the reply in the call's language; a follow-up 3-5 turns after its answer ("and
  the second step of the password one?") answered right, a fresh search allowed; a detail given at
  turn 1 (the error text, the affected users) still used at turn 6; after a reply cut at about 10%,
  "one more time" sharing 60% or more of its tokens with the cut reply. The facts check is secondary
  until the trusted check passes. Kept when every target check holds in all three plays of the dev
  scenarios it aims at, no registered scenario (s01-s10) fails a check it passed in two of three
  plays before, and violations are zero. **Order:** 1.1, then 1.4, then 1.2 with 1.3, then 1.5 with
  1.6, each an L pass against the last kept one, its setting or instructions `VERSION` named.

| Rule | For | Data and arms | Kept when | Expected |
| --- | --- | --- | --- | --- |
| A · Ticket calls | 1.2-1.4, 1.17-1.20, the talker arms | run A dev, every scenario, three plays | zero violations in every play; the action targets (right action, type, faithful summary, language) no worse than `a5-dev` | unchanged |
| F · Flight calls | Phase F, and from then on every row that can move a measured outcome (rows 1.x and 2.x, with Ole5's A and L as the check that it is general, D-101) | run F (the flight spec's 7.1): the flight app's scripted calls in text through `TextCall`, the real talker on the mock airline, each scenario three times against a new airline per play, today pinned to 2026-11-16, every fact checked in code (no judge); dev f01-f28, the held-out set written by a builder who has seen no dev result; a scenario's `needs` skipped and reported until its capability lands (`language_switch`: row 2.5, landed with D-103) | a scenario passes when at least 2 of its 3 plays hold every check; a change is kept when no dev scenario that passed before fails, the targeted ones pass and violations are zero in every play; for a target among L's checks (f25-f28), L's rule, all three plays; held-out read once at M9, `--split held-out` named | the first dev pass is the baseline |
| K0 · Search | 1.1 | no model: the talker's own stored queries from `k1-dev-spoken` (87 with "Ole5", each with its expected points) and the 31 live ones, with and without 1.1; the header share counts exactly the passages 1.1 skips | the share under 1 in 20, and no item loses its expected point at k = 7 unless another gains one (deterministic, so no sign test) | 81 of 217 → near 0 |
| E · End of turn | 1.11, 2.1, 2.3 | `poe eot` (GP-18): E0 3,000 ms, E1 1,800 ms; later E2 (2.1) and E3 (2.3), each against the last kept; the paused requests, 0.6's long-pause items, and its "yes, [pause] but" items as their own stratum; 0.7's resumed-silence field read first on the owner's calls | on the long-pause items, no more cut turns than the last kept arm plus D-067's noise (1 verdict), per language; zero sends on the "yes, but" items; then the tester day's live turns that resumed after 1.8 s counted | E1: timeout turns at about 2.0 s; E2: under 2% of turns |
| O · Overlap | 1.5's words, 1.12 | `poe overlap` on dev | no verdict goes from right to wrong (D-068's noise: 0 of 163) | FSMRkwf t2's kind answered |
| W · Warm-up | 1.13 | the first call after a restart, three restarts each way; its first turn's transcript and first token against later turns | first connect under 2 s; nothing else in the calls report beyond its min-max over the three logged days (evaluation.md's exception) | 24.3 s → under 2 s |
| J · Joins | 1.10 | the 40 stored replies synthesized offline: J0 today, J1 trimmed, J2 trimmed and packed | the median join falls by 0.15 s or more; a test proves the first take unchanged; the owner's listen marks no more clipped words than J0 | 0.48 → 0.2-0.3 s |
| P · Line at the search | 1.15, 1.17 | run T dev, its search items: P0 today's timer (twice, for the tolerance), P1 1.15's line, P2 1.17's | the search turns' first-sound median falls beyond P0's spread, their answer's first audio p50 stays within it, and turns past 3 s with no sound do not rise; the share of `say` lines passing reported; the owner's listen settles the wording | about 1.4 s first sound |
| G · Short unclear turns | 1.21 | P5's floor (-0.65, four words or fewer; in-sample), fresh on 0.6's items and the tester days; labels set by the owner from the recordings, blind to the score; read only with at least 20 clear and 8 garbled short turns, English apart | asks again on at most 1 in 20 clear short turns, catches at least 1 in 4 garbled ones; below the minimums, reported and nothing kept | 4 of 11 caught, 0 of 21 asked (the fit) |
| R · Reasoning | 1.22 | L, A, and the first clause as run K's model's own time in text runs, each arm twice: R0 medium; R1 low on the first request; R2 low also after a search; R3 medium with the reasoning sent back across the turn's tool calls | the first clause's p50 falls beyond R0's spread (R1, R2), or L improves at no cost beyond it (R3); new questions searched and refusals without a search no worse; R1 and R2 then wait for the invented-answer read | about 0.33 s (R1) |
| W2 · Arabic vocabulary | 1.16 | W2 against W1 on the dev split with 0.6's term items; the near-form list fitted on stored results, confirmed fresh on 0.6's items | as STT's two measures, and term recall better | term recall above 0.333 |
| STT · Bake-off | Phase 4 | D-025's rule on the dev split with 0.6's items; B0 and each candidate twice, in the same session; a focus set named before the run (`--focus`: mixed, terms, Saudi confirmations, 0.6's live failures); B0 first reproduces W1's 129 of 292 on the items it had | better beyond the noise in both replicates by the sign test by item on exact match or on per-item CER, neither worse; term recall no worse on at least 10 term items a language (Ole5, OTP, كلمة المرور, تسجيل الدخول, معلّق); small strata (mixed, MSA, each device) at most 1 item worse, Saudi and English by the sign test; stop words not worse; rule F (at least 3 of 9 empty references blanked, 0 of the speech); latency no worse than B0's plus its spread; 8 kHz and price reported | see Phase 4's table |
| TTS · Bake-off | Phase 4 | about 30 Arabic and 10 English lines from these calls and the golden set. A pre-screen to at most three candidates and Orpheus: the objective table (first audio p50 and p90 from this laptop, edge and join silence, characters a second, round-trip CER through Whisper), a 20-line smoke, the owner's ear on 5 lines each. Then the blind, shuffled panel (Q17), dialect and naturalness 1-5 per line, flags for a wrong word, a wrong pause, "not Saudi", clipped, a voice change; 3-4 hidden repeats a listener, one whose repeats differ by more than 1 point on average set aside; about an hour | the mean over listeners beats Orpheus's by 0.5 or more on both dialect and naturalness and is better on at least 21 of 30 Arabic lines (two-sided sign test, p < 0.05); no more wrong-word flags (one counts when two listeners flag the same clip); first audio p90 no worse than Orpheus's in the same session plus 100 ms; to speak English too, no worse than troy; the owner chooses among those that pass | see Phase 4's table |
| T · Talker | Phase 4 (T1 may run in Phase 1) | L, A, the model's own time in text runs, twice an arm, one run T for the kept one: T0 `gpt-oss-120b` medium, T1 `qwen/qwen3.8-27b` no reasoning, T2 Gemini Flash at its lowest thinking | zero violations in every play; more L scenarios passing every target check in 3 of 3 than T0, none failing one T0 passed; the first clause no slower beyond T0's spread; the owner's ear accepts its Saudi register; no more invented answers than T0; once the judge is trusted, right answers better or equal by the sign test; else `gpt-oss-120b` stays | see Phase 4's table |
| H · Language | 2.5, 5.3 | run H on the dev split, its mixed items and 0.6's switch items; arms H1 Whisper told no language (Groq), H2 the two-language classifier, H3 each STT candidate's own language and score; a scripted two-turn call each way | run H's keep rule (conditions 1 to 4), short replies never switching; the re-send rate reported | a switch in the turn asked; detection as replayed (37 of 37, 104 of 121) |
| S2S · Trial | Phase 6 | run K's audio arm on the 136 spoken dev variants against the cascade run again on them at the trial's commit (sign test by item, by stratum); run A as audio; run T | worth a plan when Saudi strata are better beyond the noise (read only after the trusted check passes on the audio arm's own answers) and first audio stays within the budget; any violation fails the arm; any control token, reasoning or unguarded claim ends the trial | unknown: no S2S model has Saudi evidence |

**Run budget** (wall clock from plans 006 and 007 where measured, else the agent's estimate):

| Run | When | Passes | Wall clock a pass | Cost a pass |
| --- | --- | --- | --- | --- |
| Baselines at be1a588: run S's ten, run A dev, K0, `poe eot` | first | 1 each | about 1.5 h in all | about $0.3 |
| L (run S's machinery, three plays) | wave 1 (4 steps), wave 2 (about 4) | about 9 | about 30-45 min | about $0.1-0.2 |
| A dev (three plays) | waves 1 and 2, the talker arms | about 6 | 31-36 min | $0.10-0.12 |
| F dev (three plays) | Phase F's baseline, then each row that can move an outcome | about 8 | about 25-35 min (the spec's estimate) | under $0.20 |
| K0; run K's retrieval | wave 1 | 2; 1 | minutes; about 30 min | $0; about $0.2 |
| E (`poe eot`) | wave 1, Phase 2 | about 4 | under 1 h | under $0.5 |
| J (offline synthesis of 40 replies) | wave 1 | 3 | about 15 min | under $0.2 |
| P (run T, search items) | waves 1 and 2 | 4 on dev, 1 held-out | about 1-2 h (Orpheus's pacing) | $0.4-0.7 |
| R and T (run K text runs, twice an arm); one confirming run T | wave 2, Phase 4 | about 10; 1 | about 30 min; 1-2 h | $0.21-0.23; $0.4-0.7 |
| STT (B0 and each candidate twice, a smoke each) | Phase 4 | about 12 | about 15 min (Cohere's trial about 1 h) | $0.1-0.5 |
| TTS (pre-screen and the panel's clips); the trial | Phase 4; Phase 6 | 1; about 3 | about 1 h each | under $2 a candidate; under $5 in all |

About 20-30 hours of runs in all, most unattended, outside tester days (the laptop hosts both); one
pass per run kind at a wave's commit serves C, L, R0, T0, P0 and J0 together.

## What the owner does

- **At approval, about 1 hour:** approve (Q1, Q2); answer Q3, Q4, Q16, Q17; sign up for Q16's keys.
- **Early, about 45 minutes:** the recording session (0.6, with any tester who agrees); Q6-Q12.
- **The knowledge base's source files** into `kb-source` (Q4), and a spot-check of 5 of the readers'
  verdicts, about 15 minutes.
- **About six short listens of 10-15 minutes:** Q11's spoken forms; the English voice nearest
  abdullah (1.9); the joins (J); the rotated lines (1.15); the read-back and ending lines (1.18,
  1.19); the talker arm's Saudi register (T). **One persona session**, about 30 minutes (Q14).
- **Two tester days** (Q5), about 2 hours each to run: the first after wave 1, the second after
  wave 2 and Phase 2. **The voice bake-off:** your ear on 5 lines a candidate (15 minutes); 5-10
  native Saudi listeners, an hour each (Q17). **The widget:** its recorded demo (15 minutes).

## Tracks

The obvious wins (1.7, 1.12, 1.13, 1.14, and 1.15 once Q8 is answered) land first, with their splits (`domain/interruptions.py`,
`voice/calls.py`). Then **Block 0**, one agent, merged before the tracks: the calls report's event
reader; the scenario format's new fields (the held-out flag, keyword checks with variants); the
Groq-only type changes (`qwen/qwen3.8-27b` in `LlmModel`, `reasoning_effort` "none", the
`REASONING_MODELS` test); the seam where the heard words reach the talker, the raw transcript kept
and a note added (1.16, 1.21); pure-move splits of the modules past 300 lines that Phase 1 grows
(`agent/turn.py`, `context.py`, `voice/stt_bridge.py`, `turn_book.py`, `report.py`, `speaker.py`,
`groq_tts.py`); and the ported pure modules as new files with no caller yet (`heard_match.py`,
`function_words.py`, the `tts_packing.py` rules, `connection_warmth.py`, with their tests). The
provider types wait for Phase 4's own Block 0, after Q16.
- **A · Measurement:** 0.1-0.6; owns the app's new `ole5_voice/evals/` modules, `evals/scenarios/`,
  `evals/actions/`, `evals/golden/`'s imports, the simulated caller's files in `testing/`.
- **B · Search and words (app):** the app's parts of 1.1, 1.2, 1.8, 1.9, 1.15-1.20, 1.23, 1.16's
  `VOCABULARY`; owns `knowledge_base.py`, `passages.py`, `agent.py`, `instructions/`,
  `tickets/lines.py`, the app's settings.
- **C · The talker (library):** 1.1's steps, 1.3-1.6, the library parts of 1.15, 1.17 and 1.20,
  1.22's talker part; owns `agent/prompt.py`, `context.py`, `turn.py`, `tool_calls.py`,
  `clause_gate.py`, `speech_guard.py`, `actions/knowledge.py`, `talker_progress.py`, `yes_turns.py`,
  `domain/action_lines.py`.
- **D · Speech and words:** 1.5's words, 1.7, 1.8, 1.10, 1.16's library part, 1.18's notices, 1.15's
  beat; owns `domain/text/`, `domain/words.py`, `presets.py`, `whisper_prompt.py`, `phrase_cache.py`,
  `wav_stream.py`, `groq_tts.py`, `tts_bridge.py`, `tts_packing.py`, `open_reply.py`, `echo.py`,
  `history.py`, `speaker.py`.
- **E · Session and turns:** 0.7's library part, 1.11, 1.19's session part and 1.21 (a new module
  each), 1.22's adapter part; owns `core/settings/turns.py`, `talking.py`, `groq_chat.py`,
  `stt_bridge.py`, `smart_turn.py`, `turn_book.py`, `session_events.py`, `report.py`,
  `core/call_report.py`, `voice/protocol.py`.
- **F · Widget and client:** 0.7's client part, then Phase 3; owns `apps/ole5-voice-agent/web/`,
  `t2v-client.js` and `dev-console.js`, with their tests.

Reviewers by concern: **security** (invariants 1, 2 and 4 on 1.3, 1.10, 1.12, 1.15-1.21, 2.1, 2.4,
2.5, 5.2 and Phase 6; invariant 7 on 1.14's route; invariant 5 on Phase 4's keys; invariant 8 on the
recordings), **voice** (turn-taking, speech, interruptions), and **harness** (layers, docs, the
measurements, the size rule, each port's source and cleaned docstring). Later phases get their own
Block 0.

## Notes for the builders

- **Where it lands:** `docs/plans/active/010-top-tier-voice-experience.md` on main, from be1a588
  (009, main's next free number, is the team's-agent branch's), in the same commit as Q1's `| M9 |`
  roadmap row that links it (DOC-MILESTONE, DOC-PLAN). New decisions are numbered from 099 and debt
  rows from 152 (that branch uses 091 to 098 and 151); none is cited with its prefix before it exists.
- **Citations:** DOC-REF reads every plan and code file, so main never cites that branch's plan by
  number, nor its milestone, which main's roadmap lacks: write "the team's-agent plan (branch
  `plan-009-integration`)". Ported docstrings are cleaned as "What we take" says. Code names no
  phase, block or arm (D-090); each block's last gate runs with `.mypy_cache` removed.

## Progress log

- 2026-11-15: drafted from 13 studies of the testers' calls, the code and the field, a completeness
  review and two skeptics per decision-driving claim; rewritten the same day to build on main after
  the owner's ruling; revised after three reviews (the order, the safety of each new spoken path, the
  measurement's rules); waiting for the owner's approval.
- 2026-11-16: approved by the owner, with their replies recorded under "The owner's decisions"
  and Q1, Q2, Q16 and Q20; dates removed, "What happens first" ordered by gain per hour, 2.5 made
  the switch on any question or request in the other language, 5.3 left to a streaming STT's own
  language; D-099 written and the roadmap row set in progress.
- 2026-11-16: the owner answered Q3, Q4 and Q6 to Q11; the first build (the calls report, 1.7, 1.12,
  1.13, 1.14 and the baselines, five builders at once) froze the laptop and was stopped half built,
  its work kept uncommitted in its worktrees; the owner asked for a flight-booking demo agent (Phase
  F, Q23) and put the STT model and the language switch first; the `kb-source` folder made for Q4.
- 2026-11-16: the speech-to-text providers, merged into plan-010-integration (6546633):
  core/config.py's load helpers moved to core/settings/loading.py (424060f, a pure move); Phase 4's
  Block 0 started with the key settings of the guide's six accounts (ElevenLabs, Speechmatics with
  its region, Cohere, Soniox, OpenAI with its address, Inworld), each a SecretStr with a _FILE
  form, all optional (39b1082); ElevenLabs Scribe v3 behind the speech-to-text port, keyterms from
  the call's prompt, its language and probability on the Transcript's new `heard_language` and
  `language_probability`, `stt.provider` loosened and built by the composition root (18f5dc0);
  Speechmatics' ar_en batch pack, one job a clip on eu1, deleted once read (4e69b4f); Cohere's
  Transcribe Arabic, the language always named, no prompt (efeae69); Soniox's stt-async-v6, the
  agent's two languages as strict hints, the prompt's terms as context, the language most words
  carry as `heard_language` with no score (9fd510b); `poe eval` takes each provider as an answerer,
  its model pinned on the scorecard, a dry estimate first and `--estimate-only` needing no key
  (1e96116, 6681049); run H's H3, `poe eval-languages --classifier groq|elevenlabs|soniox`, each
  turn's first 2 s sent with no language named, under `--price-per-hour` and `--cap-usd` (b44a4cd,
  16ae48e, f5fc2ff); the review's one fix: a provider's score below an even share counts as unsure
  instead of switching to a language it never heard (3d5dd4b). Each provider's SECURITY.md row
  added; nothing measured yet, no key; the full gate passed (8065 passed, 1 skipped).
- 2026-11-16: Telnyx and Nabrah merged into plan-010-integration (6f9ff53): their key settings
  and HUMAIN's (kept until its API reference is given) (e9ee5d5); Telnyx's HUMAIN engine
  (`humain/realtime`, only on Telnyx's streaming WebSocket; its batch models deepgram/nova-3 and
  whisper-large-v3-turbo on the batch endpoint) and Nabrah's Saudi model, each a turn on one
  WebSocket behind the speech-to-text port, websockets declared (D-102) (e71a54f); `poe eval`
  answerers (f19a3f8); the first Telnyx smoke heard nothing, so a turn goes at twice real time
  with code-switching and 1.5 s of silence; both smokes then passed (d977af0); D-100's condition
  (4) stated from each vendor's terms (5a0a7a0). HUMAIN's own API not built: its wire protocol
  is not public.
- 2026-11-16: the dev console's choice of speech-to-text merged (56e14b6, D-104): a call's
  provider, model and language mode chosen before its offer, from the providers whose key is
  set, each turn naming who heard it (634b222, 2717440, 74adeee); the merge gave `stt_kinds()`
  Telnyx's and Nabrah's rows.
- 2026-11-16: the language switch merged (17ebf4d, D-103): `stt.live_language = "detected"`, the
  session following the moved language, spoken switch requests, the talker's `switch_language`
  tool, a read-back read again in the new language, run H's detected arm (the splits 9849b80,
  cc47c9e, 175a72e, a961c8b, 513da5e; the build 5eeb9e5 to 21ad96c); the review's two fixes, Cohere
  no longer moving a long English turn to Arabic and a switch request said over a reply now
  moving the call (0ee08f4); the merge put Telnyx and Nabrah in `HEARS_NO_LANGUAGE`. Its full
  gate passed at 0ee08f4 (8176 passed, 1 skipped). Run H's baselines ran at 21ad96c; its arms
  wait.
- 2026-11-16: the speech-to-text bake-off on the golden set's dev split (292 variants, the
  owner's voice), at dc9c37d: Whisper large-v3 with W1 129 right (0.442, as recorded), ElevenLabs
  Scribe v3 209 (0.716; 47 items better, 7 worse, p < 0.0001; Saudi and MSA better beyond the
  noise; median 514 ms against 259), Speechmatics' ar_en pack 183 (0.627; median 1,982 ms),
  Cohere's Transcribe Arabic 165 (0.565, at 3d5dd4b; 306 characters from silence). Telnyx's
  HUMAIN engine and Nabrah run next.
- 2026-11-16: the bake-off's first pass completed and reported in
  [stt-report-2026-11-16.md](../../project/stt-report-2026-11-16.md): Nabrah's Saudi model 141
  right (0.483; Saudi 20 items better and 1 worse, English 0 better and 16 worse), HUMAIN's engine
  through Telnyx 137 (0.482, 8 failed; 29 better, 23 worse, within the noise; median 6,367 ms on
  the batch port, TD-152); the six dev runs' history lines recorded. One run each, dev only: the
  registered rule's second run and held-out read remain, and ElevenLabs' language pass.
- 2026-11-16: ElevenLabs' second dev run, `el-dev2`, 215 right (50 items better and 5 worse than
  Whisper); the owner made ElevenLabs Scribe v3 the default (D-105), Whisper the fallback; the
  keys moved into the owner's `.env` as key strings, at their request; `.env.example` gained the
  Ole5 app's own settings (scripts/settings_ref.py, tests/ole5_voice/test_env_example_app.py);
  the dev console's header lost the talker's model, the speech-to-text model and the voices, at
  the owner's request (a call's speech-to-text is now chosen per call).
- 2026-11-16: the flight agent's library steps merged (B1 to B3 of its spec; D-106, D-107): the
  access-code route and the page headers in the library's server facade (`access_code_router`,
  `AccessCodeGuard`, `TokenMinter`, `page_headers`), Ole5 switched to them; the agent's time zone
  as a fixed offset and a test call's pinned date; numbers, times, dates and amounts in the
  caller's register and key combinations as their keys, each behind a setting off by default;
  the review's one fix, `TextCall` finding a read-back said in its shaped form (eaf3308).
- 2026-11-16: the flight-booking agent's app merged, steps A1 to A7 (Phase F's F.1 and F.2): the
  skeleton registered, the mock airline (ten airports, a seeded timetable and fares, a demo
  traveler, an in-memory store), the trip each call plans, seven tools (search, choose, change,
  the trip read, the fare calendar, the cabins compared, the traveler's profile), and `book_trip`
  read back whole in words in three registers and written only on a clear yes; the review's three
  fixes, a bare return day counted from the departure, a slow search no longer timing out, and
  "the third one" matched to the order the caller heard (f2f268a). Still to build: the agent,
  persona, settings, server and page (A8, A9), the scenarios and their runner (A10 to A12), and
  the library's steps B4 to B7.
- 2026-11-16: the flight agent, its persona, settings and server (A8 of its spec; b2c45b8): the
  declaration on the public API (Saudi Arabic then English, Riyadh's fixed UTC+3 by D-106, the
  seven read tools and book_trip, a chat model on uncertain overlaps and unlisted answers); the
  persona's greetings, progress lines, instructions, the airline code's pronunciation and the
  vocabulary built from the names in FLIGHT_VOICE_* settings (Saad / سعد, T2 Air / طيران تي تو by
  default), a name breaking the lines' rule refused at load by its setting; the runtime's folder
  always nested under flight/, 50 bookings a caller a day unless set, the demo traveler the
  console's dev caller under dev; the server on 127.0.0.1:7862 with the library's access-code route
  (50 tokens a day) and page headers, GET /api/profile, and on this machine alone GET /api/bookings
  and POST /api/demo/reset (JSON only, an empty object); .env.example lists the app's settings. No
  echo: the runtime needs the Groq key whatever the agent.
- 2026-11-16: the flight agent's page (A9 of its spec; b095982): our own design on the library's
  client, the airline's mark and name, "Your trips" with a filter by reference, the traveler,
  "Start over" asked first, the language toggle (Arabic first, right to left, setting the call's
  starting language), the orb and the state line following the call, the lines the caller could say
  as text, cards newest first and at most three, the conversation and the options folded away;
  every text our own and set as text, tested in the fake browser. Proved once through the lock: the
  page, the token route's refusals (400 without the code, 415 as a form) and the dev console served
  from the owner's .env (a made-up access code in the process's environment, since .env has none
  yet); 14 fixed lines recorded at the first start, no call made. Still to build: the scenarios and
  their runner (A10 to A12).
- 2026-11-16: the flight agent's library step B4 (L6): what every app's spending runs share moved
  from the Ole5 app into the library's testing kit, through the `evals` facade (D-101): the paced,
  capped chat model (`PacedChat`, `ModelPacer`, `MinutePacer`, `Limits`, `DailyLimitError`,
  `RunClock`, `RunSleep`), the spend (`Spend`, `Price`, `ModelUse`, `ModelSpend`,
  `CapReachedError`), the checks before a run (`run_checkout`, `check_out`, `inspect_checkout`,
  `run_refused`) and a day counter over every app's run history (`requests_today`, `every_history`,
  `RunHistoryError`); Ole5's runners switched, their tests moved with the same assertions, and
  Ole5's day now counts the flight agent's history too (e56f0a5).
- 2026-11-16: the flight agent's library step B5 (L5): option rows on a card (`Card.rows`,
  `CardRow`: at most 8, title 80, detail 120, value 40, a mark of best, chosen or unavailable),
  read by the output guard with the card's texts, carried by `t2v/1`'s `card`, checked by the
  reference client and shown as text with the mark as `data-mark` on the dev page, the dev console
  and Ole5's widget; a card with no rows shows as before (30cbe05). The flight app's own cards move
  to rows with its page (A9).
- 2026-11-16: the `t2v/1` list spells a card's rows as `[CardRow]`, its one nested object, listed
  under `objects` with the bodies' (08e417f); the full gate passed on 08e417f.
- 2026-11-16: both merged into integration, the gate green on the merge (the agent and its page,
  then the library's B4 and B5); open for the lead: the presets' yes words in the public API, so an
  app's lines' rule at load reads them (today a test holds them), and Ole5's talker_args, eot and
  talker_score, already over 300 lines, a little longer from the moved imports. Still to build: the
  scenarios and their runner (A10 to A12), the library's B6 and B7, and the flight tools' cards sent
  as rows (the page already shows rows when a card has them).
- 2026-11-16: the flight agent's scripted calls (A10 of its spec; d8070d5): the scenario model read
  at the boundary (`flight_voice/evals/scenarios.py`: split, language, kind, needs from a closed
  list with each one's docstring, the airline's modes, today 2026-11-16, turns said when or the
  client's Stop at a point, and each turn's expectations: the tools and the values they held, each
  date beside the form the caller's words name, the trip read back with no total, the outcome,
  words said and never said, language and register, length and options, the repeat, cut, reference,
  card and progress flags), the rules a set keeps (`rules.py`'s `problems`: ids once, every kind in
  dev and held-out, no leg shared across the splits, needs on the list, every date the airline's
  own resolution of its form, every flight read back flying on its day with seats on a searched
  day, a return on the outbound's route back, a cut's repeat right after a stop), and the dev calls
  f01 to f28, their dates and flights drafted from the mock airline; the dev set breaks no rule but
  the twelve kinds still waiting for their held-out calls. f09 and f10 wait: a typed turn in
  `TextCall` is heard in the language the call joined in even after it moved, so a short turn in
  the new language is answered in the old one (`testing/text_parts.py`'s `hand_typed`; naming
  `session.setup.now.primary` there would let `language_switch` play in text). Still to build: the
  runner (A11) and the held-out set (A12), which covers the twelve kinds, `unavailable`, `profile`
  and `booking_outcome` among them.
- 2026-11-16: the flight library's step B6 (L8): the repeat measures of a call's replies in
  `testing/repeats.py`, through the `evals` facade (`find_repeat`, `Repeat`, `first_clause`,
  `token_overlap`, `cut_reply_share`, `repeats_cut_reply`). These are rule C's identical repeat
  (the same normalized text) and near repeat (the same first clause, or a token overlap of 0.8 or
  more, read over the longer reply's tokens as a multiset), rule L's cut repeat (0.6 of the cut
  reply's whole-text tokens), and the two exemptions (an asked repeat, a read-back said again), all
  on the scorers' normalization and the library's clause splitter. Documented in the guide's
  evaluation page and package-design.md. It moves no outcome, so there is no setting. The
  integration merge was a fast-forward to 1ef7b35, with no merge commit. Full gate passed (9135
  passed, 1 skipped) (6984f59).
- 2026-11-16: the repeat measures' review fix: a first clause makes a near repeat only when it
  holds 3 words or more as written (`MIN_CLAUSE_TOKENS`), so two replies that open with the same
  filler ("Sure,", "I'm sorry,", «تمام،», «أبشر،») and go on apart are no repeat; only their token
  overlap reads them. A shared first clause of 3 words or more still is one. Tests on Saudi, MSA
  and English openers; the guide's evaluation page and package-design.md updated. Full gate passed
  (9140 passed, 1 skipped) (bb1ab52).
- 2026-11-17: the flight runner's branch took in the library's repeat measures
  (`plan-010-flight-library`, bb1ab52) with no conflict; integration was already in it (7e930f6).
- 2026-11-17: the flight calls' seam to `TextCall` and their checks in code (A11,
  `flight_voice/evals/call.py`, `checks.py`): a play of the app's agent over a new mock airline and
  trip book, modes and today pinned, each turn said with its `when` and `stop`; each turn's checks
  and the play's, the long-call checks from the library's `find_repeat` and `repeats_cut_reply`;
  `BookingStore.made` (05f784b).
- 2026-11-17: `poe eval-flights` (A11, `run.py`, `run_setup.py`, `score.py`, `folder.py`): refuses
  the main checkout, a dirty tree, an `--out` in the worktree or in use, a broken set, an unpriced
  model, a differing resume, and an estimate past `--cap-usd` 10; smoke play, then every scenario
  once and again; records, `scorecard.json` and `.md` (2 of 3 plays, violations per play), one
  history line a session read by `requests_today` over both apps; exit 0, 1, 2; registered in
  pyproject and CLAUDE.md (8632758).
- 2026-11-17: a resumed flight run keeps a failed smoke play's violations; the chat adapter is
  built before the folder; an interrupt is recorded, exit 1 (8bd8512). Full gate passed at 8bd8512:
  9230 passed, 1 skipped.
- 2026-11-17: the flight runner's review fixes (b400b1d): a play pins the talker's prompt date to
  the scenario's today, as the airline is (`TextCall(today=)`); `--resume` goes on at a later
  commit whose changes since the run's are only the apps' `evals/history.jsonl`
  (`folder.histories_only`), the run keeping its first commit and each `Session` recording its own,
  the test's fake git now moving HEAD and dirty until the history line is committed; the repeat
  check no longer exempts the talker's own words in a turn carrying a runtime line (those lines are
  already outside the compared text). The gate ran on the integration merge (below).
- 2026-11-17: run F's held-out set, h01-h15, written by a builder who saw no dev result: fifteen,
  not about twelve, so every dev kind has its held-out scenario (`problems()` refuses a kind
  without one; the spec's twelve left booking_outcome, profile and unavailable out, now h13 a late
  write the lookup finds, h14 the profile's last London trip, h15 a city not served); "the second
  one" moved from Singapore (one flight a day) to Paris (h01), Singapore to the long Saudi call
  with a cut (h11); no dev and held-out pair shares a leg, every pick checked against the airline's
  own listing; h06 waits for `language_switch`. The whole set breaks no rule; `--split held-out`
  lists it (tested with the fake play only; no held-out call played) (cdfa72f); the full gate
  passed on cdfa72f.
- 2026-11-17: the held-out set's review fixes: h01's caller said «يوم اثنين ديسمبر», which reads as
  "the second of December" and as "a Monday in December", so its verdict would rest on the script's
  wording; it now says «يوم أربعة ديسمبر» (T2 453 on 12-04, back on T2 454 on 12-09, each still the
  second listed), and a test refuses any Arabic day said by its number that is also a weekday's
  name (c80de6c); its gate ran on the integration merge (below).
- 2026-11-17: the flight cards' options sent as rows (the library's `CardRow`): a listed flight's
  times as its title, its length, stops, flight and aircraft as its detail, its fare as its value,
  the cheapest marked best and a full one unavailable; the trip's chosen legs marked chosen, then
  the travelers and the total; the fare calendar's seven days, the three said marked best; the
  cabins compared, the trip's cabin chosen and one full or not offered unavailable; every card of
  every tool passes the output guard's ID rule in each language (0224bf9).
- 2026-11-17: the flight page shows a card's rows, each part as text with `dir="auto"`, its mark
  from the closed set as `data-mark`, styled in app.css and shown with the page's own word ("Lowest
  fare" / «أقل سعر», "Your pick" / «اختيارك», "Not available" / «غير متاح»), a mark not in the set
  dropped; the fake-browser test of a card with rows (2a2488c).
- 2026-11-17: the warm-up's first part, as the builder stopped by the freeze of 2026-11-16 left it:
  voice/spare.py (a call's detectors made one ahead) and the start's import of the offer's modules
  in a thread (TD-089), committed unfinished (48f105d).
- 2026-11-17: integration merged into the warm-up's branch; calls_start.py had come to both sides
  from the same move, the warm-up's additions kept beside integration's ChosenStt (8d18243).
- 2026-11-17: a move: calls.py's start and detectors paragraphs and the body of `start` to
  calls_start.py (`warm`), calls.py 306 → 284 lines before 1.13 grows it (633564e).
- 2026-11-17: 1.13's start part behind a new settings group, `warmup.at_start` (off by default,
  GP-18): the offer's modules imported in a thread and each call's detectors made one ahead at the
  server's start; `calls_warmed` logs the start's times; the default's characterization test. Left:
  P3's port and GroqChat.warm(), the warm requests at join (ElevenLabs by default since D-105,
  Whisper under groq, Orpheus, the chat model when cold), the reconnect after a cancel (TD-115),
  the connect's timing lines (57af78a).
- 2026-11-17: 1.13's join and cancel parts behind `warmup.at_join` and `warmup.after_cancel` (both
  off by default, GP-18): P3's `ConnectionWarmth` port taken from the team's-agent plan (branch
  `plan-009-integration`) beside a new `WarmUp` port; GroqChat's `warm()` and `warm_up()` (a free
  GET of the model list); GroqSTT's and ElevenLabsSTT's `warm_up()` (each a free GET of its model
  list); voice/join_warmth.py sends each joining call's warm requests once in the background (its
  speech-to-text's `warm_up`, its text-to-speech's `check_language`, the chat model's `warm_up`
  when not warm), logged as `call_warmed`, a failure never failing the call; GroqChat reopens its
  connection in the background after a cancelled stream (TD-115); `call_answered` and
  `call_connected` log the connect's server steps as times alone. Full gate passed on 9123292 (9123
  passed, 1 skipped, coverage 99.27%). Left: rule W (9123292).
- 2026-11-17: review fix: P3's per-request warm flag. `warm_now`
  (domain/ports/connection_warmth.py) reads the chat model's `warm()` just before each request,
  None from a model that does not say; the talker's `ModelReplied.warm_connection` carries it, its
  turn's `talker_replied` line the first request's; the call report's `TurnRecord.warm_connection`
  and the turn span's `turn.warm_connection` keep the turn's first request's; the session's own
  chat request logs it as `model_word_sent`. Fake-only tests: a cold request, a warm one, one after
  a cancel. Left: rule W; the gate ran on the integration merge (below) (254d58a).
- 2026-11-17: the flight scenarios, their runner and held-out set (plan-010-flight), the cards as
  rows (plan-010-flight-library) and the warm-up (plan-010-warm-up) merged into integration
  (6d5248a, 3e0bbae; the flight README's and package-design.md's one paragraph each kept both
  sides). f09, f10 and h06 play in text (b1749ba): a typed turn in `TextCall` is heard in the
  call's language as it stands (`setup.now`), as a real call's speech-to-text is told a move (the
  scenarios job's proposed TD, so no row), and run F plays a call that needs `language_switch`
  under `stt.live_language = "detected"` (D-103), every other call under the app's default. Rule
  C's near repeat amended before any result reads it (below). Open for the lead: the warm-up's
  ports in the public API (D-021; a team's adapter takes part by shape today),
  voice/session/report.py at 369 lines, a public `TextCall` wait for a moment (TD-155). The gate
  ran on b1749ba plus these records.
- 2026-11-17: rule C's near repeat amended by the lead before any result reads near repeats (the
  hand counts of 2026-11-15 hold identical replies only; for the owner to confirm): a first clause
  counts only when it holds 3 words or more as written, so two replies that open with the same
  filler ("Sure,", "I'm sorry,", «تمام،», «أبشر،») are read by their token overlap alone
  (`MIN_CLAUSE_TOKENS`, bb1ab52). Rule L and rows 1.3 and 1.6 read the same definition.
- 2026-11-17: run F's first session (f-dev-1, a9ee9ce) stopped at its smoke play: Groq refused
  every talker request of f01 (400 `tool_use_failed`), the model having written `search_flights`'
  date as text («الخميس الجاي») where the schema asks for a date form; the library reads it as
  `rejected`, not retried, so the turn failed. Saad could not have searched a date in a live call
  either: no test had sent a tool to the real model. Measured on run F's 28 first turns, twice
  each, the requests as the talker sends them (a scratchpad harness, about $0.05): the schema as it
  was, 37 of 56 refused and no date form right; its references inlined, none refused and 39 of the
  40 date turns' forms valid (one left out `kind`, then optional); inlined with each union's tag
  required, none refused, 40 of 40 valid and 36 right (the four others: f15 answered without
  searching, f26 said the return's month, the same date); one flat date object, none refused and
  every form valid but about 133 ms slower a turn (paired median); strict mode for tools refused by
  Groq. Fix: the library shows a tool's parameters with each reference inlined, a union as `anyOf`
  with no `discriminator`, and each constant required (`actions/tool_schema.py`, `model_schema`),
  the arguments' shape unchanged; no Ole5 tool holds a reference, union or constant, so its
  requests are as they were (a test holds it, GP-18); the flight tools' schemas are tested to hold
  none; the guide says to try a new tool once on the real model. f01's first turn, replayed on
  Groq, searched with `{kind: weekday, weekday: thu}` and listed the flights.
- 2026-11-17: run F's second session (f-dev-2) asked nothing Groq refused, and its smoke play
  stopped the run as `stuck`: f01's agent searched again and answered nothing on "the morning one"
  (the library's error notice for an empty answer), so the read-back its last turn waits for never
  came; replayed, the same turns chose the morning flight. The runner stopped on any failure,
  stricter than its rule (the flight spec's 7.3: no failed, retried or refused request and no
  violation): a smoke play stuck on the agent's own turn is now its verdict, kept, and the run goes
  on; a provider's failure, a retry or a violation still stops it. Seen for the baseline: an empty
  answer after a tool's result is told as an error, a library matter (TD-115's row).
- 2026-11-17: rule F amended by the lead before any of its results is read (f-dev-3 runs under the
  checks as they were, read for a diagnosis alone; the baseline is the first pass under these): (1)
  `register`, on a turn held Saudi, fails when the agent's own words hold a form only MSA says
  (سوف، لن، الآن، أريد، تريد، ماذا، لماذا، لدينا، لديك، ليس، هكذا، حسنا، يمكنك), and on a turn held
  MSA, when they hold a Saudi form (the library's `register_of`, the caller's list, and the agent's
  own: ودك، تبي، تبون، حقت، الصبح، رايح، لقيت، أبشر، زين); `register_of` alone read the caller's
  words and failed the Saudi forms the instructions prescribe («متى ودك ترجع؟»: the flight reviews,
  both skeptics); (2) a new turn check, `notice`, fails when the caller heard a failure notice (the
  error or cut-off line) or a clause the guard blocked: the flight spec's f13 asks it ("the
  talker's own 'nothing is booked' not blocked, no fixed error phrase"), and f-dev-2's "the morning
  one" heard the error line, which no check read. Both in code, no judge, as rule F.
- 2026-11-17: f-dev-3 stopped after 8 plays, a diagnosis alone (the checks as they were): a play
  stuck on the agent's turn took about 236 s against 45-65 s for one that went on, since
  `TextCall`'s wait for a moment summed its sleeps (about 195 s of wall time for its 120 s) and
  went on after the call had ended idle (`limits.idle_s`, 120 s). The library's wait now gives up
  at once when the call has ended and counts the system clock's own time (`testing/text_side.py`);
  run F's plays end 60 s after the caller's last turn (`run_setup.IDLE_S`), which only a play stuck
  on the agent's turn reaches (a booking's timeout and a slow search take about 20 s), so no
  verdict moves. The amended checks (`evals/spoken.py`: the register; `notice`) and the speed land
  together; the baseline is the next pass, f-dev-4.
- 2026-11-17: run F's baseline, f-dev-4 (2ee9d27, `openai/gpt-oss-120b` at medium, three plays
  each, $0.446): 9 of 28 dev scenarios pass (f02, f05, f11, f13, f16, f21, f22, f23, f24),
  violations zero in every play of 84; the failed checks most often `args` and `calls` (the tools
  called and what they held), `max_options`, `register`, `repeat` and `notice`; f20 never says the
  booking's reference. Its scorecard is in the scratchpad's runs/f-dev-4 (not the owner's var/),
  its history line committed. Next: a diagnosis of each failed scenario, each cause challenged,
  then the fixes by scenarios fixed an hour, each measured against this pass.
- 2026-11-17: rule F's scenarios amended by the lead after f-dev-4 was read and before any later
  result, each from a diagnosis a skeptic upheld (a workflow: an analyst for each failed scenario,
  a skeptic for each cause, the fixes grouped by scenarios fixed an hour): (M1) f01, f03 and f24's
  per-person variants gain «لكل شخص» and «لكل فرد», ordinary MSA (f03's MSA replies said them in
  plays 1 and 3); (M2) f01's return «الأخيرة» and f19's «الأخيرة» check the leg alone, not the pick
  kind `latest`: «الأخيرة», "the last one", is the last listed as much as the latest, the set codes
  «الأولى» as a number (f03, f06, f28), the model sent the last number in 6 of 6 plays, the same
  flight, and each turn's read-back pins it; (M3) f10's «هذي» with one flight listed checks the leg
  alone, every pick kind naming that flight; (M4) f15's Jeddah to Dubai checks no call: the
  instructions decline a route between two other cities ("Every flight starts or ends in Riyadh"),
  so a correct reply need not search, and «Riyadh» is still said; (M6) the pass rule's wording in
  whole plays ("at least 2 of its 3 plays hold every check"), as `score.py` counts and
  evaluation.md says, the stricter reading: only f26 reads otherwise on f-dev-4 (a different check
  fails in each of two plays), and it stays failed. f-dev-4 re-scored under M1-M4 from its records:
  13 of 28 (f01, f03, f10, f15 added; f19 still fails on play 3's register and play 2's stuck
  call), the baseline later passes compare to. The held-out files were not opened; whether they
  code «الأخيرة» or a lone option's pick by kind is read when held-out is, at M9.
- 2026-11-17: run F's first round of fixes (the flight app only, measured by run F's kept rule
  against f-dev-4 re-scored, 13 of 28; no setting, as D-089's tool texts; the prompt's version
  2026-11-17.2), each from a cause a skeptic upheld, built by two builders and reviewed: the
  instructions (both files) search only once the caller said the day they leave (and the return's),
  never a day they did not say, a pick named by any of its six kinds, a bare number after a listing
  a new day, change_trip for a cabin, travelers or one way once flights are listed and no search
  for that or a pick; a date said with its weekday and its month's full name; the same trip as last
  time from traveler_profile, its city, travelers and cabin kept and its past dates never offered;
  the booking's reference from traveler_profile when asked; no second booking offered after an
  unconfirmed one; in Saudi «الحين» never «الآن» and the whole retry line, to an MSA caller MSA
  forms and the tools' MSA words. The tools: a fourth option said by its part of the day, never its
  time or fare (its time still in the data, so a caller who asks hears it); a new day's listing
  said with its weekday first and without per person again; search_flights' description and
  `depart` say a day the caller said, never again after a listing for a pick or a cabin; a
  departure in days and a return in days after leaving told apart in the date forms;
  compare_cabins' pick as choose_flight's; fare_calendar's cabin the trip's when left out. Every
  new example is off the dev items (D-011: another date, another number; a test holds that no
  quoted example is a dev line). Run F's records now keep each tool call's arguments and the
  clauses the guard blocked (no verdict moves).
- 2026-11-17: run F's dev pass on round 1, f-dev-5 (ce8cbe3, three plays each, $0.473): 20 of 28
  pass against f-dev-4 re-scored, 13 (f04, f07, f08, f12, f14, f17, f18, f19 and f20 added),
  violations zero in every play of 84; `max_options` and `notice` failures 12 and 5 to none,
  `repeat` 9 to 3, `register` 8 to 5, «الآن» in a Saudi reply 5 to 1. The kept rule does not hold:
  f10 and f16, passed before, pass 1 of 3. f10's failed plays repeat the baseline's own failures (a
  search made up on the caller's first turn, as in its play 2; «(Waiting…)» stage notes said aloud,
  as in its play 3; one «الآن»), the model's variance; f16's two fail its args check on the morning
  pick sent as its listed time (`pick = "time"`, 09:30), the same flight, which the scenario codes
  as a part of the day. Across the dev set a part-of-day pick failed its args in 15 of 39 turns
  reached (11 of 39 in f-dev-4; f13, f16, f25, f28). Round 1 stays on the branch, not yet kept;
  next, round 2: the pick passed as the caller said it, the stage notes, and the scenarios still
  failing (f06, f09, f25, f26, f27, f28) diagnosed from the new records, the two rounds then
  measured together against f-dev-4 re-scored.
- 2026-11-17: rule F amended by the lead after f-dev-5 was read and before any later result: (M7) a
  check, `stage_note`, fails a turn whose heard text holds a stage note or markup (a parenthesis or
  bracket holding Latin letters in a reply in Arabic script, one that opens a stage word in any
  language, «انتظار» among them, or a "<" opening a tag), in its own code beside the guard's rule
  it measures: the agent is voice only and only spoken words score, and f-dev-5's callers heard
  «(Waiting for user response)» (f10 p2, f27 p3) and `<action tool="book_trip"/>` (f26 p2), which
  no check failed on its own. Scanned over every heard text of f-dev-4 and f-dev-5, it fails only
  the 12 spoken notes and tags and nothing else; every one is in a play that already failed, so
  f-dev-4 stays 9 of 28 and f-dev-5 20.
- 2026-11-17: run F's second round of fixes, each from a cause a skeptic upheld (a workflow: an
  analyst for each scenario still failing in f-dev-5, a skeptic for each, the fixes grouped by
  scenarios fixed an hour), built by two builders, each track reviewed by two lenses and its
  findings fixed. The flight app's texts (no setting, as round 1; the prompt's version
  2026-11-17.3): a pick passed in the kind the caller said it (a part of the day as its part, a
  comparison of when it leaves as the earliest or the latest, a number only for a number or order
  word said or the only flight listed, a time only for a time said), in both instruction files, the
  pick schema's descriptions and `_CHOICE`; the pick examples copied from dev lines replaced
  (D-011: "the cheaper one", "the morning one", «حقت الصبح», «الثانية», and "the second" near h01's
  line in 7.2), and the test that holds it now reads every string of every dev turn and the pick
  schema; the MSA twin of the departure question «متى تودّ السفر؟», MSA from the first reply to an
  MSA caller; a search in the same reply once the caller said where and when, with no question to
  confirm and the defaults never asked (round 1's wording had missed 7 first searches in 75,
  against none in f-dev-4); the first outbound listing opens with its day and weekday, a return
  listing as before; the cabins' say waits for the caller. The library, three settings off by
  default (GP-18; characterization tests hold the old behavior), which the flight app turns on
  unless set: `guard.question_stop_drops_calls` (f27's search on days nobody said, run after a
  question stop), `guard.drop_stage_notes` (the stage notes and tags as a leak of reasoning,
  D-089's stop) and `llm.max_requests_per_turn` (4 in the app, in place of turn.py's fixed 3: f26's
  refused booking then its pick and its read-back); run F's cost estimate counts the app's 4. The
  two rounds are measured together against f-dev-4 re-scored (13 of 28) by the next pass, f-dev-6.
- 2026-11-17: run F's dev pass on rounds 1 and 2, f-dev-6 (5e7689d, three plays each, $0.553): 19
  of 28 (f-dev-5 20; f10 and f26 added, f01, f04 and f24 lost). Across the 84 plays, failed `calls`
  checks 24 to 10 and `args` 31 to 16, the picks and the search at once; `said_any` 6 to 8 and
  `repeat` 3 to 7. The kept rule does not hold: f01 and f24, passed in f-dev-4 re-scored, pass 1 of
  3, their listing saying «للرايح بس» with no «للشخص» (4 of their 6 plays; the first listing's
  longer say, `_DAY`, the likely cause); f16 stays at 1 of 3, Saudi forms («الصبح», «تقدر») in
  replies to its MSA caller; and two English listings (f13 p3, f18 p3) wrote their times as digit
  words ("zero eight:zero zero"), which rule B reads as "0800" with no evidence: 2 violations. The
  rounds stay on the branch, not kept. The owner's live test of the same day (five calls, their
  notes in the next line) comes first; run F's failures are weighed against it.
- 2026-11-17: the owner's live test of the flight agent on this branch (five calls, 10:23 to 10:48
  local, read from the worktree's `var/flight/dev-console`, nothing written there), and their
  notes: "The demo is still far from spotless or flawless, so we need to work on it." Five
  read-only readers traced each note to the code. (1) The confirmation: one call heard the
  read-back six times. The model asked its own "shall I book?" after a declined read-back, though
  the `complete` say forbids it; a yes said over the summary counts for nothing by invariant 1, so
  it plays on and asks again; confirm words on no list («أكد الحجز», «خلاص، أكد») cut it as a
  correction or a stop, and each new book_trip call reads it whole again; and it runs 26 to 50
  words, 12 to 21 s. (2) No pick by price but the cheapest: «أريد أغلى واحدة» got two wrong
  either-or questions, and a fare said («اللي بـ 400») was passed as a time against line 16; a
  full flight was listed with its fare and no word that it was full, and after its `no_seats`
  the model moved the trip to business unasked. (3) The page keeps three snapshot cards, so a
  "Your pick" stays on a flight changed away from, a list never marks its pick, a cabin change
  shows no list of its new fares, and "Lowest fare" looks like a pick. (4) No date form holds a
  span: "in the next week" became a made-up Monday, then two questions; the only tool over days,
  fare_calendar, is for prices. (5) English nonsense: two degenerate gpt-oss replies (markdown
  around zero-width spaces and "[cut ...", and two questions joined by a run of dots that the
  question limit read as one clause), which no filter caught.
- 2026-11-17: rule F amended by the lead for round 3, before any result of it (the flight spec's
  7.1 and 7.2 hold the text): `args` reads a departure span of days as its `span` and a fare
  pick as its `fare_sar`; `outcome` of f22's bare «إي» over the closing question is now `done`
  (the owner's "Any yes books"), its send-word turn removed; `max_options` (3) is read against
  the brief listing (the first, last and cheapest times; a full flight said as full one more; a
  span's overview the route's daily times); `said_any` for the fare basis is held on the first
  listing's turn only; `repeat` is still held for a brief relisting of another day (f04 and f27
  may now fail it, a risk the reviewers named); four new dev calls, f29 to f32 (a week's
  overview, the dearest pick on a tie, a bare yes over the read-back's summary, a full flight
  said as full). And the `violations` play check: TextCall's yes rule accepts, under the flight
  app's `interruptions.yes_over_read_back`, a confirmation whose speech began after the summary's
  first audio when a reading of the same draft then played whole (its code fix is round 3's
  review fix F4); with the setting off it reads as before. Round 3 (6c74a36, b8a96f0) was gated
  green (9676 passed); four read-only reviewers found 14 issues, three of them races in the held
  yes (a no begun in the summary's last 200 ms, a yes said over an earlier clause of the same
  reply, transcripts landing out of order), fixed after the lean build.
- 2026-11-17: the lean Saad built beside the scripted agent (the owner's "Lean next to it",
  D-113): four tools that return plain data (find_flights for a day or a span, choose_flights,
  book_trip, traveler_profile), a 30-line prompt per language with a 21-day calendar, and one
  booking check in the app's code (the total said, played past it, a caller turn after it; a change
  to the trip resets it); `FLIGHT_VOICE_AGENT`, scripted by default. Run F's outcome mode for the
  lean agent registered before any result of it (the flight spec's section 13): kept checks
  `failure`, `violations` (rule B, the plain-speech drops, a booking claimed before the store holds
  one), `booked` (one booking exactly when the scenario books, with its flights, dates, travelers and
  cabin; none otherwise), `reference`, `language`, `register`, `stage_note`, `notice`, `max_words`
  and `repeat`; reported, not scored: the caller turns and seconds until the booking and the words
  said; a turn marked `read_back` or `closing_question` is said right after the reply that states
  the total. Two read-only reviews found 9 issues; 7 fixed, among them a turn that cut the summary
  past its total now counts as the yes, and a calendar stale past midnight is logged. Open: a bare
  yes said over the summary's closing question is settled as a go-on overlap and never answered, so
  the call goes quiet; its fix is a library setting (the owner's "Any yes books" for an agent with
  no read-back), after round 3's fixes land.
- 2026-11-17: the owner split the laptop's lock: spending practice runs take a run lock of their own,
  still one at a time; test jobs and gates keep the test lock; a timing run takes both.
- 2026-11-17: the owner ruled that the lean agent's span of days runs up to two months ("Yes, two
  months", over the 14 days first built): up to 14 days the span is given day by day, longer week
  by week (the Saudi week, each week's days with a flight and its cheapest day) with the two
  cheapest days, so the tool result stays short; its card shows only days the result holds.
- 2026-11-17: round 3's 14 review fixes and a checker's one finding merged (af72c7c, 011c9d3).
- 2026-11-17: the owner's one-request language switch built (D-115): `stt.live_language =
  "hinted"`, one Scribe request a turn naming the call's language with the agent's others as
  secondary languages, the call moved by the answer's own language at or above
  `stt.switch_min_probability`; off by default. Its keep rule registered by the lead before any
  run, read against `detected` gated as a live call sends it (D-115's text): keep `hinted` at the
  lowest threshold of 0.50 to 0.95 with no false move on a short reply, no more wrong moves than
  `detected`, right moves at least `detected`'s minus 2, and no worse WER in either item language
  beyond the run's noise; that threshold becomes the default of `stt.switch_min_probability`,
  otherwise `detected` stands. Dev only, arms (a) hinted, (b) secondary alone, (c) none, and
  `detected`.
- 2026-11-17: the owner's test of the lean Saad: "it is good"; asked for a Najdi accent (the lean
  Arabic instructions now name Riyadh's Najdi dialect with a few of its words); "do not be too
  strict on edge cases that it would restrict the agent too much and make it feels deterministic
  or robotic"; and for streaming, "the goal is to optimize the call and make it responsive not only
  TTFA (although I think mean TTFA is a very good indicator)".
- 2026-11-17: run H's Scribe arms, dev (D-115's keep rule): (a) the hint with secondary languages
  moved the call on 0 of 194 due turns at every threshold (Scribe echoes the hint), so `hinted`
  is not kept and `detected` stands; (b) secondary languages without a hint are refused by Scribe
  (both smoke requests failed); (c) no hint moved 179 of 194 at 0.8 with 20 false moves on short
  replies.
  `detected`, the reference, gated as live, moved 174 with no wrong move (p50 0.80 s, p95 1.46 s);
  D-115's amendment holds the numbers, and an exploratory reading (the no-hint answer alone on
  turns past the 1.2 s gate) that moves as `detected` does with one request a turn, p95 0.32 s
  sooner, to be built and run as its own registered arm if the owner wants it.
- 2026-11-17: D-116 built and merged: a yes said over the question that ends a reply is answered
  once the reply ends (`interruptions.answer_yes_over_question`, on for the lean agent), so the
  lean agent's "Shall I book it?" no longer meets dead air; run F's lean mode says its
  `closing_question` turns over the question, after the total. The flight app also says times and
  fares in the caller's register (`tts.spoken_numbers = "by_register"`, D-107), at the owner's
  question about "06:00" and "14:00". **A held-out exposure to record:** the fix's builder ran a
  `grep -rn` for `closing_question` over `apps/flight-voice-agent/evals/`, which printed the
  matching lines of h01, h02 and h03 to that agent (not to the lead); it reports using none of them.
  Earlier the same day, a command that would have printed h06 and h10 was refused whole. The
  three files' `closing_question` lines are to be treated as seen when the held-out set is read at
  M9, for the owner to keep or replace.
- 2026-11-17: the owner's answers. Najdi: "the lack of Nadji words made it doesn't sound Nadji,
  although the voice i have picked is capable of talking Nadji Arabic", so Saad's Saudi greeting
  and searching line are Najdi now («هلا والله ...», «أشوف لك وش فيه رحلات»), beside the lean
  instructions' Najdi. The reference: "it should only say the reference when asked", so the
  lean booking's result names it `reference_if_asked` (run F's `reference` check stands). The
  one-request language switch: "Yes please, try it. I would like a one request language change
  without hurting the transcription": `stt.live_language = "single"` is being built (D-117), its
  keep rule registered before any run: against `detected` gated as live, both at one commit, on
  dev, at the lowest threshold of 0.50 to 0.95 with no false move on a short reply, no more wrong
  moves than `detected`, right moves at least `detected`'s minus 2, and the owner's condition: in
  each item language (English, Saudi, MSA, mixed) the corpus WER no worse than `detected`'s by
  more than 0.5 points, and no item language worse on more items than better by the paired sign
  test by item at p < 0.05; that threshold becomes the flight app's, otherwise `detected` stands.
- 2026-11-17: the owner's go on the whole-call study's quick wins ("Yes, start them"): the search
  line said as the search starts (row 1.15), the warm-up on for the flight app (row 1.13), the
  end-of-turn fallback at 1.8 s (row 1.11), Smart Turn's live time logged, and row 2.2 brought
  forward; and on the streaming ones: "Do both the streaming ones. Leave the faster barge-in"
  (Scribe v3 Live behind a probe first, row 5.1; ElevenLabs' socket for v4 Turbo, design 6.1).
  The low-reasoning arm for the lean agent, registered before its run: `--effort low` against the
  `medium` run at the same commit (9067b0b, f-dev-lean-3), both run F's lean outcome mode on dev;
  low is kept for the flight app if no dev scenario that passed at medium fails at low, its
  violations are zero in every play, and its mean seconds to a booking are no more than medium's;
  otherwise medium stands (D-074).
- 2026-11-17: D-117 built and merged (`stt.live_language = "single"`, off by default); a checker
  corrected the lead's exploratory figure (at 0.8, 165 right against `detected`'s 174; at 0.50 to
  0.65, 174 with none wrong). Its arm is read by the keep rule registered above, at the merge
  commit, with its own gate pass.
- 2026-11-18: the lean agent's first practice run, f-dev-lean-3 (gpt-oss-120b at medium, 9067b0b):
  13 of 32 dev scenarios passed, 0 violations, $0.38; an earlier start (f-dev-lean-1) stopped at
  its smoke play on a retry after a made-up total was blocked. Four read-only diagnoses found the
  causes: round trips listed both days at once and one pick chose both legs (wrong bookings in f09
  and f30), the reference volunteered from book_trip's data, MSA callers given Saudi phrases, the
  fare basis's digit word joined with a fare by rule B. Fixed in the lean files (1dc60b5); a
  library word-list change was left out under GP-18. Four lean checks were found to misjudge a
  natural agent and were amended by the lead before any result of them (the flight spec's
  section 13, 2026-11-18): a tie at the fare a fare pick names books either flight, a near repeat
  counts only when the reply adds no new fact, a first clause alone under the near overlap is no
  repeat, and max_words counts the reply as written. Rescored offline, the same plays pass 18 of
  32 under the amended checks (the checks' change alone, not the agent's).
- 2026-11-18: the whole-call quick wins built, checked and merged (D-118, D-119, D-120): the search
  line said as the search starts in short rotating Najdi and English wordings, the warm-up on, the
  fallback at 1.8 s for the scripted agent (the lean agent keeps 3 s until the owner rules on its
  closing question), Smart Turn's time logged and on two threads (offline about 60 ms, so the live
  232 ms was most likely a busy laptop), the held request at the detector's stop, and the early
  start over a reply in progress. The wordings were rendered in the owner's voice for the owner to
  pick; most run 0.8 to 1.4 s of speech.
- 2026-11-18: the low-reasoning arm read by its registered rule: f-dev-lean-low-1 (gpt-oss-120b at
  low, 9067b0b) passed 11 of 32 with 17 violations, against f-dev-lean-3's 13 of 32 with none at
  medium; violations are not zero, so low is not kept and medium stands (D-074). Scribe v3 Live's
  probe smoke (10 dev clips, $0.008): commit to final p50 263 / p95 435 ms against batch's 664 /
  969 ms; English 0 % WER both ways, Arabic 13.3 % against 10.0 % (one word on one two-word MSA
  reply); the port is built only if the full dev probe, a timing run, clears the bar.
- 2026-11-18: ElevenLabs' dialogue socket for talker replies built and merged (D-121,
  `tts.stream_replies`, off by default): smoke in the owner's voice, first audio 0.16-0.19 s
  against HTTP's 0.20-0.23 s, gaps between clauses about the same. Whether a flush per clause keeps
  the flow the TTS study heard from one flush per line is for the owner's ear (the measure
  script's socket, socket-end and HTTP renders). Size debt: adapters/elevenlabs_stream.py 335
  lines, speaker.py 371, clause_cache.py 318, under the cap, to split in the next pass.
- 2026-11-18: the fresh lean practice run, f-dev-lean-4 (gpt-oss-120b at medium, 5e973f6): 24 of
  32 passed (from 13), 3 violations, all "a booking claimed before the store held one" at turn 2
  (f01, f30); a second round of diagnoses and fixes follows. Scribe v3 Live's full dev probe (292
  variants, a timing run, at 5e973f6, cents): commit to final p50 250 / p95 302 ms against batch
  568 / 812 ms; WER Arabic 9.6 % live against 13.7 % batch (Saudi 12.0 / 15.7, MSA 5.2 / 6.2, mixed
  9.7 / 18.9), English 4.8 % against 3.7 %; one live timeout in 292. It clears the bar (at least
  250 ms faster at p50, no more than 2 points worse in either language), so the streaming port is
  built, off by default, and turned on only after a live check.
- 2026-11-18: the lean agent's second round of fixes merged (e3c2688): choose_flights books
  nothing and the Saudi words for a choice replace «حجزت لك» (f-dev-lean-4's three violations),
  round-trip returns listed once the outbound is chosen or when asked, the booking check reads
  "3 080", the switch to Arabic moves the call (a library bug), and the owner's ruling of
  2026-11-18 on the reference ("saying the reference unasked is fine, it is not a hard
  requirement"): the booking gives it again, and run F's lean `reference` fails only a turn that
  asks for it and is not answered with it, an amendment registered before any result of it.
- 2026-11-18: the owner's test call on the second build (05:57) and their rulings. Najdi: the
  call was MSA throughout, because the library reads a caller as MSA unless a dialect word is on
  its list («ودي», «الجاي», «طويل العمر» are not), so Najdi by default for the flight agent and a
  guard against a false "booked" claim are being built (the model said «تم حجز رحلتك» after a
  refused book_trip). The booking check loosened by the owner ("the confirmation can be done
  before the agent saying the total, I have it on screen"): a caller turn after a reply since the
  trip was set is enough (D-113's amendment). Live, that call's mean time to first audio was
  2.54 s (8 turns; the earlier calls' 2.93 s), its search turn 2.9 s (earlier about 4.4 s).
- 2026-11-18: merged for the demo of 10:00: OpenAI's chat models (D-112, off by default; on the
  lean agent gpt-oss 13, gpt-5.4-mini 13 and gpt-6-luna 14 of 32, luna booking on a turn with no
  yes in 12 of 44 bookings), Scribe v3 Live streaming (D-122, off until a live check), and a
  clearer date-problem note with one prompt line to say why a date does not work (the owner's
  English call: a return before the departure refused with no reason given). The one-request
  language mode `single` failed its keep rule on transcription (MSA +1.37 points, 5 items worse
  and none better; Saudi +1.19), so `detected` stands. The socket's measurement in the owner's
  voice: first audio 0.19 s against HTTP's 0.23 s, gaps 0.29 against 0.31 s; renders sent for
  the owner's ear.
- 2026-11-18: Najdi by default and no false booking claim built, checked and merged (D-123,
  D-124): with `words.saudi_first` the flight agent reads a caller as Saudi unless a turn plainly
  speaks MSA, with the app's own Saudi forms («ودي», «الجاي», «طويل العمر» and others); the owner's
  call reads Saudi at every turn and every MSA dev scenario still reads MSA. book_trip declares
  its claims, so rule A blocks «تم حجز رحلتك» until it has booked, and the request is sent again
  once so the caller hears the summary and no error notice.
- 2026-11-18, before the owner's demo: the register held for the whole call, Najdi by default in
  the flight app and MSA with `T2V_WORDS__FIXED_REGISTER=msa`; the weekday a caller said held
  over the date the model worked out; a one-day span searched as that day (D-125).
- 2026-11-17: the text-to-speech candidates for the owner's pick by ear (D-114, branch
  `plan-010-tts`): `tts.provider` takes `elevenlabs`, `groq` and `telnyx`, each speaking the
  provider's default voices with `tts.languages` unset. The owner picked ElevenLabs v4 Turbo in
  the voice `nhJWWCFdNdusuVUT3x19` for Saad, and ruled it the default with Groq the fallback. A listening
  sheet of the flight agent's own lines (greeting, listing, read-back, sending, done, a mixed
  line; Saudi, MSA, English) in seven Arabic and six English voices, with latency, cost and
  Scribe's hearing of each take, is in the session notes (`tts/tts_pick.md`). ElevenLabs' key hit
  its own 10,000-credit cap during the timing, which stops Scribe too until it is raised.

## Decision log

- 2026-11-15: the plan drafted as M9 on today's main, measurement first, in two lines of work (no new
  provider; the owner's keys), taking five voice pieces from the team's-agent branch by path;
  nothing decided until the owner answers Q1 and Q2.
- 2026-11-16: the owner approved the plan as M9 (D-099) with the five ported pieces; other
  providers measured on the keys they offered, a guide to the best ones first; the call's language
  switched by any question or request in the other language, from each turn's detected language
  held to Arabic and English; no dates, the work by gain per hour, the obvious wins first.
- 2026-11-16: answers are read by two blind agent readers with the knowledge base's source files
  (Q4); the search clean-up stays in the app (Q6); a flight-booking agent becomes the demo and main
  test set, Ole5 the check that each change is general; the STT model and the switch go first; at
  most two builders at once.
- 2026-11-16: rule F registered before any run F result (the flight spec's 7.1, a dated amendment
  before its scenarios are written): run F, the flight app's scripted calls checked in code, its
  kept rule (every check in 2 of 3 plays; no dev scenario that passed fails, violations zero in
  every play; L's targets in all three), its held-out read the eighth M9 read; F.3 reads run F in
  place of "run S and run A scenarios"; `language_switch` is row 2.5's, landed with D-103.
- 2026-11-17: the lead ruled that a run F fix needing library behavior lands as a library setting
  off by default, turned on by the flight app alone (GP-18), so D-085's question limit, D-089's
  leak rule and the turn's request cap stay as approved for every other app and team; the three
  settings are the owner's to keep or turn off (`for_the_app`, one line each).
- 2026-11-17: the owner ruled on the three design questions of their live test's notes. (1) A yes
  said over the flight agent's read-back books once the summary has played to its end, a bare yes
  word («إيه», «نعم») too ("Any yes books", over the lead's recommendation to hold only an explicit
  "book it"), unless the caller says anything else before it ends; a library setting off by
  default, which the flight app turns on (GP-18), amending invariant 1 for an agent that sets it.
  (2) A day's flights are said briefly, voice only: how many, the first and last departure times,
  and the cheapest with its fare; the others when asked; the cards show every flight (amending
  D-101's "every option is said aloud" for the flight agent). (3) The page is reworked into three
  segments, in the owner's words: "First it shows the outbound flights as options (or a calendar
  of flights if asked about a range of time of flights), then the return flights, and finally the
  review for confirmation. It should handle one way flight too." Round 3 builds these with the
  fixes that need no ruling (no own booking question, confirm words, a shorter read-back with
  every value kept, picks by the dearest and by a fare said, a full flight said as full, no change
  the caller did not ask for, a span of days for search_flights, a plain-speech check with one
  retry behind a library setting).
