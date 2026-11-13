"""The runtime's lock file (the design's 4.5; D-029): one process per `storage.var_dir`, since the
used-token store there is a local SQLite file that a second process would break (invariant 7).

The runtime's lifespan takes an exclusive lock on `LOCK_NAME` under `storage.var_dir` before it
opens anything there, and releases it as it stops. A second process on the same folder, or a
second runtime of this process, is refused with a ConfigurationError whose FIX line points to
the sidecar. The lock is the operating system's, on an open file: Windows' `msvcrt.locking` on
its first byte, POSIX's `fcntl.flock`; it goes with the process, so a process that crashed
leaves the file but no lock, and the next start takes it. Each module is imported by name when
the lock is taken (`importlib`), so this module imports on every platform, and its tests run
each one's calls on any platform with a stand-in.

Under the same folder each agent keeps its own files in a folder named after it
(`agent_folder`): its phrases and clauses (api/voices.py), its used-token store (api/runtime.py)
and its outbox (api/actions.py).
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Final

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.declaration import VoiceAgent

# The lock file's name under `storage.var_dir`.
LOCK_NAME: Final = "runtime.lock"
_FIX = (
    "FIX: run one process per storage.var_dir: serve its runtime from one process (the "
    "sidecar, `t2v serve APP`, runs one worker), or give this one a folder of its own "
    "(T2V_STORAGE__VAR_DIR under the settings' prefix)."
)

log = get_logger(__name__)


def agent_folder(settings: VoiceSettings, agent: VoiceAgent) -> Path:
    """The folder `agent`'s own files are kept in under `storage.var_dir` (the module's
    docstring)."""
    return settings.storage.var_dir / agent.name


class LockFile:
    """An exclusive lock on one folder, held while the object is: `take` it, `release` it."""

    def __init__(self, path: Path, descriptor: int) -> None:
        self.path = path
        self._descriptor: int | None = descriptor

    @classmethod
    def take(cls, folder: Path) -> LockFile:
        """The lock on `folder` (made when missing), or a ConfigurationError naming the setting,
        never the folder's path, when another process or runtime holds it."""
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / LOCK_NAME
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        if not _lock(descriptor):
            os.close(descriptor)
            raise ConfigurationError(
                f"Another process holds this storage folder's lock. {_FIX}",
                details={"setting": "storage.var_dir"},
            )
        log.info("lock_taken")
        return cls(path, descriptor)

    @property
    def held(self) -> bool:
        """Whether this object still holds the lock."""
        return self._descriptor is not None

    def release(self) -> None:
        """Release the lock and close its file; the file stays. A second call does nothing."""
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is None:
            return
        try:
            _unlock(descriptor)
        finally:
            os.close(descriptor)
        log.info("lock_released")


def _lock(descriptor: int) -> bool:
    """Whether the lock on the open file `descriptor` was taken, without waiting."""
    return _windows_lock(descriptor) if sys.platform == "win32" else _posix_lock(descriptor)


def _unlock(descriptor: int) -> None:
    """Release the lock on the open file `descriptor`."""
    if sys.platform == "win32":
        _windows_unlock(descriptor)
    else:
        _posix_unlock(descriptor)


def _windows_lock(descriptor: int) -> bool:
    """Windows: lock the file's first byte, failing at once when another handle holds it."""
    msvcrt = importlib.import_module("msvcrt")
    os.lseek(descriptor, 0, os.SEEK_SET)
    try:
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    except OSError:
        return False
    return True


def _windows_unlock(descriptor: int) -> None:
    msvcrt = importlib.import_module("msvcrt")
    os.lseek(descriptor, 0, os.SEEK_SET)
    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)


def _posix_lock(descriptor: int) -> bool:
    """POSIX: an exclusive `flock`, failing at once when another open file holds it."""
    fcntl = importlib.import_module("fcntl")
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _posix_unlock(descriptor: int) -> None:
    fcntl = importlib.import_module("fcntl")
    fcntl.flock(descriptor, fcntl.LOCK_UN)
