"""`poe eval-timing`'s refusals, each before anything is sent: the main checkout, a dirty tree,
a setting the registration fixes, a missing price, a folder name that is no name, data with no
paused request, and the flags a run needs together."""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.evals import timing
from ole5_voice.evals.timing import TimingParts

from tests.ole5_voice.evals.eot_support import golden_set, parts_of, paused
from tests.ole5_voice.evals.timing_support import ENGLISH, Setup, make_setup


@pytest.fixture
def setup(tmp_path: Path) -> Setup:
    return make_setup(tmp_path)


@pytest.mark.parametrize(
    ("main", "dirty", "named"), [(True, False, "main checkout"), (False, True, "has changes")]
)
def test_a_run_refuses_the_main_checkout_and_a_dirty_tree(
    setup: Setup, main: bool, dirty: bool, named: str, capsys: pytest.CaptureFixture[str]
) -> None:
    parts = setup.parts()
    if main:
        setup.world.git.top = setup.world.main
        parts = TimingParts(
            **{
                **parts.__dict__,
                "plan": type(parts.plan)(**{**parts.plan.__dict__, "folder": setup.world.main}),
            }
        )
    setup.world.git.dirty = dirty
    assert timing.main(setup.argv(), parts=parts) == 2
    assert named in capsys.readouterr().out
    assert setup.echo.asked == [] and setup.cache.declared == [] and not setup.out.exists()


def test_a_run_refuses_settings_the_registration_fixes_and_a_missing_price(
    setup: Setup, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("T2V_TTS__TRIM_SILENCE", "true")
    assert timing.main(setup.argv(), parts=setup.parts()) == 2
    assert "tts.trim_silence false" in capsys.readouterr().out
    monkeypatch.delenv("T2V_TTS__TRIM_SILENCE")
    argv = setup.argv()
    del argv[argv.index(f"{ENGLISH}=22") - 1 : argv.index(f"{ENGLISH}=22") + 1]
    assert timing.main(argv, parts=setup.parts()) == 2
    assert f"no price for {ENGLISH}" in capsys.readouterr().out
    assert setup.echo.asked == []


def test_a_run_refuses_a_folder_name_that_is_no_name_and_data_with_no_mark(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = setup.argv()
    argv[argv.index("--out") + 1] = str(setup.world.main / "var" / "runs" / "Bad Name")
    assert timing.main(argv, parts=setup.parts()) == 2
    assert "is not a name" in capsys.readouterr().out
    only = parts_of(setup.world, golden_set(paused(setup.world, "r1", kind="request")))
    parts = TimingParts(**{**setup.parts().__dict__, "plan": only})
    assert timing.main(setup.argv(), parts=parts) == 2
    assert "no paused request" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("change", "named"),
    [
        (["--note"], "a run needs"),
        (["--tts-price", "no-price"], "MODEL=USD"),
        (["--stt-rpm", "0"], "1 or more"),
        (["--cap-usd", "-1"], "0 or more"),
    ],
)
def test_the_flags_a_run_needs(
    setup: Setup, change: list[str], named: str, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = setup.argv()
    if change == ["--note"]:
        argv = argv[: argv.index("--note")]
    else:
        argv += change
    with pytest.raises(SystemExit):
        timing.main(argv, parts=setup.parts())
    assert named in capsys.readouterr().err
    with pytest.raises(SystemExit):
        timing.main([*setup.argv()[:-2], "--note", "{{" + "X}}"], parts=setup.parts())
    assert "placeholder" in capsys.readouterr().err
