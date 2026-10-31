# T2 Agentic Voice

A Python library for speech-first voice agents: a live call in the browser, natural
turn-taking and interruptions, answers from your knowledge base, and actions (such as opening a
ticket) taken only after a clear spoken yes, in Saudi Arabic, MSA and English.

The library is at an early stage: its public API is designed in the repository's
`docs/design/package-design.md`, and the guide for teammates is in `docs/guide/`. Everything an
app may use is exported from the package root:

```python
from t2_agentic_voice import Settings, status

print(status(Settings()))
```
