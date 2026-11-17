# Is this for you?

A fit check before you start: what the library needs from your machine, your service, your
network and your Groq account, and what comes with it.

## Python and systems

- **CPython 3.12**, running asyncio. The package allows later versions (`requires-python` is
  `>=3.12`), but only 3.12 has been run (below).
- **Systems.** The library is built and tested on Windows 11 x64. Production is meant to run on
  Linux x86_64 (the design's 11), which no run has checked yet: the gate runs only on the
  developer's machine until the repository has a remote for CI (TD-001). macOS is not checked.
- **CPU only.** No GPU and no torch: Silero VAD and Smart Turn v3.2 run through ONNX Runtime, on
  model files that ship inside Pipecat's wheel, so nothing is downloaded at run time;
  `t2v doctor` checks each file's SHA-256. The one exception is opt-in: the ECAPA classifier of
  each turn's language runs on torch (CPU builds) through the library's `ecapa` extra, which
  the base install never brings; Silero's classifier needs no torch. Either's model files are
  fetched once by hand ([languages.md](languages.md), "Each turn's language from a
  classifier").

## The install

One install with no extras brings everything a call needs (D-018). It is heavy: measured on
2026-11-03 on Windows 11 x64 with Python 3.12.13, the library and every distribution it needs
at run time, 89 in all, take **509.1 MB** installed (each distribution's installed files, summed
from its metadata). The largest:

| Distribution | Installed |
| --- | --- |
| llvmlite (under numba) | 121.5 MB |
| opencv-python-headless (Pipecat's `webrtc` extra) | 115.9 MB |
| av, PyAV (under aiortc) | 68.6 MB |
| onnxruntime | 43.7 MB |
| numpy | 42.0 MB |
| pipecat-ai | 20.6 MB |

What to know before adding it to a project that has its own dependencies:

- **Pinned underneath.** Pipecat 1.15.0 (`pipecat-ai[webrtc]~=1.15.0`) pins `sentencex==1.0.32`
  and needs `protobuf` below 7; the workspace's lock takes protobuf 6.33.6 and numpy 2.5.4.
- **OpenCV.** Pipecat brings `opencv-python-headless`, which may clash with an `opencv-python`
  already installed (not checked).
- **loguru** is one logger for the whole process; the library switches Pipecat's lines off in it
  and touches nothing else ([tracing-and-logs.md](tracing-and-logs.md)).
- **Environment variables.** The library reads only its own `T2V_*` settings, but the packages
  under it read some variables of their own: [the guide's list](README.md#variables-to-leave-unset)
  says which to leave unset.
- **No tagged version yet:** until the first one, the library runs from this repository's
  workspace ([quickstart.md](quickstart.md)).

## One process per data folder

A call lives in one process's memory, and the store of used join tokens is a SQLite file in the
data folder (`storage.var_dir`): **one process with one worker serves one data folder**, and a
lock file refuses a second process on the same host. The lock cannot see another host, so run
one instance. A service with several workers or replicas runs the runtime as a separate process,
the sidecar; a one-worker FastAPI app may mount it ([serving.md](serving.md)). The data folder
belongs on storage that survives a restart.

## Network

- **Media goes over UDP**, from the caller's browser to your backend, with no media server
  between. On one machine, or within one network, nothing else is needed.
- **From other networks** the backend needs an open UDP path or a TURN relay, and a network that
  passes only TCP 443 needs TURN over TLS on 443. The library mints no TURN credentials yet:
  they come with the deployment, which has its own plan once a server is available.
- **HTTPS** serves the page that opens the microphone, anywhere but `localhost`.
- **Outbound,** the library contacts Groq and your trace endpoint, and nothing else.

## Groq

- **The only provider for now** (D-004): Whisper hears each turn, a chat model writes the
  talker's replies (`openai/gpt-oss-120b` by default), and Orpheus speaks. You need a key
  that can call that model, and each Orpheus model's terms accepted in Groq's console. Both
  Orpheus models are previews and take at most 200 characters a request, which the library
  keeps to.
- **The published limits are low.** Groq's rate-limits page, read on 2026-10-31 (the design's
  10.4), lists 10 requests a minute, 100 a day and 3.6K tokens a day for each Orpheus model, and
  20 requests a minute for each Whisper model. The echo sends one Whisper request a turn and up
  to three Orpheus requests an echo, and synthesizes its fixed phrases once, at its first start,
  so 100 Orpheus requests a day carry only a few calls. Read your key's real limits in the
  console; each call's report counts its requests per call minute, per model. The talker's
  one to three chat requests a turn (`llm.max_requests_per_turn`) count against the chat model's
  own limits.
- **A 429 in a call** fails that turn, and the caller hears the error notice; waiting it out,
  and turning callers away with a busy notice, are not built yet.

## Licences

Every package comes as published and is used unmodified, and the owner accepted each licence for
this project (D-018; plan 003). Pipecat and Smart Turn v3.2 are BSD-2, aiortc BSD-3 and Silero
VAD MIT. Some come with copyleft parts: soxr and the libsndfile inside `soundfile` (LGPL-2.1),
the FFmpeg inside OpenCV's wheels (LGPL-2.1), the FFmpeg inside PyAV's wheels (with x264 and
x265, GPL), num2words (LGPL) and tqdm (MPL-2.0 and MIT). Orpheus is used under Groq's terms for
each model. Phoenix, if you trace to it, is run beside your app, never installed with it: its
Elastic License 2.0 allows running it inside T2, not offering it as a service.
