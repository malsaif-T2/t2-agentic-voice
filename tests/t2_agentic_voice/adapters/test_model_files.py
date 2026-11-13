"""The check of a classifier's model files (adapters/model_files.py; D-086, plan 007's Q16): each
file in `stt.classifier_dir` against its pinned size and SHA-256, at every load and by `t2v
doctor`. A missing file, a wrong size and a wrong hash are each refused with a
ConfigurationError naming the file, the setting and the guide's page, never the file's bytes
(GP-19, tests/leaks.py); no folder set, or one that does not exist, is refused with a fix. The
files are small ones the test writes, never a model."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from t2_agentic_voice.adapters.model_files import GUIDE, ModelFile, checked, digest, problem
from t2_agentic_voice.core.errors import ConfigurationError

from tests.leaks import holding, shown

CONTENT = b"made-up model bytes 0123456789 which no error may show"
SHOWN = "made-up model bytes"


def _pinned(folder: Path, name: str, content: bytes = CONTENT) -> ModelFile:
    (folder / name).write_bytes(content)
    return ModelFile(name=name, size=len(content), sha256=hashlib.sha256(content).hexdigest())


def test_files_that_match_their_pins_pass(tmp_path: Path) -> None:
    files = (_pinned(tmp_path, "model.onnx"), _pinned(tmp_path, "labels.json", b"{}"))
    assert checked(tmp_path, files) == tmp_path
    assert [problem(tmp_path, file) for file in files] == [None, None]
    assert digest(tmp_path / "model.onnx") == files[0].sha256


def test_a_file_read_in_chunks_hashes_as_a_whole(tmp_path: Path) -> None:
    big = bytes(range(256)) * 5000  # past one read's chunk
    assert digest(_write(tmp_path / "big.bin", big)) == hashlib.sha256(big).hexdigest()


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


@pytest.mark.parametrize("fault", ["missing", "size", "hash"])
def test_a_missing_or_changed_file_is_refused_naming_it_and_never_its_bytes(
    tmp_path: Path, fault: str
) -> None:
    good = _pinned(tmp_path, "labels.json", b"{}")
    pinned = _pinned(tmp_path, "model.onnx")
    if fault == "missing":
        (tmp_path / "model.onnx").unlink()
    elif fault == "size":
        (tmp_path / "model.onnx").write_bytes(CONTENT + b"!")
    else:
        (tmp_path / "model.onnx").write_bytes(CONTENT.replace(b"0", b"1"))
    with pytest.raises(ConfigurationError) as refused:
        checked(tmp_path, (good, pinned))
    message = refused.value.message
    assert "model.onnx" in message and "stt.classifier_dir" in message
    assert GUIDE in message and "FIX:" in message
    assert {"missing": "missing", "size": "bytes", "hash": "SHA-256"}[fault] in message
    assert holding(SHOWN, shown(refused.value)) == []
    assert holding(pinned.sha256, {"message": message}) == []
    found = problem(tmp_path, pinned)
    assert found is not None and SHOWN not in found


def test_no_folder_or_a_folder_that_is_not_there_is_refused_with_a_fix(tmp_path: Path) -> None:
    files = (ModelFile(name="model.onnx", size=1, sha256="0" * 64),)
    with pytest.raises(ConfigurationError, match=r"stt\.classifier_dir is not set.*FIX"):
        checked(None, files)
    with pytest.raises(ConfigurationError, match=r"not a folder.*FIX"):
        checked(tmp_path / "absent", files)


def test_a_pin_must_be_a_sha256_in_hex() -> None:
    for sha256 in ("0" * 63, "g" * 64, "A" * 64):
        with pytest.raises(ValueError, match="SHA-256"):
            ModelFile(name="model.onnx", size=1, sha256=sha256)
    with pytest.raises(ValueError, match="name"):
        ModelFile(name="../model.onnx", size=1, sha256="0" * 64)
