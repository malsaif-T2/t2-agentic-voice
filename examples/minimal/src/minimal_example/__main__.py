"""Start the echo agent: `python -m minimal_example`, with `T2V_ENV=dev`, serves it on
127.0.0.1:7860 under `/voice`, its dev page at `/voice/dev` when `T2V_SERVER__DEV_PAGE=true`."""

from __future__ import annotations

from functools import partial

from t2_agentic_voice import VoiceSettings, configure_logging
from t2_agentic_voice.server import serve

from minimal_example import LOGGERS
from minimal_example.app import make_runtime


def main() -> None:
    """Load the settings, send the library's lines, the example's and uvicorn's to the output,
    and serve the echo agent until the process is stopped."""
    settings = VoiceSettings.from_env()
    logs = settings.logging
    configure_logging(logs.level, logs.format, loggers=(*LOGGERS, "uvicorn"), content=logs.content)
    serve(partial(make_runtime, settings))


if __name__ == "__main__":
    main()
