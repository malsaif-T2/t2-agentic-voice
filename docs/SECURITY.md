# Security

The threat model and the invariants of T2 Agentic Voice and the Ole5 Voice Agent built on it.
Proposed by the agent on 2026-10-28 and approved by the owner on 2026-11-01
([D-007](design/decisions.md)).

Each invariant names the test or check that will enforce it. Until the code it protects exists,
an invariant is a requirement on the plan that builds that code: the plan adds the adversarial
tests in the same commit (GP-08). Code and docs cite an invariant as "invariant N"; numbers are
never reused (DOC-REGISTER).

## Trust boundaries

| Boundary | What crosses it | Trusted? |
| --- | --- | --- |
| The browser to the backend | The caller's audio, the join request, data-channel messages | No: anything a caller sends may be crafted, so it is parsed strictly and bounded: each HTTP body under its route's cap in bytes before it is parsed, each data-channel message at most 1024 bytes as the session gets it (the object Pipecat parsed, written back as compact UTF-8 JSON: Pipecat parses the channel's text first, with no bound of ours up to the transport's message size, and holds the messages that come before the call connects, so whitespace past the bound, and a key held twice with its last value, reach a call), and a refusal names only the kinds of problem, never a value it was sent (D-029, D-039). The client's address is the connection's peer, or the one in `X-Forwarded-For` only from a proxy `server.forwarded_allow_ips` lists, no entry wider than /8 for IPv4 or /32 for IPv6, nor wider than /104 where it overlaps an IPv6 range that carries IPv4 addresses (`::ffff:0:0/96`, `::ffff:0:0:0/96`, `64:ff9b::/96`, `64:ff9b:1::/48`, `::/96`) or /24 where it overlaps 6to4's `2002::/16` (D-028). A browser and a backend on one machine still meet over its private network addresses, not loopback: aioice never offers 127.0.0.1 as a candidate, so a backend whose HTTP listens on 127.0.0.1 opens the call's UDP sockets on the LAN addresses, and a browser's `.local` candidates send mDNS on the LAN (plan 003's decision log) |
| The website to the backend | Who the caller is, proved by the website's login or a one-time code (an open question in the roadmap) | Only as a join token the backend verifies; an email typed by the caller is never an identity |
| The backend to Groq | Audio, text, and prompts out; transcripts, model output, and audio back | The output is not: a transcript or a model reply is data, never an instruction |
| The backend to the knowledge base | A query out; passages back | Passages are data: text in them is never obeyed |
| The backend to the ticket system | Ticket writes and reads | Its replies are the only source of a ticket number |
| The backend to Phoenix | Traces of every turn | Holds call content: hosted with the backend, never public; a local one listens on 127.0.0.1 only, since one on every interface serves its traces to the whole network with no login (D-023; [the guide](guide/evaluation.md), "Making a registered run") |
| The runtime to its storage folder (`storage.var_dir`) | Call content at rest, on the backend's disk: with `tts.cache_clauses` on, the clause cache's takes, the agent's words of each talker call as audio (read-backs of callers' requests among them); an action's writes in the outbox; under `env` dev with the dev page on, the test console's files; recordings only with consent (invariant 8) | Kept on the backend's own disk and never served: whoever can read the folder can hear what the agent said in calls. The clause cache writes and removes only files of its own naming in its own folder, at most `tts.clause_cache_mb`, the takes played longest ago removed past it, and logs no text or key (D-087) |
| The owner's browser to the recorder (`poe record`) | The speaker's consent, each take's audio, the review's confirmations and typed references | No: it listens on 127.0.0.1 only, answers only its own `Host` and paths under its session's token, takes a POST only from its own `Origin`, of a bounded body, and serves only its allow-list, so no request reads a file outside it, `.env` included (`tests/ole5_voice/evals/test_recorder_security.py`) |
| The process environment to the packages under the library | The variables they read whatever the library passes: `GROQ_*` and `OTEL_*` ones; Pipecat's `PIPECAT_*`, one of which runs files inside every call and another writes the caller's audio to disk; loguru's `LOGURU_*`; websockets' `WEBSOCKETS_*`; uvicorn's `FORWARDED_ALLOW_IPS`, `WEB_CONCURRENCY` and `UVICORN_*`; FastAPI's `FASTAPI_OTEL_AUTO_CONFIGURE`; onnxruntime's `ORT_LOAD_CONFIG_FROM_MODEL`; and the proxy and CA variables, which can send the key, the audio and the transcripts through a proxy or trust another certificate authority | No: the library reads only `T2V_*` names as settings and passes every value it can. Of the rest it asks only whether a variable is set, by name, never using its value: `from_env` notes `GROQ_API_KEY`, so its error can name the variable to set instead, and `voice` refuses to start calls while `PIPECAT_SETUP_FILES` or `PIPECAT_SMART_TURN_LOG_DATA` is set (`core.config.foreign_set`, D-028; built by plan 003's Track E). [The guide](guide/README.md), "Variables to leave unset", lists each of the rest and what it does, and the debt rows TD-003, TD-004, TD-005 and TD-015 say why the Groq, OpenTelemetry, proxy and CA ones are still read |

The last two rows were added by plan 004 (2026-11-02) from what M1 built and tested, as was the
Phoenix row's last clause; the owner has not reviewed them yet. Plan 003's Block 0 (2026-11-02)
widened the last row to the packages a call brings, from its reading of them, and gave the first
row its last sentence (D-035); after its review (2026-11-03), the first row gained its bounds
and the client's address, and the last its refusals by name (D-028, D-029, D-039). The owner
has not reviewed those either. Plan 007's Block I (2026-11-11) added the row for the storage
folder, after Phoenix's (D-087).

## Threats

- **A caller makes the agent act without consent:** a ticket created on a misheard yes, a yes
  spoken over the read-back, or a tool call in which the model claims the caller said yes.
- **The agent claims an action that did not happen:** the prototype's "Your ticket has been
  created" with no ticket.
- **One caller reaches another's tickets:** by typing or saying another customer's email or a
  ticket number.
- **Instructions hidden in data:** words in a transcript, a knowledge-base passage, or a tool
  result that tell the model to call a tool or reveal its prompt.
- **Cost and abuse:** endless calls, very long calls, or many ticket creates from one caller.
- **Leaks:** secrets or call content in logs, traces, error messages, or the browser.

## Invariants

1. **No ticket without a clear yes.** A ticket is created only from a confirmed draft. Only
   `domain`'s yes rule issues one, and only from two inputs no other layer can make: the
   caller's heard words, which only `voice` builds from a speech-to-text result, and a
   read-back receipt, which only `voice` builds once the read-back's summary has played in full
   without interruption. The yes rule takes heard words only if they came after the receipt.
   A yes is the caller's own heard words after the read-back: a yes on the rule's lists, or,
   for an agent that asks for it (`VoiceAgent.ask_on_unlisted_answers`, off by default), a
   chat model's judgement of those same words as agreement, within the rule's rails. The owner
   ruled so on 2026-11-10: "Lets do the model sorts the rest. But I would also want it to
   recognize different words of confirmation like ("go for it", "اكيد" etc.. While also capable
   of knowing that "Yes, but change.." is a request for change and not only confirmation)"
   (D-082). The model is asked only about words the lists cannot place, and sees only the
   read-back and those words; the rule never takes its word as it is: words with a no word, a
   question mark or a change word ("but", «بس»), the agent's own words heard back as it says
   them, and an answer to a read-back no longer current are never a yes, and a model that fails
   or is too slow is never a yes either: the caller is asked again, or, when the words hold a
   no word and are not the agent's own words heard back, the read-back is dropped as a no,
   nothing sent (the owner's "Yes, all three", 2026-11-11, after run A's `a3-dev`, where a
   cancel for another ticket was asked again and the next yes made the ticket dropped). Over
   the closing question the rule takes only
   a yes with a send word («نعم أرسلها»), or the model's explicit go-ahead to send ("go for
   it"); a bare «نعم», or the model's plain agreement ("sure"), there is asked again (the
   owner's second ruling, the same day: "Yes, send it"). A send word said alone («أرسلها», "go
   ahead") is the model's to judge too, and words that copy the agent's own line count as its
   echo only when begun while that line could still be heard: as it plays, or within its
   reply's tail after it ended, the drop rule's 0.3 s of the agent's voice leaked past echo
   cancellation, none after the caller's own stop (the owner's third ruling, the same day:
   "Yes, let the model judge"). The model's `no` (a refusal or a cancel, and since the owner's
   answer of 2026-11-11 a question or a request for something else) and its `change` only ever
   drop the read-back, nothing sent, and on the agent's own words heard back as it says them
   each is asked again, so its echo never cancels or changes a read-back either. No tool
   argument or model output can stand in for either input: the model judges the heard words,
   and builds neither.
   Enforced by `[[restricted]]` (ARCH-CONSTRUCT) on the confirmed draft (`domain`) and on both
   inputs (`voice`), each added in the commit that creates its class, by adversarial tests
   of the yes rule and of a talker tool call that claims a yes, and by adversarial tests of the
   model's rails (`tests/t2_agentic_voice/domain/test_yes_rule_judged.py`,
   `test_yes_rule_judged_no.py`, `test_yes_rule_send_alone.py`,
   `tests/t2_agentic_voice/voice/session/test_yes_ask.py`,
   `test_yes_ask_echo.py`, `test_yes_ask_tail.py`, `ActionSafetySuite`'s judged cases).
2. **No claim without a record.** No sentence the agent speaks claims an action (created,
   updated, escalated, handed off), or says a ticket number, unless the call's record of
   completed actions or a ticket-status result holds it. Only `actions` records a completed
   action (`[[restricted]]`), and the output guard checks every sentence. The guard reads the
   text that is said: what the talker writes is filtered first, each character of a script none
   of the agent's languages writes taken out and a fullwidth form or another script's digit
   rewritten as its ASCII form (`guard.remove_stray_script`, on by default; D-084), so a stray
   character cannot hide a claim phrase («تم重 إنشاء طلبك» is read as «تم إنشاء طلبك») or split
   an ID ("12重34重5" is read as 12345). A claim phrase right after an Arabic negation («ما
   فتحت لك التذكرة», I did not open the ticket for you) claims nothing, but never after a word
   that makes the negation a conjunction («بعد ما», after), with «إلا» or «غير» (only) after
   it, or in a question (D-089). Enforced by tests of the guard (the negation's adversarial
   cases in `tests/t2_agentic_voice/domain/test_claims.py`), by adversarial tests of the filter
   before it (`tests/t2_agentic_voice/agent/test_talker_scripts.py`), and by simulated calls
   with zero violations ([evaluation.md](design/evaluation.md), hard constraints).
3. **Identity comes from the session, never from the call.** Whose tickets are read or written
   is fixed by the join token when the call starts. Nothing said or typed during the call
   changes it. Enforced by adversarial tests of Ole5's tickets: another customer's ticket is never
   read, found or noted, by its number or through an outbox row
   (`tests/ole5_voice/tickets/test_status.py`, `test_mock.py`, `test_actions.py`), a call's status
   answer names only the caller's own (`tests/ole5_voice/tickets/test_ticket_calls.py`), and a
   token request naming another customer gets no token (`tests/ole5_voice/test_customer.py`).
4. **Model output is parsed, never trusted.** Tool arguments are parsed into pydantic models;
   values with a fixed set (queue, type, priority) are taken only from the ticket system's own
   lists; text from a transcript, a passage, or a tool result never selects a tool by itself.
   The arguments are parsed after the stray-script filter (D-084), which changes only their
   string values, never a key: a field named like consent is refused as before, and arguments
   that are not JSON reach the runner as written. So a fixed-set value that differs from a
   member only by a stray character (a ticket type "Bug重") parses as that member, and is read
   back as it. Enforced by tests at each tool's boundary (GP-06) and by the filter's
   adversarial tests (`tests/t2_agentic_voice/agent/test_talker_scripts.py`).
5. **Secrets stay in the backend.** API keys, service passwords, the join keys and the TURN
   secret are `SecretStr` settings, each with a `_FILE` form, never sent to the browser, never
   logged, never traced; a join key and the TURN secret hold at least 32 bytes. A call's offer
   secret and its TURN password are `SecretStr` too, and go only to the browser that joined: the
   join's answer reveals them only as it is serialized to JSON, never in a repr or a
   python-mode dump; and no refusal of a request repeats a value it sent, the join token among
   them (D-029). Enforced by `test_every_secret_setting_is_a_secret_str_with_a_file_form`,
   `test_a_secret_shorter_than_32_bytes_is_refused_as_the_settings_load` and
   `test_no_secret_appears_in_a_repr_or_a_log_line`
   (`tests/t2_agentic_voice/core/test_settings_secrets.py`);
   by `test_no_secret_reaches_a_span_or_a_log_line`
   (`tests/t2_agentic_voice/core/test_tracing.py`), whose settings carry the Groq key, a join
   key and the TURN secret, inline in one run and in their files in the other, its log lines
   read from DEBUG up; by
   `test_no_secret_shows_in_a_python_mode_dump_or_a_line_built_from_it` and
   `test_a_body_as_the_route_reads_it_is_answered_echoing_none_of_it`
   (`tests/t2_agentic_voice/api/test_protocol.py`), each test that looks for a value in an
   error, a log line or a span reading every surface it may show through `tests/leaks.py`; and
   by adversarial tests in the plan that builds call set-up, plan 003: Track F's (each
   adversarial body posted through the router answers with no value or key it sent).
6. **Writes are never cut in half.** A ticket write runs as a job outside the turn that asked
   for it. Its unique request ID goes into a durable outbox (behind a `domain` port, under
   `var/`) before the ticket system is called. A write with no reply is never repeated blindly.
   If the ticket system can find a ticket by the request ID, it is looked up before anything is
   said or retried. If it cannot, the write is not retried: the agent says the ticket could not
   be confirmed and says no number, and the outbox keeps the draft and the request ID for the
   owner to reconcile. A classification update that fails after creation is retried from the
   outbox, never by creating the ticket again. Enforced by tests with a fake ticket system that
   times out, with and without the lookup.
7. **Join tokens are single-use and short-lived.** A token starts one call, once, within its
   lifetime, and binds the caller's verified identity to it. It is a compact JWT, HS256 only,
   signed with a key of at least 32 bytes; it lives `join.ttl_s` (120 s at most) within a
   clock-skew allowance (`join.max_clock_skew_s`, 60 s at most), and the used-token store
   refuses its `jti` a second time, keeping it until the token's expiry plus the allowance's
   bound (60 s), the latest instant any allowance lets the token verify, so a restart with a
   larger allowance forgets no token it could take again; and it never records as a first use
   a `jti` whose instant has passed by its own clock. The call ID is never a credential: the offer
   and each ICE update need the call's offer secret, random and for that call alone, which
   stops working once ICE completes or the call ends, and rides in a header or the body, never
   in a URL; a second offer is refused. One process holds a
   `storage.var_dir`, through the lock file the runtime takes at start, so no second process
   shares its used-token store (D-029, D-035). Enforced for the keys' length by
   `test_a_secret_shorter_than_32_bytes_is_refused_as_the_settings_load`
   (`tests/t2_agentic_voice/core/test_settings_secrets.py`), for the lifetime's and the
   allowance's bounds by `test_a_value_out_of_its_bounds_is_refused` and
   `test_the_join_bounds_hold_the_tokens_lifetime`
   (`tests/t2_agentic_voice/core/test_settings_checks.py`), and by adversarial tests in the
   plan that builds call set-up, plan 003: Track C's (a token used twice, expired, issued in
   the future beyond the skew, signed with another key, with an unknown `kid`, with `alg` none
   or any algorithm but HS256, with a changed claim, with no `jti`, or with a lifetime over
   120 s, each refused; a token used, the store then pruned at its expiry, and the token
   presented again before its expiry plus the allowance, refused; a token used under a 30 s
   allowance, the store reopened, and the token presented at its expiry plus 45 s to a verifier
   allowed 60 s, refused; a use whose last instant has passed by the store's clock, and two
   replays either side of that instant, each refused; `SignedJoinTokens` built with
   a lifetime over 120 s or an allowance over 60 s, refused; the used-token store under two
   threads and after a restart) and Track F's (an offer with no secret, with another call's
   secret, with the secret in the query string, a second offer, and a `PATCH` after ICE
   completed and after the call ended, whether voice still holds the call or has forgotten it,
   each refused at the router; a second process on one `storage.var_dir`, refused at start).
8. **Audio is kept only with consent.** No call audio is written unless `privacy.record_audio`
   is on and the call's signed join token carries the caller's recording consent: only the
   consent `SignedJoinTokens` read from a token whose signature it verified counts (a
   `SignedConsent`), so `DevIdentity`'s never does, and no client message sets either. Audio is
   never exported to traces; what was said (what the caller was heard to say, the agent's
   replies, the arguments the model wrote for a tool and what the tool gave back, never a value
   bound from the caller as such) is the only call content traces keep, under
   `tracing.include_transcripts`,
   on by default (D-079). A spoken-language classifier (`stt.live_language = "classified"`,
   D-086) hears a turn's first seconds in memory, in the call's process, and keeps nothing:
   the audio is sent nowhere for it, and its traces hold language codes, shares and times,
   never audio.
   The agent's own synthesized voice, the phrase cache's and the clause cache's takes under
   `storage.var_dir`, is not call audio and is kept with no consent (the owner, 2026-11-10;
   D-087), though the clause cache's takes say the agent's words of a call; neither cache ever
   keeps the caller's audio or the echo's words.
   Call content is not logged at any level unless `logging.content` is on, which only `dev`
   allows, and no framework's debug log writes call content: Pipecat's loguru namespace is off
   by default, switched off before `voice` first imports Pipecat (D-031, D-035). Enforced by
   two guards on which `SignedConsent` counts. At run time, `allows_recording(consent)` in
   `core/identity.py`, which every other layer asks, is true only for the very instance that a
   validation given `CONSENT_SEAL` as its context built (the validation records it, by a weak
   reference, with its fields as they were), alive and unchanged since. Any other consent
   allows nothing: a copy of any kind (`copy`, `model_copy` by any path, `copy.copy`,
   `copy.deepcopy`, a pickle, a crafted one included), a consent rebuilt (`__init__` called
   again) or re-typed (`__class__` assigned), one whose fields were written in place, and a
   subclass's. So that the common mistakes fail loudly, the class also refuses with TypeError
   its constructor, a validation without the seal (a `TypeAdapter` of the class, and a model
   with a field of it, which the seal alone guards, included), `model_construct`, `model_copy`
   with an update, the deprecated `copy` given `update`, `include` or `exclude`, and a
   subclass. Statically, `[[restricted]]` (ARCH-CONSTRUCT) reports a call that builds a
   `SignedConsent` outside `adapters`, and any mention of `CONSENT_SEAL` outside
   `adapters/join_tokens.py` and `core/identity.py`, in the library or an app: a token that is
   the name (an import under any alias, an attribute, a read, an annotation, a keyword, a class
   pattern's keyword), a literal that holds it (a string, bytes, an f-string's part, a
   docstring), and a star import from either module. That only `SignedJoinTokens.verify` gives
   the seal, inside that module, is a review. What gets past both is deliberate, and review
   sees it: code that computes the seal's name at run time, or finds the seal without its name
   (scanning a module's namespace, `vars(module)`, or the garbage collector's referents); memory
   rewritten through `ctypes`; and writes to `core/identity.py`'s own state (its registry of
   sealed consents, or `allows_recording` replaced). With
   `test_only_a_signed_consent_is_a_verified_tokens_and_only_adapters_build_one`,
   `test_a_consent_allows_recording_only_as_the_seal_validated_it`,
   `test_a_copy_reads_as_the_consent_and_allows_nothing`,
   `test_a_sealed_consent_allows_recording_while_its_fields_are_unchanged`,
   `test_a_collected_consent_leaves_the_registry`, `test_a_signed_consent_is_built_no_other_way`,
   `test_a_signed_consent_takes_no_subclass`,
   `test_poe_arch_reports_the_seal_and_the_class_outside_the_verifier` and
   `test_only_the_verifier_and_the_module_that_makes_the_seal_mention_it`
   (`tests/t2_agentic_voice/core/test_identity.py`),
   `test_a_consent_is_a_bounded_version_and_a_real_boolean`
   (`tests/t2_agentic_voice/core/test_identity_parsing.py`), and
   `test_a_restricted_name_is_mentioned_only_by_its_layers_and_files` and
   `test_an_app_never_mentions_a_restricted_name`
   (`tests/harness/test_check_architecture.py`); by
   `test_the_turn_tts_and_limit_defaults_are_the_plans` (recording and Pipecat's lines off by
   default) and `test_each_check_holds_in_its_environments_as_the_settings_load`
   (`logging.content` refused outside `dev`), in
   `tests/t2_agentic_voice/core/test_settings_checks.py`; and by adversarial tests in plan
   003: Track C's (a verified token whose consent says `record_audio` gives a consent
   `allows_recording` accepts, and one that says false a consent it refuses); Track D's
   (nothing recorded with the setting off, with the token's consent false, with both, under
   `DevIdentity` with the setting on, or with a plain `Consent`, or a copy of a verified one,
   that says `record_audio` and the setting on, whatever a client message says; no audio in an
   exported span); and Track E's
   (voice refusing to start while `PIPECAT_SMART_TURN_LOG_DATA`, which has Smart Turn write
   each turn's audio to disk, or `PIPECAT_SETUP_FILES` is set; and, in a child process, a
   voice-framework debug line holding a transcript reaching no output at the default settings,
   and importing the library printing no banner).
