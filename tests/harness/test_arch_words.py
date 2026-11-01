"""ARCH-WORDS: the library's src/ never names an app, in any case, in a file or its path; bytecode
and the folders above src/ are never read, since they hold the checkout's own absolute path."""

from __future__ import annotations

from pathlib import Path

from scripts.arch_words import check_words
from scripts.check_architecture import ROOT, check_repo
from scripts.harness_config import load_config
from tests.harness.support import ARCHITECTURE, SYNTHETIC, config, write

BANNED = SYNTHETIC.replace("banned_words = []", 'banned_words = ["Shop", "shop.example"]')


def _found(root: Path, files: dict[str, str]) -> list[tuple[str, int]]:
    """(path, line) of each ARCH-WORDS violation in a project holding `files`."""
    write(root, {"ARCHITECTURE.md": ARCHITECTURE, "src/app/__init__.py": "", **files})
    violations, _ = check_repo(root, config(root, BANNED))
    return sorted((v.path, v.line) for v in violations if v.rule == "ARCH-WORDS")


def test_this_library_names_no_app() -> None:
    violations, checked = check_words(ROOT, load_config(ROOT).arch)
    assert checked > 5
    assert violations == [], "\n".join(map(str, violations))


def test_a_banned_word_is_found_in_any_case_and_inside_words(tmp_path: Path) -> None:
    files = {
        "src/app/core/a.py": '"""Built for SHOP."""\nNAME = "shop_voice"\nOK = "workshop"\n',
        "src/app/api/static/page.html": "<p>Calls go to api.Shop.example</p>\n",
        "src/app/domain/notes.md": "No app here.\n",
    }
    assert _found(tmp_path, files) == [
        ("src/app/api/static/page.html", 1),
        ("src/app/api/static/page.html", 1),  # both words, on one line
        ("src/app/core/a.py", 1),
        ("src/app/core/a.py", 2),
        ("src/app/core/a.py", 3),  # inside a longer word too: the check is a substring match
    ]


def test_a_path_below_src_is_read_too(tmp_path: Path) -> None:
    found = _found(tmp_path, {"src/app/adapters/shop_tickets.py": "", "src/app/core/x.json": "{}"})
    assert found == [("src/app/adapters/shop_tickets.py", 1)]


def test_bytecode_other_files_and_the_folders_above_src_are_skipped(tmp_path: Path) -> None:
    root = tmp_path / "shop-checkout"  # the checkout's own folder holds a banned word
    root.mkdir()
    write(root, {"src/app/core/ok.py": "VALUE = 1\n", "src/app/core/logo.svg": "<svg>shop</svg>"})
    pyc = root / "src/app/core/__pycache__/ok.cpython-312.pyc"
    pyc.parent.mkdir()
    pyc.write_bytes(f"\x00{root}/src/app/core/ok.py shop".encode())
    note = root / "src/app/core/__pycache__/note.txt"
    note.write_text("shop", encoding="utf-8")
    assert _found(root, {}) == []


def test_no_banned_word_means_nothing_is_read(tmp_path: Path) -> None:
    write(tmp_path, {"ARCHITECTURE.md": ARCHITECTURE, "src/app/__init__.py": "shop"})
    assert check_words(tmp_path, config(tmp_path).arch) == ([], 0)
