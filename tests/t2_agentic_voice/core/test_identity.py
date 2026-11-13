"""Only the consent a verified signed token carried, which only `adapters` builds, can let audio
be recorded (docs/SECURITY.md, invariant 8): only the very instance the seal validated,
unchanged since, allows it; the common ways to build or change one raise at run time; and
`poe arch` reports the seal's name anywhere but in the verifier and core/identity.py."""

from __future__ import annotations

import ast
import copy
import gc
import pickle
import weakref
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import TypeAdapter, create_model
from t2_agentic_voice.core import identity
from t2_agentic_voice.core.identity import (
    CONSENT_SEAL,
    Consent,
    SignedConsent,
    allows_recording,
)

from scripts.arch_module import ModuleChecker
from scripts.harness_config import load_config
from tests.t2_agentic_voice.core.consent_support import (
    ALLOWS_NOTHING,
    RECORD,
    UNSEALED,
    Holder,
    MixedIn,
    Unchecked,
    deprecated,
    verified,
)

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "packages/t2-agentic-voice/src/t2_agentic_voice"


@pytest.mark.parametrize("build", UNSEALED.values(), ids=UNSEALED.keys())
def test_a_signed_consent_is_built_no_other_way(build: Callable[[SignedConsent], object]) -> None:
    """The common mistakes fail loudly, even with a declined verified consent in hand: no new
    `SignedConsent` comes out, and the refusal says who builds one."""
    with pytest.raises(TypeError, match="Only adapters' SignedJoinTokens builds a SignedConsent"):
        build(verified(record_audio=False))


def test_a_signed_consent_takes_no_subclass() -> None:
    """Refused as it is defined; past a mixin that skips the refusal, as it is validated, and
    one that skips that too allows nothing."""
    with pytest.raises(TypeError, match="takes no subclass"):

        class Mine(SignedConsent):  # type: ignore[misc]
            pass

    with pytest.raises(TypeError, match="takes no subclass"):
        create_model("Mine", __base__=SignedConsent)
    with pytest.raises(TypeError, match="Only adapters' SignedJoinTokens"):
        MixedIn.model_validate(RECORD, context=CONSENT_SEAL)
    mine = Unchecked.model_validate(RECORD, context=CONSENT_SEAL)
    assert isinstance(mine, SignedConsent) and allows_recording(mine) is False


@pytest.mark.parametrize("record_audio", [True, False])
@pytest.mark.parametrize("route", ALLOWS_NOTHING.values(), ids=ALLOWS_NOTHING.keys())
def test_a_consent_allows_recording_only_as_the_seal_validated_it(
    route: Callable[[SignedConsent], object], record_audio: bool
) -> None:
    """From a verified consent that allows recording or from one that does not, whatever the
    route gives allows nothing; and `allows_recording` answers a real boolean."""
    made = route(verified(record_audio=record_audio))
    assert isinstance(made, Consent) and allows_recording(made) is False


@pytest.mark.parametrize(
    "same",
    [
        lambda c: c.model_copy(),
        lambda c: c.model_copy(update={}),
        lambda c: c.model_copy(deep=True),
        lambda c: Consent.model_copy(c),
        lambda c: deprecated(c.copy),
        lambda c: deprecated(lambda: c.copy(deep=True)),
        copy.copy,
        copy.deepcopy,
        lambda c: pickle.loads(pickle.dumps(c)),  # noqa: S301 (the test's own consent)
    ],
    ids=[
        "model_copy",
        "an empty update",
        "deep",
        "Consent's",
        "copy",
        "deep copy",
        "copy.copy",
        "deepcopy",
        "pickle",
    ],
)
def test_a_copy_reads_as_the_consent_and_allows_nothing(
    same: Callable[[SignedConsent], SignedConsent],
) -> None:
    """Only the instance the seal validated lets audio be kept: a copy with no change reads the
    same, and allows nothing."""
    signed = verified(record_audio=True)
    copied = same(signed)
    assert type(copied) is SignedConsent and copied == signed and copied is not signed
    assert allows_recording(copied) is False and allows_recording(signed) is True


def test_a_sealed_consent_allows_recording_while_its_fields_are_unchanged() -> None:
    """Rewritten in place, even to the same text, it allows nothing."""
    signed = verified(record_audio=True)
    assert allows_recording(signed) is True
    assert allows_recording(signed) is True  # asking changes nothing
    signed.__dict__["version"] = "".join(["v", "1"])  # the same text, another object
    assert signed.version == "v1" and allows_recording(signed) is False
    declined = verified(record_audio=False)
    object.__setattr__(declined, "record_audio", True)
    assert allows_recording(declined) is False


def test_a_collected_consent_leaves_the_registry() -> None:
    """The registry holds a sealed consent only while it lives, so it never grows with calls."""
    signed = verified(record_audio=True)
    key, alive = id(signed), weakref.ref(signed)
    assert identity._SEALED[key].consent() is signed
    del signed
    gc.collect()
    assert alive() is None and key not in identity._SEALED


def test_only_a_signed_consent_is_a_verified_tokens_and_only_adapters_build_one() -> None:
    signed = verified(record_audio=True)
    plain = Consent(version="v1", record_audio=True)
    assert isinstance(signed, Consent) and not isinstance(plain, SignedConsent)
    assert signed != plain  # the same choices, but not from a verified token
    assert type(Consent.model_validate(signed.model_dump())) is Consent
    assert allows_recording(signed) is True
    assert allows_recording(verified(record_audio=False)) is False
    assert allows_recording(plain) is False  # DevIdentity's, or a team's own verifier's
    for given in (  # the seal's holder may also build one through a model or a TypeAdapter
        Holder.model_validate({"consent": RECORD}, context=CONSENT_SEAL).consent,
        TypeAdapter(SignedConsent).validate_python(RECORD, context=CONSENT_SEAL),
    ):
        assert given == signed and allows_recording(given) is True


# What a module might write to reach the seal or build a signed consent, with the lines
# `poe arch` reports, read with this repository's harness.toml as the session's recorder.
STAR = "from t2_agentic_voice.core.identity import *\n"
MODULE = "from t2_agentic_voice.core import identity\n"
REACHES: dict[str, tuple[str, list[int]]] = {
    "the seal imported under another name": (
        "from t2_agentic_voice.core.identity import CONSENT_SEAL as S\n",
        [1],
    ),
    "the seal imported relatively": ("from ...core.identity import CONSENT_SEAL\n", [1]),
    "a name bound to the seal": (MODULE + "seal = identity.CONSENT_SEAL\n", [2]),
    "the seal by getattr": (MODULE + "seal = getattr(identity, 'CONSENT_SEAL')\n", [2]),
    "a string that holds the name": (
        MODULE + "seal = getattr(identity, ' CONSENT_SEAL'.strip())\n",
        [2],
    ),
    "an f-string's part": (MODULE + "seal = getattr(identity, f'{x}CONSENT_SEAL')\n", [2]),
    "bytes": (MODULE + "seal = getattr(identity, b'CONSENT_SEAL'.decode())\n", [2]),
    "an escape": (MODULE + "seal = getattr(identity, 'CONSENT\\x5fSEAL')\n", [2]),
    "two literals joined": (MODULE + "seal = getattr(identity, 'CONSENT_' 'SEAL')\n", [2]),
    "a docstring": ('"""Where CONSENT_SEAL is kept."""\n', [1]),
    "a fullwidth spelling": (MODULE + "seal = identity.\uff23ONSENT_SEAL\n", [2]),
    "a class pattern's keyword": (
        MODULE + "match identity:\n    case object(CONSENT_SEAL=seal):\n        pass\n",
        [3],
    ),
    "a star import": (STAR, [1]),
    "a star import, then the name read": (STAR + "seal = CONSENT_SEAL\n", [1, 2]),
    "a star import, then an annotation": (
        STAR + "CONSENT_SEAL: object\nkind = CONSENT_SEAL\n",
        [1, 2, 3],
    ),
    "a star import, then a subscript's key": (STAR + "seen = {}\nseen[CONSENT_SEAL] = 1\n", [1, 3]),
    "a star import, then the name assigned to itself": (
        STAR + "CONSENT_SEAL = CONSENT_SEAL\n",
        [1, 2],
    ),
    "a star import from the verifier": ("from ...adapters.join_tokens import *\n", [1]),
    "the class called": ("SignedConsent(version=None, record_audio=True)\n", [1]),
    "the class validated": ("identity.SignedConsent.model_validate({})\n", [1]),
}


def _construct_lines(source: str, *, rel: str) -> list[int]:
    """The lines ARCH-CONSTRUCT reports in `source`, as the library's module `rel`."""
    arch = load_config(ROOT).arch
    checker = ModuleChecker(arch, layer=rel.split("/")[0], rel=rel, display=rel, source=source)
    checker.visit(ast.parse(source))
    return sorted(v.line for v in checker.violations if v.rule == "ARCH-CONSTRUCT")


@pytest.mark.parametrize(("source", "lines"), REACHES.values(), ids=REACHES.keys())
def test_poe_arch_reports_the_seal_and_the_class_outside_the_verifier(
    source: str, lines: list[int]
) -> None:
    """A TypeAdapter of the class, or a model with a field of it, is the seal's to guard: without
    it, either fails at run time (test_a_signed_consent_is_built_no_other_way)."""
    assert _construct_lines(source, rel="voice/session/recording.py") == lines
    assert _construct_lines(source, rel="adapters/join_tokens.py") == []


def test_only_the_verifier_and_the_module_that_makes_the_seal_mention_it() -> None:
    """core/identity.py defines and checks the seal, and adapters/join_tokens.py gives it; any
    other module is reported, of `adapters` or of `core` too."""
    for rel in ("core/identity.py", "adapters/join_tokens.py"):
        source = (PACKAGE / rel).read_text(encoding="utf-8")
        assert "CONSENT_SEAL" in source
        assert _construct_lines(source, rel=rel) == []
    for rel in ("core/events.py", "adapters/dev_identity.py", "api/join.py"):
        assert _construct_lines("seal = CONSENT_SEAL\n", rel=rel) == [1]
