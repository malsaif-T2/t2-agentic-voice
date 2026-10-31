# Ole5 Voice Agent

A voice-first support assistant for Ole5 that answers from the knowledge base and opens tickets
only on a clear yes, in Saudi Arabic, MSA and English.

This is the owner's description of what is being built: the input every plan starts from. The
agent writes it with the owner (asks, drafts, revises) and changes it only with the owner's
approval. What is decided about *how* lives elsewhere: [ARCHITECTURE.md](../../ARCHITECTURE.md)
and [decisions.md](../design/decisions.md).

First drafted by the agent on 2026-10-28 from the owner's messages that day, the prototype's
logs, and the architecture proposal the agent wrote for the owner that day. What is not the
owner's carries its source in brackets, or is marked as the agent's. Awaiting the owner's
approval (plan 000).

## The problem

Ole5 is enterprise software used in Saudi Arabia. Its customers need support: how-to questions
answered from the Ole5 knowledge base, problems logged as tickets in the T2 support desk (OTRS),
and a way to reach a person.

Joori's Ole5 chatbot answers typed questions. A voice mode was built around it in October 2026,
and it failed its rehearsals on 28 Oct 2026. It misheard Saudi Arabic: about 12 of 22 Arabic
utterances were usable on a laptop microphone [source: ../voice-lab/capture/utterances.jsonl,
05:39–05:53, the agent's count]. It did not stop when told «وقف». It took 12–43 s per knowledge
answer [source: ../voice-lab/server_1028_0146.log]. It held a new request until the running
search finished, and once said a ticket was created when none was. The agent's diagnosis: the
cause was building voice around a text agent. This project builds a voice-first agent of its
own, in its own repository, without affecting Joori's work.

## Users

- **The customer (the caller)**, an Ole5 user on the website. They speak Saudi dialect, MSA or
  English, often with English product terms in Arabic sentences («الـVPN ما يشبك»), on laptop
  speakers and microphone or on a headset. They want a short spoken answer, a ticket logged
  correctly, their tickets' status, and a person when they need one. They must never be able to
  read or change another customer's tickets, get a ticket created without their own clear yes,
  hear the agent claim an action that did not happen, or reach the backend's secrets.
- **Support staff** receive tickets, handoff tickets included, in OTRS, with a summary they can
  act on without asking the customer again. They do not use this product directly.
- **The owner** hosts the backend (D-005) and can read any call's trace in Phoenix.

## Capabilities

1. **Talk in the browser:** a voice widget on the website. Start a call, speak, hear the answer,
   stop it at any time (the Stop button, Esc, or «وقف»), with live captions of the agent, and of
   the caller once each stretch of speech is transcribed.
2. **Natural turn-taking:** the agent knows when the user has finished, lets the user interrupt
   it, and ignores listening sounds («اي», «تمام») and its own voice coming back through the
   speakers.
3. **Answers from the knowledge base:** short and spoken, with the full steps on screen.
4. **Ticket creation:** the agent collects the details, reads them back, creates the ticket only
   after a clear yes, and says the number the ticket system returned.
5. **Ticket status:** the customer's tickets and their states.
6. **Handoff:** a ticket with a summary for support staff, made on request, and also when the
   agent is stuck [agent's proposal]. There is no live transfer.
7. **Languages:** Saudi Arabic, MSA and English; the agent replies in the user's language.
8. **Visibility:** every call traced in Phoenix (each turn's text, timings and tool calls), so a
   failure can be found and measured.
9. **Typed chat** in the same widget: a bonus, not required.

## Out of scope

- A live call center, or transferring the call to a person (a handoff is a ticket).
- Phone calls (SIP or PSTN) and mobile apps, for now.
- Any change to Joori's Ole5 chatbot or its repository.
- Model servers, GPUs, and hosted model providers other than Groq, for now.
- Identifying a caller by their voice [agent's proposal: a voiceprint would be biometric data].

## Constraints

From the owner on 2026-10-28, in their words ([plan 000](../plans/active/000-project-scaffold.md)
keeps the full messages):

- **Groq only, for now:** "Also for now I can only use the Groq API key, we can not try other
  models for now", and "When it comes to profiles, lets not focus on it being in Saudi as long
  as we can swap it later" (D-004). [The agent's design: each provider behind an adapter,
  D-003.]
- **Hosting:** "I can not host anything other than the website itself, the backend and some
  small services" (D-005).
- **Data:** "For Phase 0, I do not have the ability to gather data other than my own. I am the
  only one working in this repo" (D-006). [The agent reads Phase 0 as the measurement phase,
  now M1.]
- **Tracing:** "Lets use Phoenix Arize instead of LangFuse" (D-008).
- **Handoff:** "Handoff is only a ticket, there is no real call-center" (D-009).
- **The old repository:** "You can use the old (Jooris) repo to help you initiate the new one",
  in a fresh folder "to start there without affecting Joori work" (D-010).
- **No timeline:** "Lets not rely on the timeline you provided, we will rely on a plan and our
  own progress" ([WORKING-RULES.md](../../WORKING-RULES.md)).

Context, not from the owner [agent's]: the knowledge base (Qdrant at ds.t2.sa, with its
embedding gateway) and the T2 Ticket API for OTRS belong to T2. Whether T2 can change them for
this project is an open question below.

## How success is measured

[evaluation.md](../design/evaluation.md) is proposed for adoption (D-011). Everything is
measured on the owner's own recordings (D-006) and on simulated calls:

- speech-to-text accuracy on the owner's Saudi Arabic, MSA and English, by device (laptop
  speakers and microphone, wired headset, Bluetooth headset);
- turn-taking: how often the agent cuts the user off, false and missed interruptions, and the
  time from «وقف» to silence;
- the time from the end of the user's speech to the first useful audio;
- task success in simulated calls: the right answer, the right ticket, the right handoff;
- a hard constraint: no call in which the agent claims an action that did not happen.

Acceptance by example [agent's proposal]: the owner's rehearsal of 28 Oct 2026 passes, step by
step [source: ../voice-lab/server_1028_0146.log, 05:39–05:53]:

1. «نسيت كلمة المرور كيف أستعيدها؟», then «وقف» while the agent answers.
2. «أعد», then «ممكن تعيد؟».
3. «كيف أؤرشف مراسلة في النظام؟», then «أبغى موظف» while the agent answers.
4. A mumble, which the agent must ask about.
5. A correction of something the agent misheard.
6. The ticket flow, ending with an eager «نعم أرسلها».
7. One question in English.

## Open questions

- How the website proves who the customer is: its server mints the call's join token for a
  logged-in customer, or the customer confirms a one-time code sent to their email. An email
  typed in the widget proves nothing, so it never unlocks ticket status.
- How the knowledge base is reached: directly through Qdrant and the embedding gateway (the
  agent's recommendation, D-002), or through ragent2, the library the old repository uses
  (from a wheel T2 provides or T2's package index: ../Ole5-chatbot/README.md).
- What the ticket API lacks, to ask T2: a request ID stored on the ticket with a lookup by it,
  a list of a customer's tickets (the old repository keeps its own spreadsheet), and creation
  with all fields in one call (today, classification is a second call).
- Which Groq voices: the Orpheus Saudi Arabic voices (a preview model, under 200 characters per
  request [source: Groq's model page, read on 2026-10-28 by the agent's research]) and an
  English one.
- Where the backend and Phoenix run, and how WebRTC media reaches the backend from customers'
  networks (open UDP ports, a TURN service, or another transport).
- When Phase 0 ends, can recordings from other speakers be gathered?
