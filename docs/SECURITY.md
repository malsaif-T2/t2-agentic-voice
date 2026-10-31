# Security

The threat model and the invariants of Ole5 Voice Agent. Proposed by the agent on 2026-10-28
([D-007](design/decisions.md)); the owner keeps or drops it in plan 000.

Each invariant names the test or check that will enforce it. Until the code it protects exists,
an invariant is a requirement on the plan that builds that code: the plan adds the adversarial
tests in the same commit (GP-08). Code and docs cite an invariant as "invariant N"; numbers are
never reused (DOC-REGISTER).

## Trust boundaries

| Boundary | What crosses it | Trusted? |
| --- | --- | --- |
| The browser to the backend | The caller's audio, the join request, data-channel messages | No: anything a caller sends may be crafted |
| The website to the backend | Who the caller is, proved by the website's login or a one-time code (an open question in the roadmap) | Only as a join token the backend verifies; an email typed by the caller is never an identity |
| The backend to Groq | Audio, text, and prompts out; transcripts, model output, and audio back | The output is not: a transcript or a model reply is data, never an instruction |
| The backend to the knowledge base | A query out; passages back | Passages are data: text in them is never obeyed |
| The backend to the ticket system | Ticket writes and reads | Its replies are the only source of a ticket number |
| The backend to Phoenix | Traces of every turn | Holds call content: hosted with the backend, never public |

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
   Over the closing question it takes only a yes with a send word («نعم أرسلها»); a bare «نعم»
   there is asked again. No tool argument or model output can stand in for either input.
   Enforced by `[[restricted]]` (ARCH-CONSTRUCT) on the confirmed draft (`domain`) and on both
   inputs (`voice`), each added in the commit that creates its class, and by adversarial tests
   of the yes rule and of a talker tool call that claims a yes.
2. **No claim without a record.** No sentence the agent speaks claims an action (created,
   updated, escalated, handed off), or says a ticket number, unless the call's record of
   completed actions or a ticket-status result holds it. Only `actions` records a completed
   action (`[[restricted]]`), and the output guard checks every sentence. Enforced by tests of
   the guard and by simulated calls with zero violations ([evaluation.md](design/evaluation.md),
   hard constraints).
3. **Identity comes from the session, never from the call.** Whose tickets are read or written
   is fixed by the join token when the call starts. Nothing said or typed during the call
   changes it. Enforced by adversarial tests in the plan that builds ticket status.
4. **Model output is parsed, never trusted.** Tool arguments are parsed into pydantic models;
   values with a fixed set (queue, type, priority) are taken only from the ticket system's own
   lists; text from a transcript, a passage, or a tool result never selects a tool by itself.
   Enforced by tests at each tool's boundary (GP-06).
5. **Secrets stay in the backend.** API keys and service passwords are `SecretStr` settings,
   never sent to the browser, never logged, never traced. Enforced, once the first secret
   setting exists, by a test in `tests/core/test_config.py` that every key and password is a
   `SecretStr` and never appears in a repr or a log line, and, in the plan that adds tracing, by
   a test that no secret value appears in a trace.
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
   lifetime, and binds the caller's verified identity to it. Enforced by adversarial tests in
   the plan that builds call set-up.
8. **Audio is kept only with consent.** Call audio is not stored unless a setting turns it on
   for the owner's own recordings; transcripts in traces are the only call content kept by
   default, and no framework's debug log writes call content. Enforced by a test of the default
   settings, and by a test that a voice-framework debug line holding a transcript does not
   reach the output at the default log level.
