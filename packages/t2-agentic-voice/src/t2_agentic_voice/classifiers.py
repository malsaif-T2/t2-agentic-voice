"""The spoken-language classifiers behind the `LanguageClassifier` port (D-086):
Silero's, on onnxruntime, and ECAPA's, on torch through the library's `ecapa` extra, each
loading only from the folder `stt.classifier_dir` names. Provisional. A facade: it only
re-exports (ARCH-FACADE)."""

from t2_agentic_voice.adapters.ecapa_language import EcapaLanguage
from t2_agentic_voice.adapters.silero_language import SileroLanguage

__all__ = ["EcapaLanguage", "SileroLanguage"]
