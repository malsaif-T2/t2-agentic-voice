# T2 Agentic Voice

A Python library that T2's teams install to give their products a speech-first voice agent: a
live call in the browser, natural turn-taking and interruptions, answers from the product's own
knowledge, and actions taken only after a clear spoken yes, in Saudi Arabic, MSA and English.
Its first app, built on it in the same repository, is the **Ole5 Voice Agent**, a voice support
assistant for Ole5.

This is the owner's description of what is being built: the input every plan starts from. The
agent writes it with the owner (asks, drafts, revises) and changes it only with the owner's
approval. What is decided about *how* lives elsewhere: [ARCHITECTURE.md](../../ARCHITECTURE.md),
[decisions.md](../design/decisions.md), and the package design
([package-design.md](../design/package-design.md), proposed).

First drafted by the agent on 2026-10-28 for the Ole5 Voice Agent alone; widened on 2026-10-31,
when the owner made the project a shared library (D-013). What is not the owner's carries its
source in brackets, or is marked as the agent's. Awaiting the owner's approval (plan 000).

## The problem

Teams at T2 want voice in their products, and a good voice agent is hard to build: it must know
when the user has finished, stop the moment it is interrupted, hear Saudi Arabic with English
product terms in it, answer fast enough for speech, and never act or claim to act without the
user's clear yes. Each team building that alone would repeat the same work and the same
mistakes.

Ole5 showed it first. A voice mode built in October 2026 around the Ole5 chatbot, a text agent,
did not hold up in its rehearsals on 28 Oct 2026. About 12 of 22 Arabic utterances were usable
on a laptop microphone [source: ../voice-lab/capture/utterances.jsonl, 05:39–05:53, the agent's
count]. It did not stop when told «وقف». It took 12–43 s per knowledge answer [source:
../voice-lab/server_1028_0146.log], and held a new request until the running search finished.
The agent's diagnosis: voice was added around an agent designed for typing. The owner presented
three approaches to their manager, and a dedicated, speech-first voice agent was chosen (D-012).
This repository builds it once, as a library, so Ole5 and other products share it.

## Users

- **Teammate developers** at T2: Python developers who add voice to their own product (an IT
  helpdesk, a request service, a support desk) with their own tools, knowledge and prompts, in
  their own project (D-014). They need to know what the library gives them and what they must
  bring, to reach a first working call from the guide alone, to change its behaviour through
  settings and extension points rather than its code, and to upgrade it without surprises.
- **The people who run a teammate's agent**: they host it within the limits of their own team,
  set its keys and settings, watch its traces, and check its quality on their users' speech
  before it goes live.

For the Ole5 Voice Agent:

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

The library, for every app built on it:

1. **A live call in the browser**, over WebRTC, that the app serves from its own backend.
2. **Natural turn-taking:** the agent knows when the user has finished, lets the user interrupt
   it and stop it at once, and ignores listening sounds («اي», «تمام») and its own voice coming
   back through the speakers.
3. **A fast talker** that speaks, asks and calls the app's tools; it never acts by itself.
4. **Confirmed actions:** an action the app declares as needing a yes is read back and run only
   after a clear yes; no sentence claims an action the backend did not complete.
5. **Languages:** Saudi Arabic, MSA and English; the agent replies in the user's language.
6. **Swappable providers:** speech-to-text, the model and text-to-speech each behind a port,
   chosen by a setting (Groq today, D-004).
7. **Settings and extension points** for what differs between products: the prompt, the tools,
   the actions, the vocabulary, the voices, the providers.
8. **Visibility:** every call traced in Phoenix (each turn's text, timings and tool calls).
9. **A testing kit:** fakes for every provider, and scripted and simulated callers, so an app's
   behaviour is tested without a microphone or a key.
10. **Documentation:** a guide that takes a teammate from installing the library to running
    their agent, and a reference of every setting.
11. **An optional thinker** that the talker can hand a complex task to, off by default (D-015).

The Ole5 Voice Agent, on top of it:

1. **Talk in the browser:** a voice widget on the website. Start a call, speak, hear the answer,
   stop it at any time (the Stop button, Esc, or «وقف»), with live captions of the agent, and of
   the caller once each stretch of speech is transcribed.
2. **Answers from the Ole5 knowledge base:** short and spoken, with the full steps on screen.
3. **Ticket creation:** the agent collects the details, reads them back, creates the ticket only
   after a clear yes, and says the number the ticket system returned.
4. **Ticket status:** the customer's tickets and their states.
5. **Handoff:** a ticket with a summary for support staff, made on request, and also offered
   when the agent is stuck [agent's proposal]. Like any ticket, it is read back and made only
   after a clear yes (D-018). There is no live transfer.
6. **Typed chat** in the same widget: a bonus, not required.

## Out of scope

- For the first version of the library: a drop-in widget for teammates' pages, a server
  configured without Python, and plugging in a teammate's agent over HTTP (D-014, later
  options).
- A live call center, or transferring the call to a person (a handoff is a ticket).
- Phone calls (SIP or PSTN) and mobile apps, for now.
- Any change to Joori's Ole5 chatbot or its repository.
- Model servers, GPUs, and hosted model providers other than Groq, for now.
- Identifying a caller by their voice [agent's proposal: a voiceprint would be biometric data].

## Constraints

From the owner, in their words ([plan 000](../plans/active/000-project-scaffold.md) and
[plan 001](../plans/active/001-library-and-app.md) keep the full messages):

- **Approach 3:** "I presented the presentation and we are doing Approach 3 now" (2026-10-31,
  D-012).
- **A library for teammates, and Ole5 still required:** "This requires our work to be highly
  modular, with settings they can change to fit them and documentation to show them how to use
  it. All of this while we make our "Ole5-voice-agent" because it is still required"
  (2026-10-31, D-013). And: "we need to determine what we provide for teammate developers and
  what we require for them, I mean we need to do the whole design of the package early"
  (2026-10-31, D-017).
- **Open source:** "we could use open-source code and projects to help us accomplish ours"
  (2026-10-31, D-016).
- **Groq only, for now:** "Also for now I can only use the Groq API key, we can not try other
  models for now", and "When it comes to profiles, lets not focus on it being in Saudi as long
  as we can swap it later" (2026-10-28, D-004).
- **Hosting:** "I can not host anything other than the website itself, the backend and some
  small services" (2026-10-28, D-005).
- **Data:** "For Phase 0, I do not have the ability to gather data other than my own. I am the
  only one working in this repo" (2026-10-28, D-006). [The agent reads Phase 0 as the
  measurement phase, now M1.]
- **Tracing:** "Lets use Phoenix Arize instead of LangFuse" (2026-10-28, D-008).
- **Handoff:** "Handoff is only a ticket, there is no real call-center" (2026-10-28, D-009).
- **The old repository:** "You can use the old (Jooris) repo to help you initiate the new one",
  in a fresh folder "to start there without affecting Joori work" (2026-10-28, D-010).
- **No timeline:** "Lets not rely on the timeline you provided, we will rely on a plan and our
  own progress" (2026-10-28, [WORKING-RULES.md](../../WORKING-RULES.md)).

Context, not from the owner [agent's]: the knowledge base (Qdrant at ds.t2.sa, with its
embedding gateway) and the T2 Ticket API for OTRS belong to T2. Whether T2 can change them for
this project is an open question below.

## How success is measured

[evaluation.md](../design/evaluation.md) is proposed for adoption (D-011). For the Ole5 Voice
Agent, everything is measured on the owner's own recordings (D-006) and on simulated calls:

- speech-to-text accuracy on the owner's Saudi Arabic, MSA and English, by device (laptop
  speakers and microphone, wired headset, Bluetooth headset);
- turn-taking: how often the agent cuts the user off, false and missed interruptions, and the
  time from «وقف» to silence;
- the time from the end of the user's speech to the first useful audio;
- task success in simulated calls: the right answer, the right ticket, the right handoff;
- a hard constraint: no call in which the agent claims an action that did not happen.

For the library [agent's proposal]: the Ole5 app and the minimal example use only its public
API (ARCH-PUBLIC, checked on every change); a teammate reaches a first working call by
following the guide alone; and an upgrade within a major version needs no change to an app.

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

The library's own open questions (how teammates install it, which first teammate use case
to aim at, and others) are in the package design's last section. For the Ole5 Voice Agent:

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
