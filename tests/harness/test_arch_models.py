"""The architecture's rules for the spoken-language classifiers' libraries (harness.toml; plan 007's
Block H): torch, torchaudio and SpeechBrain are `adapters`' alone (ARCH-OWNER), read in an import
statement and in a call that loads a literal name alike, so an import of torch outside
`adapters` is reported with its fix; `huggingface_hub` stays out of the library's own code
(ARCH-BAN), so no adapter fetches a model at run time (the design's 11); every module the ECAPA
adapter loads is provided by a requirement of the library's `ecapa` extra, read from the source
and the pyproject, never from what is installed, so the answer is one with or without the
`language-id` group; and importing every module of the library, in a new process, loads neither
torch nor SpeechBrain, so `poe check` imports no torch with the group installed either (that
child is test_arch_ban.py's, which also keeps Pipecat's runner out). The rules are this
repository's own, rendered onto the synthetic project of support.py, whose `adapters` layer
stands in for the library's."""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

from scripts.arch_ban import imported
from scripts.check_architecture import check_repo
from scripts.harness_config import load_config
from tests.harness.support import ARCHITECTURE, SYNTHETIC, config, write

ROOT = Path(__file__).resolve().parents[2]
ARCH = load_config(ROOT).arch
LIBRARY = ROOT / "packages" / "t2-agentic-voice"
ECAPA = LIBRARY / "src" / "t2_agentic_voice" / "adapters" / "ecapa_language.py"


def _quoted(values: object) -> str:
    return "[" + ", ".join(f'"{value}"' for value in sorted(values)) + "]"  # type: ignore[call-overload]


def _rules() -> str:
    """This repository's owner rule of torch and its ban of `huggingface_hub`, on `app`."""
    owner = ARCH.owners["torch"]
    (ban,) = [b for b in ARCH.bans if b.banned("huggingface_hub")]
    return (
        f"\n[[owners]]\nmodules = {_quoted(['torch', 'torchaudio', 'speechbrain'])}\n"
        f'layers = ["adapters"]\nfix = "{owner.fix}"\n'
        f'\n[[bans]]\nmodules = ["huggingface_hub"]\nallowed = []\nwithin = ["app"]\n'
        f'fix = "{ban.fix}"\n'
    )


def test_this_repositorys_rules_give_torch_to_adapters_and_ban_huggingface_hub() -> None:
    for name in ("torch", "torchaudio", "speechbrain"):
        assert ARCH.owners[name].layers == frozenset({"adapters"}), name
    assert "adapters" in ARCH.owners["torch"].fix and "extra" in ARCH.owners["torch"].fix
    for module in ("huggingface_hub", "huggingface_hub.file_download"):
        assert any(b.scope("t2_agentic_voice.adapters.x") and b.banned(module) for b in ARCH.bans)
        assert any(b.scope("t2_agentic_voice") and b.banned(module) for b in ARCH.bans)
    smart_turn = [
        b for b in ARCH.bans if b.banned("pipecat.audio.turn.smart_turn.local_smart_turn_v2")
    ]
    assert "the base install" in smart_turn[0].fix


def test_torch_outside_adapters_and_huggingface_hub_anywhere_are_reported_with_their_fix(
    tmp_path: Path,
) -> None:
    files = {
        "src/app/__init__.py": "",
        "src/app/services/use.py": "import torch\n",
        "src/app/core/load.py": "import importlib\nimportlib.import_module('torchaudio')\n",
        "src/app/api/route.py": "from speechbrain.inference import classifiers\n",
        "src/app/adapters/model.py": (
            "import importlib\nimportlib.import_module('torch')\n"
            "importlib.import_module('speechbrain.inference.classifiers')\n"
        ),
        "src/app/adapters/fetch.py": "from huggingface_hub import hf_hub_download\n",
        "src/app/domain/hub.py": "import importlib\nimportlib.import_module('huggingface_hub')\n",
    }
    write(tmp_path, {"ARCHITECTURE.md": ARCHITECTURE, **files})
    violations, _ = check_repo(tmp_path, config(tmp_path, SYNTHETIC + _rules()))
    found = sorted(
        (v.path.removeprefix("src/app/"), v.rule, v.fix)
        for v in violations
        if v.rule in ("ARCH-OWNER", "ARCH-BAN")
    )
    owner, (ban,) = (
        ARCH.owners["torch"].fix,
        [b.fix for b in ARCH.bans if b.banned("huggingface_hub")],
    )
    assert found == [
        ("adapters/fetch.py", "ARCH-BAN", ban),
        ("api/route.py", "ARCH-OWNER", owner),
        ("core/load.py", "ARCH-OWNER", owner),
        ("domain/hub.py", "ARCH-BAN", ban),
        ("services/use.py", "ARCH-OWNER", owner),
    ]


def _normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def test_every_module_the_ecapa_adapter_loads_comes_with_the_ecapa_extra() -> None:
    project = tomllib.loads((LIBRARY / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    names = r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)"
    extra = {
        _normalized(m.group(1))
        for r in project["optional-dependencies"]["ecapa"]
        if (m := re.match(names, r))
    }
    base = {_normalized(m.group(1)) for r in project["dependencies"] if (m := re.match(names, r))}
    assert extra == {"speechbrain", "torch", "torchaudio"}
    loaded = {
        name.split(".")[0] for name, _ in imported(ast.parse(ECAPA.read_text(encoding="utf-8")))
    }
    outside = loaded - set(sys.stdlib_module_names) - {"t2_agentic_voice", "__future__"}
    assert {"torch", "speechbrain"} <= outside
    for module in outside:
        assert _normalized(module) in extra | base, module
    assert {_normalized(m) for m in outside} & base == {"numpy"}  # all else is the extra's
