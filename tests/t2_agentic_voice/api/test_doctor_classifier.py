"""`t2v doctor`'s section for the spoken-language classifier (api/doctor.py; D-086),
shown only under `stt.live_language = "classified"`: each model file in `stt.classifier_dir`
against its pinned SHA-256, as the ONNX files are checked, a changed or missing one failing with
the guide's page, no folder failing with a fix; and under `stt.classifier = "ecapa"` whether
torch is installed and any CUDA package or triton beside it, read from the installed
distributions' metadata, never by importing torch. The files are small ones the test writes."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from t2_agentic_voice.adapters.model_files import ModelFile
from t2_agentic_voice.api.doctor import Check, classifier_checks
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.stt import SttSettings


def _by_name(found: list[Check]) -> dict[str, Check]:
    return {check.name: check for check in found}


def _classified(folder: Path | None, classifier: str = "silero") -> VoiceSettings:
    stt = SttSettings(live_language="classified", classifier=classifier, classifier_dir=folder)  # type: ignore[arg-type]
    return VoiceSettings(env="dev", stt=stt)


def _pins(folder: Path) -> tuple[ModelFile, ...]:
    found = []
    for name, data in (("model.onnx", b"made-up model"), ("labels.json", b"{}")):
        (folder / name).write_bytes(data)
        found.append(ModelFile(name=name, size=len(data), sha256=hashlib.sha256(data).hexdigest()))
    return tuple(found)


def test_the_classifiers_section_shows_only_under_classified_each_file_against_its_pin(
    tmp_path: Path,
) -> None:
    """Each model file's SHA-256 against its pin, as the ONNX files are checked, a changed one
    failing with the guide's page; no section under `session`."""
    files = _pins(tmp_path)
    assert classifier_checks(VoiceSettings(env="dev"), files=files) == []
    found = _by_name(classifier_checks(_classified(tmp_path), files=files))
    assert set(found) == {"classifier model.onnx", "classifier labels.json"}
    assert all(check.ok and check.detail.startswith("sha256 ") for check in found.values())
    (tmp_path / "labels.json").write_bytes(b"[]")
    changed = _by_name(classifier_checks(_classified(tmp_path), files=files))
    assert not changed["classifier labels.json"].ok
    assert "docs/guide/languages.md" in changed["classifier labels.json"].detail
    unset = classifier_checks(_classified(None), files=files)
    assert [(c.name, c.ok) for c in unset] == [("classifier folder", False)]
    assert "stt.classifier_dir" in unset[0].detail and "FIX:" in unset[0].detail


def test_under_ecapa_the_doctor_finds_torch_and_any_cuda_package_without_importing_it(
    tmp_path: Path,
) -> None:
    files = _pins(tmp_path)
    settings = _classified(tmp_path, "ecapa")
    imported = "torch" in sys.modules
    cpu = _by_name(
        classifier_checks(settings, files=files, installed={"torch": "2.15.0", "numpy": "2"})
    )
    assert cpu["torch"].ok and "2.15.0" in cpu["torch"].detail and cpu["cuda"].ok
    gpu = {"torch": "2.15.0", "nvidia-cudnn-cu13": "9", "triton": "3.9"}
    found = _by_name(classifier_checks(settings, files=files, installed=gpu))
    assert not found["cuda"].ok and "nvidia-cudnn-cu13" in found["cuda"].detail
    assert "triton" in found["cuda"].detail and "FIX:" in found["cuda"].detail
    missing = _by_name(classifier_checks(settings, files=files, installed={}))
    assert not missing["torch"].ok and "uv sync --group language-id" in missing["torch"].detail
    silero = _by_name(classifier_checks(_classified(tmp_path), files=files, installed={}))
    assert "torch" not in silero  # Silero needs no torch
    assert ("torch" in sys.modules) == imported  # read from the metadata, never imported
