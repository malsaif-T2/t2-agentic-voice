"""What a pass of `poe eval-languages` runs with (languages_run.py; plan 007's run H, its H1):
the settings, the environment's and `--env-file`'s as `poe eot` loads them, with the pass's
classifier on top (`--classifier off` under `stt.live_language = "session"`, `silero` or `ecapa`
under `classified`, its files in `--classifier-dir` or `stt.classifier_dir`, `detected` under
`detected`), refused under a rule other than the registered one (Q20, `REGISTERED`; and
`stt.detect_from_s` 1.2, `DETECT_FROM_S`, D-038's amendment); what of them a pass records (`shown`,
never the classifier's folder, a local path); the classifier the `classifiers` facade builds from
them; Ole5's codes the classifier is loaded with and the language every pass's calls are held in;
and the process's peak memory, where the platform tells it (`peak_mb`).
"""

from __future__ import annotations

import argparse
import sys
from typing import Final

from t2_agentic_voice import ConfigurationError, VoiceSettings
from t2_agentic_voice.classifiers import EcapaLanguage, SileroLanguage
from t2_agentic_voice.ports import LanguageClassifier

from ole5_voice.agent import ECHO_AGENT
from ole5_voice.evals import run_settings
from ole5_voice.evals.eot import LEAD_S, TAIL_S

# The rule's numbers run H registered (Q20), each checked before a pass.
REGISTERED: Final = {"classifier_from_s": 2.0, "classifier_min_share": 0.7, "classifier_threads": 2}
CODES: Final = tuple(dict.fromkeys(language.primary for language in ECHO_AGENT.languages))
HELD_IN: Final = ECHO_AGENT.languages[0].primary  # every pass's calls are held in it
DETECT_FROM_S: Final = 1.2  # the voiced seconds a turn needs to go naming no language too


def classifier_of(settings: VoiceSettings) -> LanguageClassifier:
    """The classifier `stt.classifier` names, built from the settings with no IO."""
    if settings.stt.classifier == "ecapa":
        return EcapaLanguage.from_settings(settings)
    return SileroLanguage.from_settings(settings)


def peak_mb() -> float | None:
    """The process's peak memory so far, in MB, where the platform tells it (the peak working
    set on Windows, the largest resident set elsewhere); None when it cannot be read."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class _Counters(ctypes.Structure):  # PROCESS_MEMORY_COUNTERS
            _fields_ = (
                ("cb", wintypes.DWORD),
                ("page_faults", wintypes.DWORD),
                *(
                    (name, ctypes.c_size_t)
                    for name in ("peak", "now", "a", "b", "c", "d", "e", "f")
                ),
            )

        counters = _Counters()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        if not ctypes.windll.psapi.GetProcessMemoryInfo(
            process, ctypes.byref(counters), counters.cb
        ):
            return None
        return float(counters.peak) / 2**20
    else:
        import resource

        peak = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)  # KB; bytes on macOS
        return peak / 2**20 if sys.platform == "darwin" else peak / 2**10


def settings_of(args: argparse.Namespace) -> VoiceSettings:
    """The settings, as `poe eot` loads them (`run_settings.env_settings`), with the pass's
    classifier on top; refused under a rule other than the registered one."""
    loaded = run_settings.env_settings(args)
    stt = loaded.stt
    if any(getattr(stt, name) != value for name, value in REGISTERED.items()):
        raise ConfigurationError(
            "Run H's passes run at the registered rule (Q20): stt.classifier_from_s 2.0, "
            "stt.classifier_min_share 0.7 and stt.classifier_threads 2. FIX: unset them, or "
            "set those values.",
            details={"setting": "stt.classifier_from_s, stt.classifier_min_share"},
        )
    if args.classifier == "detected":
        if stt.detect_from_s != DETECT_FROM_S:
            raise ConfigurationError(
                "Run H's detected pass runs at the registered stt.detect_from_s 1.2. FIX: "
                "unset it, or set that value.",
                details={"setting": "stt.detect_from_s"},
            )
        return loaded.model_copy(
            update={"stt": stt.model_copy(update={"live_language": "detected"})}
        )
    off = args.classifier == "off"
    update: dict[str, object] = {"live_language": "session" if off else "classified"}
    if not off:
        update |= {"classifier": args.classifier}
        update |= {"classifier_dir": args.classifier_dir or stt.classifier_dir}
    return loaded.model_copy(update={"stt": stt.model_copy(update=update)})


def shown(settings: VoiceSettings, args: argparse.Namespace) -> dict[str, str]:
    """What a pass's turns depend on, by dotted name: every `turns` setting, the classifier's
    (never its folder, a local path), and the run's padding."""
    turns = {
        f"turns.{name}": str(value).lower() if isinstance(value, bool) else str(value)
        for name, value in settings.turns.model_dump().items()
    }
    stt = settings.stt
    heard = {
        "stt.live_language": stt.live_language,
        "stt.classifier": stt.classifier if stt.live_language == "classified" else "none",
        "stt.detect_from_s": str(stt.detect_from_s),
        **{f"stt.{name}": str(getattr(stt, name)) for name in REGISTERED},
    }
    run = {"run.lead_s": str(LEAD_S), "run.tail_s": str(TAIL_S)}
    return {
        "env": settings.env,
        **turns,
        **heard,
        **run,
        "run.smoke_only": str(args.smoke_only).lower(),
    }
