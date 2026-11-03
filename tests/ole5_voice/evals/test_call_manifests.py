"""The recorded calls' manifests (call_manifests.py): each call's consent and each file's hash and
length (a WAV's rate, channels and seconds), never its audio or text; a manifest written once,
left as it is when the same and refused when it differs; folders that are no recorded call's
refused; and the command's exit codes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from ole5_voice.evals import call_manifests
from ole5_voice.evals.audio import write_wav
from ole5_voice.evals.call_manifests import CallManifest, manifest_of, write_manifests

VERSION = "m2-owner-test-1"
TIMELINE = b'{"clauses": ["made-up words said"]}'


def _call(recordings: Path, call_id: str = "call_1") -> Path:
    folder = recordings / call_id
    folder.mkdir(parents=True)
    (folder / "caller.wav").write_bytes(write_wav(b"\x01\x00" * 16_000))
    (folder / "agent.wav").write_bytes(write_wav(b"\x01\x00" * 12_000, 24_000))
    (folder / "timeline.json").write_bytes(TIMELINE)
    (folder / ".agent.wav.partial").write_bytes(b"half")
    return folder


def test_a_manifest_holds_the_consent_and_each_files_hash_and_length(tmp_path: Path) -> None:
    folder = _call(tmp_path / "recordings")
    manifest = manifest_of(folder, consent_version=VERSION)
    assert manifest.call_id == "call_1"
    assert manifest.consent.model_dump() == {"version": VERSION, "record_audio": True}
    agent, caller, timeline = manifest.files
    assert [f.path for f in manifest.files] == ["agent.wav", "caller.wav", "timeline.json"]
    assert (caller.sample_rate, caller.channels, caller.seconds) == (16_000, 1, 1.0)
    assert (agent.sample_rate, agent.seconds) == (24_000, 0.5)
    assert timeline.sha256 == hashlib.sha256(TIMELINE).hexdigest()
    assert (timeline.bytes, timeline.seconds, timeline.sample_rate) == (len(TIMELINE), None, None)
    text = call_manifests.dump(manifest)
    assert "made-up words" not in text and text.endswith("}\n")
    assert CallManifest.model_validate_json(text) == manifest


def test_a_file_named_wav_that_is_not_one_keeps_its_hash_and_bytes(tmp_path: Path) -> None:
    folder = tmp_path / "call_2"
    folder.mkdir()
    (folder / "caller.wav").write_bytes(b"not a wave file")
    (only,) = manifest_of(folder, consent_version=VERSION).files
    assert (only.bytes, only.seconds) == (15, None)


def test_a_manifest_is_written_once_and_never_over_another(tmp_path: Path) -> None:
    recordings, out = tmp_path / "recordings", tmp_path / "calls"
    _call(recordings)
    _call(recordings, "call_2")
    assert write_manifests(recordings, out, consent_version=VERSION) == (2, 0, 0)
    first = (out / "call_1.json").read_bytes()
    assert write_manifests(recordings, out, consent_version=VERSION) == (0, 2, 0)
    (recordings / "call_1" / "timeline.json").write_bytes(b"{}")
    assert write_manifests(recordings, out, consent_version=VERSION) == (0, 1, 1)
    assert (out / "call_1.json").read_bytes() == first
    assert json.loads(first)["files"][2]["path"] == "timeline.json"


def test_a_folder_that_is_no_recorded_calls_is_refused(tmp_path: Path) -> None:
    recordings = tmp_path / "recordings"
    (recordings / "empty_call").mkdir(parents=True)
    _call(recordings, "not a call id")
    (recordings / "stray.txt").parent.mkdir(exist_ok=True)
    (recordings / "stray.txt").write_bytes(b"a file, not a call's folder")
    assert write_manifests(recordings, tmp_path / "calls", consent_version=VERSION) == (0, 0, 2)
    assert not (tmp_path / "calls").exists()


def test_the_command_says_whether_every_call_has_its_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recordings, out = tmp_path / "recordings", tmp_path / "calls"
    _call(recordings)
    argv = ["--recordings", str(recordings), "--consent-version", VERSION, "--out", str(out)]
    assert call_manifests.main(argv) == 0
    assert "manifests_done" in capsys.readouterr().out and (out / "call_1.json").exists()
    (recordings / "empty").mkdir()
    assert call_manifests.main(argv) == 1
    missing = ["--recordings", str(tmp_path / "none"), "--consent-version", VERSION]
    assert call_manifests.main(missing) == 2
    assert "recordings_missing" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        call_manifests.main(["--recordings", str(recordings), "--consent-version", "a b"])
    assert "no space" in capsys.readouterr().err
