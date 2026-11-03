"""The runtime's lock file (api/lockfile.py; D-029): one process per `storage.var_dir`, a second
process refused with a FIX line that names no path, the lock gone with the process that held
it; Windows' calls run here, and POSIX's through a stand-in `fcntl` (the Linux case itself waits
for CI, TD-001)."""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pytest
from t2_agentic_voice.api.lockfile import LOCK_NAME, LockFile
from t2_agentic_voice.core.errors import ConfigurationError

from tests.isolation import child_shell

ROOT = Path(__file__).resolve().parents[3]
# A child that takes the lock on the folder it is given, says so, and holds it until its input
# closes.
_HOLDER = (
    "import sys\n"
    "from pathlib import Path\n"
    "from t2_agentic_voice.api.lockfile import LockFile\n"
    "lock = LockFile.take(Path(sys.argv[1]))\n"
    "print('held', flush=True)\n"
    "sys.stdin.read()\n"
    "lock.release()\n"
)


def test_a_folder_is_locked_once_and_released(tmp_path: Path) -> None:
    folder = tmp_path / "var"
    lock = LockFile.take(folder)
    assert [lock.held, (folder / LOCK_NAME).is_file()] == [True, True]
    with pytest.raises(ConfigurationError) as raised:
        LockFile.take(folder)
    assert "FIX:" in raised.value.message and "sidecar" in raised.value.message
    assert str(tmp_path) not in raised.value.message
    lock.release()
    lock.release()  # a second release does nothing
    assert [lock.held] == [False]
    LockFile.take(folder).release()


def test_a_second_process_on_the_folder_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "var"
    child = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(folder)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        cwd=ROOT,
        env=child_shell(),
        text=True,
    )
    try:
        assert child.stdout is not None and child.stdout.readline().strip() == "held"
        with pytest.raises(ConfigurationError, match="Another process holds"):
            LockFile.take(folder)
    finally:
        child.communicate(timeout=60)
    LockFile.take(folder).release()  # gone with the process


class _Fcntl(types.ModuleType):
    """A stand-in for POSIX's `fcntl`, holding one lock per descriptor."""

    LOCK_EX, LOCK_NB, LOCK_UN = 2, 4, 8

    def __init__(self) -> None:
        super().__init__("fcntl")
        self.held: set[int] = set()
        self.refuse = False
        self.calls: list[tuple[int, int]] = []

    def flock(self, descriptor: int, operation: int) -> None:
        self.calls.append((descriptor, operation))
        if operation & self.LOCK_UN:
            self.held.discard(descriptor)
        elif self.refuse:
            raise BlockingIOError(11, "Resource temporarily unavailable")
        else:
            self.held.add(descriptor)


def test_posix_takes_an_exclusive_flock_without_waiting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _Fcntl()
    monkeypatch.setitem(sys.modules, "fcntl", fake)
    monkeypatch.setattr(sys, "platform", "linux")
    lock = LockFile.take(tmp_path)
    assert fake.held and fake.calls[0][1] == fake.LOCK_EX | fake.LOCK_NB
    lock.release()
    assert not fake.held and fake.calls[-1][1] == fake.LOCK_UN
    fake.refuse = True
    with pytest.raises(ConfigurationError):
        LockFile.take(tmp_path)
