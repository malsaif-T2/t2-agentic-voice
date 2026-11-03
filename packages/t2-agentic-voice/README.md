# T2 Agentic Voice

A Python library for speech-first voice agents: a live call in the browser, natural
turn-taking and interruptions, answers from your knowledge base, and actions (such as opening a
ticket) taken only after a clear spoken yes, in Saudi Arabic, MSA and English.

**Status: M2, a call that listens and speaks.** What works today is an echo agent: the browser
opens a live call to your backend over WebRTC, the library hears when the caller has finished a
turn (Silero VAD and Smart Turn v3.2, on the CPU), sends the turn to Groq's Whisper and says the
words back through Groq's Orpheus voices, with captions and a Stop button. Around it: serving
(a process of its own, or mounted in a FastAPI app), signed join tokens, the reference browser
client `t2v-client.js` with a dev page, typed settings, structured logs and OpenTelemetry
traces. The talker that answers, tools, actions on a spoken yes, interruptions beyond Stop and
the deployment come in later milestones. No tagged version exists yet: use it from its
repository's uv workspace.

An agent, as `examples/minimal/src/minimal_example/app.py` declares it:

```python
agent = VoiceAgent(
    name="minimal-echo",
    languages=[
        Language.english(greeting="Hi! Say something, and I will say it back."),
        Language.saudi_arabic(greeting=SAUDI_GREETING),
    ],
)


def make_runtime(settings: VoiceSettings | None = None) -> VoiceRuntime:
    """The echo agent's runtime, with `settings`, or those the `T2V_*` variables give (nothing
    is read at import)."""
    return VoiceRuntime(
        agent, settings=settings or VoiceSettings.from_env(), identity=DevIdentity()
    )
```

Served on this machine with its dev page, from the repository's root:

```bash
uv sync
T2V_ENV=dev T2V_GROQ__API_KEY_FILE=/path/to/groq_api_key uv run t2v dev minimal_example.app:make_runtime
# then, in Chrome or Edge on the same machine: http://127.0.0.1:7860/voice/dev
```

The `t2v` command also runs `serve APP` (a runtime in a process of its own), `doctor` (what a
first call needs: the key, each language's model and voice, the turn models' files) and
`settings show --redacted`.

Everything an app may use is exported from the package root or one of its public facades:
`t2_agentic_voice.ports`, `.groq`, `.identity`, `.server`, `.stores`, `.events`, `.languages`,
`.evals` and `.tracing`. The guide for teammates is the repository's `docs/guide/`, starting
with its `README.md` and `quickstart.md`; the design is `docs/design/package-design.md`.
