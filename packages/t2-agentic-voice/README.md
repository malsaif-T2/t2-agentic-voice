# T2 Agentic Voice

A Python library for speech-first voice agents: a live call in the browser, natural
turn-taking and interruptions, answers from your knowledge base, and actions (such as opening a
ticket) taken only after a clear spoken yes, in Saudi Arabic, MSA and English.

**Status: in development; no tagged version exists yet**, so use it from its repository's uv
workspace. What works today: the browser opens a live call to your backend over WebRTC; the
library hears when the caller has finished a turn (Silero VAD and Smart Turn v3.2, on the CPU)
and sends it to Groq's Whisper; the talker answers with Groq's chat model, the agent's own tools
and its knowledge base, in short spoken clauses through Groq's Orpheus voices, with captions,
cards of steps and a Stop button; a caller can also stop it, ask it to wait or to repeat, in
words. Around it: serving (a process of its own, or mounted in a FastAPI app), signed join
tokens, the reference browser client `t2v-client.js` with a dev page, typed settings, structured
logs, OpenTelemetry traces, and a test kit that runs an agent's calls in text with a scripted
model (`TextCall`, `ScriptedLLM`). Actions taken on a spoken yes, and the deployment, come later.

An agent, as `examples/minimal/src/minimal_example/app.py` declares it: a talker with one read
tool, which needs no knowledge base.

```python
@tool(description="Today's opening hours of one branch, by the branch's name.")
async def opening_hours(
    branch: Annotated[
        str,
        Field(min_length=1, max_length=40, description="The branch's name, such as Olaya."),
    ],
) -> str:
    """The branch's hours today; the branches there are, when it names none of them."""
    hours = HOURS.get(branch.strip().casefold())
    if hours is None:
        return f"No branch has that name. The branches are {', '.join(map(str.title, HOURS))}."
    return hours


helper = VoiceAgent(
    name="minimal-helper",
    languages=[
        Language.english(greeting="Hi! Which branch's opening hours would you like to know?"),
        Language.saudi_arabic(greeting=HELPER_GREETING),
    ],
    instructions=INSTRUCTIONS,
    tools=[opening_hours],
)


def make_runtime(settings: VoiceSettings | None = None) -> VoiceRuntime:
    """The helper's runtime, with `settings`, or those the `T2V_*` variables give (nothing is
    read at import)."""
    return VoiceRuntime(
        helper, settings=settings or VoiceSettings.from_env(), identity=DevIdentity()
    )
```

Served on this machine with its dev page, from the repository's root (the same key calls the
chat model; `make_echo_runtime` serves the example's echo, which needs no chat model):

```bash
uv sync
T2V_ENV=dev T2V_GROQ__API_KEY_FILE=/path/to/groq_api_key uv run t2v dev minimal_example.app:make_runtime
# then, in Chrome or Edge on the same machine: http://127.0.0.1:7860/voice/dev
```

The `t2v` command also runs `serve APP` (a runtime in a process of its own), `doctor` (what a
first call needs: the key, each language's model and voice, the turn models' files, the
clock's skew against Groq's) and `settings show --redacted`.

Everything an app may use is exported from the package root or one of its public facades:
`t2_agentic_voice.ports`, `.groq`, `.identity`, `.server`, `.stores`, `.events`, `.languages`,
`.evals` and `.tracing`. The guide for teammates is the repository's `docs/guide/`, starting
with its `README.md` and `quickstart.md`; the design is `docs/design/package-design.md`.
