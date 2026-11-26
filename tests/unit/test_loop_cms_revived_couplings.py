# SPDX-License-Identifier: 0BSD
"""Couplings restriction simplification removed and the complex-mass scheme
revives (``cms-revived-coupling``).

``simplify = true`` removes every coupling that is zero at the restriction
card's values. A removed coupling with no runtime (external) dependence
records no specialisation guard: no binding can change it. The complex-mass
transform changes parameter values without any binding, though: the NLOCT
convention parameter ``CMSParam`` becomes 1, the Yukawa inputs follow the
(pole) masses, masses with a width become complex pole masses. The compile
therefore records every removed coupling (``CompiledModel.removed_couplings``)
and the transform evaluates them again with its own substitutions and
arithmetic (``model_cms.tree_model_payload``); one it does not leave zero is
refused at admission (generation and dry run), naming it, the transform and
the remedy, instead of computing without its vertex.
"""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import replace
from importlib import resources
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("symbolica")

_ELECTRON_Z = (
    "GC_24 = Coupling(name = 'GC_24',\n"
    "                 value = '(ee*complex(0,1)*sw)/(2.*cw)'"
)
_PHOTON_DOWN = "'-(ee*complex(0,1))/3.'"
_CMS_PARAMETER = (
    "\nCMSParam = Parameter(name = 'CMSParam', nature = 'internal', "
    "type = 'real', value = '0.0', texname = 'CMSParam')\n"
)
_POINT = [
    ["250", "0", "0", "250"],
    ["250", "0", "0", "-250"],
    ["250", "150", "0", "200"],
    ["250", "-150", "0", "-200"],
]
# loop_sm's card "test": every Yukawa but the tau's is zero while the b and t
# masses are not; under the complex-mass scheme the Yukawas follow the masses.
_TEST_CARD_REVIVED = (
    "GC_1015",
    "GC_1021",
    "GC_1027",
    "GC_1030",
    "GC_1082",
    "GC_1095",
    "GC_33",
    "GC_37",
)


def _switched_loop_sm(
    destination: Path, original: str, factor: str = "CMSParam"
) -> Path:
    """A copy of the shipped loop_sm with the coupling ``original`` times the
    NLOCT convention parameter ``CMSParam`` (internal, 0 in the real scheme,
    1 under the complex-mass scheme), or times ``factor`` (which should
    contain it)."""

    shipped = Path(
        str(resources.files("pyamplicol").joinpath("assets/models/ufo/loop_sm"))
    )
    shutil.copytree(shipped, destination, ignore=shutil.ignore_patterns("__pycache__"))
    couplings = destination / "couplings.py"
    text = couplings.read_text(encoding="utf-8")
    assert text.count(original) == 1
    couplings.write_text(
        text.replace(original, original[:-1] + f"*{factor}'"), encoding="utf-8"
    )
    with (destination / "parameters.py").open("a", encoding="utf-8") as parameters:
        parameters.write(_CMS_PARAMETER)
    return destination


def _card(
    root: Path,
    model: Path | str,
    process: str,
    *,
    simplify: bool = True,
    restriction: str | None = None,
    mass_scheme: str = "complex-mass",
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    card = root / "card.toml"
    card.write_text(
        f"""action = "generate"
[model]
source = "{model}"
simplify = {json.dumps(simplify)}
{"" if restriction is None else f'restriction = "{restriction}"'}
cache_dir = "{root / "cache"}"
[process]
entries = [{{expression = {json.dumps(process)}, name = "p"}}]
loop_coupling_orders = ["QCD"]
[loop]
external_widths = "zero"
r2_strategy = "model"
[loop.model]
loop_coupling_orders = ["QCD"]
uv_complete = true
model_r2_complete = true
[loop.model.scheme]
dimensional_regularization = "HV"
external_states = "physical-four-dimensional"
gamma5 = "source-UFO-four-dimensional-prescription"
renormalization = "source-UFO mass-dependent decoupling"
mass_scheme = "{mass_scheme}"
finite_restoration = "source-UFO-local-rules"
model_convention = "loop_sm lhv=1 supplied QCD rules"
[loop.preparation]
fixed_parameters = {{ WW = "0", WZ = "0" }}
[generation]
output = "{root / "artifact"}"
emit_api_bundle = false
[generation.validation]
post_build_validation = false
"""
    )
    return card


def _generate(card: Path, process: str) -> Path:
    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config

    config = resolve_config(card)
    output = Path(config.effective.generation.output)
    Generator(config).generate(
        ProcessSet((ProcessRequest.parse(process, name="p"),)), output
    )
    return output


def _dry_run(card: Path, process: str) -> tuple[str, ...]:
    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config

    plan = Generator(resolve_config(card)).plan(
        ProcessSet((ProcessRequest.parse(process, name="p"),))
    )
    return tuple(plan.unsupported_features)


def _born_and_finite(artifact: Path) -> list[list[float]]:
    from pyamplicol.api import Runtime

    result = Runtime.load(artifact).evaluate(
        [_POINT], mu_r2=["250000"], arithmetic="double"
    )
    return [
        [complex(value).real for value in result.born_values[0]],
        [complex(value.finite).real for value in result.values[0]],
    ]


def _refused(card: Path, process: str) -> str:
    from pyamplicol.loops.model_cms import ComplexMassSchemeUnsupported

    with pytest.raises(ComplexMassSchemeUnsupported) as refused:
        _generate(card, process)
    assert refused.value.key == "cms-revived-coupling"
    # The dry run (the model is in the cache now) lists the same refusal.
    (blocker,) = _dry_run(card, process)
    assert blocker.startswith("cms-revived-coupling: "), blocker
    message = str(refused.value)
    assert "simplify = false" in message
    return message


# ------------------------------------------------------------- the record


@pytest.mark.loop_fast
def test_the_record_round_trips_and_an_older_record_is_no_record(tmp_path):
    """The removed couplings serialise with the compiled model; a model whose
    record predates them (``"complete"``: the guards only) is read as one
    without a record, which generation refuses (re-prepare); an unknown
    record is an error."""

    from pyamplicol.models.loading import (
        SPECIALIZATION_RECORD,
        CompiledModel,
        compile_model_source,
        require_specialization_record,
    )

    builtin = compile_model_source("built-in-sm", cache_dir=tmp_path)
    removed = (
        {
            "name": "GC_9",
            "expression": "UFO::CMSParam*UFO::ee",
            "orders": [["QED", 1]],
            "value": [0.0, 0.0],
        },
    )
    source = {
        **builtin.source,
        "kind": "ufo",
        "options": {**dict(builtin.source.get("options", {})), "simplify": True},
    }
    model = replace(
        builtin,
        source=source,
        specialization_record=True,
        removed_couplings=removed,
    )
    payload = model.to_dict()
    assert payload["specialization_record"] == SPECIALIZATION_RECORD
    assert payload["removed_couplings"] == [dict(removed[0])]
    restored = CompiledModel.from_dict(payload, validate_fingerprint=False)
    assert restored.removed_couplings == removed
    assert require_specialization_record(restored) is restored

    older = {**payload, "specialization_record": "complete"}
    older.pop("removed_couplings")
    legacy = CompiledModel.from_dict(older, validate_fingerprint=False)
    assert not legacy.specialization_record
    with pytest.raises(ValueError, match="prepare or compile the model again"):
        require_specialization_record(legacy)
    with pytest.raises(ValueError, match="unknown specialisation record"):
        CompiledModel.from_dict(
            {**payload, "specialization_record": "future"},
            validate_fingerprint=False,
        )
    with pytest.raises(ValueError, match="sorted and unique"):
        CompiledModel.from_dict(
            {**payload, "removed_couplings": [dict(removed[0])] * 2},
            validate_fingerprint=False,
        )
    # A model without removed couplings writes no field.
    assert "removed_couplings" not in replace(model, removed_couplings=()).to_dict()


def _environment_model(externals, internals):
    """A minimal ``ufo_model_loader`` model view (``GuardEnvironment.
    from_ufo_model``): ``externals`` name -> value, ``internals`` name ->
    expression text or a constant value."""

    from symbolica import E

    def parameter(name, value=None, expression=None):
        return SimpleNamespace(
            name=name,
            value=value,
            expression=None if expression is None else E(expression),
            parameter_type="real",
        )

    return SimpleNamespace(
        get_external_parameters=lambda: [
            parameter(name, value) for name, value in externals.items()
        ],
        get_internal_parameters=lambda: [
            parameter(name, value=item)
            if not isinstance(item, str)
            else parameter(name, expression=item)
            for name, item in internals.items()
        ],
        get_model_variables=lambda: {},
    )


@pytest.mark.loop_fast
def test_the_rule_after_a_transform():
    """A removed coupling stays removed only if it is provably zero for every
    value of the externals, under both exact readings of its numbers (the
    shortest decimal and the exact binary64), with no binary64 arithmetic:
    a value that is zero only in binary64, zero only at the current values,
    zero in one reading only, or not reducible is refused. The binary64 value
    is never evidence (a value the evaluation did not set, NaN, changes
    nothing)."""

    from symbolica import E

    from pyamplicol.models.specialization_guards import revived_removed_couplings

    cmass = "(UFO::MT^2-UFO::I*UFO::MT*UFO::WT)^(1/2)"
    model = _environment_model(
        {"MT": 173.0, "WT": 1.5},
        {
            "CMSParam": 1.0,
            "ZERO": 0.0,
            "I": 1j,
            "TENTH": 0.1,
            "K": "UFO::MT-173",
            "L": "UFO::MT-UFO::MT",
            "CMASS_MT": cmass,
        },
    )

    def coupling(name, expression, value=0.0):
        return SimpleNamespace(name=name, expression=E(expression), value=value)

    found = revived_removed_couplings(
        model,
        [
            coupling("revived", "UFO::CMSParam*UFO::WT", 1.5),
            coupling("constant", "UFO::ZERO*UFO::CMSParam"),
            coupling("identical", "UFO::L*UFO::CMSParam"),
            coupling("at-values", "UFO::K*UFO::CMSParam"),
            coupling("unset", "UFO::CMSParam", complex(math.nan, 0.0)),
            # Order one, zero in binary64 only (the reviewer's cancellation).
            coupling(
                "binary64-only",
                "2*10^8*UFO::I*UFO::CMSParam*(10000000000000001^(1/2)-100000000)",
            ),
            # Zero exactly at the decimal 1/10, not at the binary64 0.1.
            coupling("one-reading", "UFO::CMSParam*(3*UFO::TENTH-3/10)"),
            # An algebraic identity of the complex pole mass: provably zero,
            # whatever its binary64 value (rounding) is.
            coupling(
                "pole-identity",
                "UFO::CMSParam*((UFO::CMASS_MT+UFO::WT)^2-UFO::CMASS_MT^2"
                "-2*UFO::CMASS_MT*UFO::WT-UFO::WT^2)",
                complex(0.0, 2.0**-40),
            ),
            # A branch identity Symbolica does not take: not proven, refused.
            coupling("branch", "UFO::CMSParam*((UFO::MT^2)^(1/2)-UFO::MT)"),
        ],
    )
    assert [(item.name, item.revived) for item in found] == [
        ("revived", True),
        ("at-values", False),
        ("unset", True),
        ("binary64-only", False),
        ("one-reading", False),
        ("branch", False),
    ]
    by_name = {item.name: item for item in found}
    assert by_name["at-values"].parameters == ("MT",)
    assert "a binding would revive it" in by_name["at-values"].describe()
    assert by_name["binary64-only"].parameters == ()
    assert "not proven exactly zero" in by_name["binary64-only"].describe()


# ------------------------------------------------------- custom loop_sm models


@pytest.fixture(scope="module")
def electron_z_switched(tmp_path_factory) -> Path:
    return _switched_loop_sm(
        tmp_path_factory.mktemp("cms-switch") / "loop_sm_cms_switch", _ELECTRON_Z
    )


@pytest.fixture(scope="module")
def shipped_cms_reference(tmp_path_factory) -> list[list[float]]:
    """The shipped loop_sm's complex-mass u u~ > e+ e- (GC_24 itself)."""

    root = tmp_path_factory.mktemp("cms-shipped")
    return _born_and_finite(
        _generate(_card(root, "loop_sm", "u u~ > e+ e-"), "u u~ > e+ e-")
    )


@pytest.mark.loop_physics
def test_a_born_only_coupling_the_scheme_revives_is_refused(
    electron_z_switched, shipped_cms_reference, tmp_path
) -> None:
    """The reviewer's model: the electron-Z coupling GC_24 times CMSParam,
    removed at CMSParam = 0 with no runtime dependence (no guard). Under the
    complex-mass scheme it is GC_24 again. It enters only the Born of
    u u~ > e+ e- [QCD] (no QCD loop dresses the lepton vertex), so the loop
    generation's own check never meets it: the Born was 0.00141029 against
    0.00059438 before. Now it is refused at admission; without
    simplification the model is the shipped one and gives its values."""

    message = _refused(
        _card(tmp_path / "s", electron_z_switched, "u u~ > e+ e-"), "u u~ > e+ e-"
    )
    assert "GC_24 = " in message and "CMSParam = 1" in message
    unsimplified = _born_and_finite(
        _generate(
            _card(tmp_path / "u", electron_z_switched, "u u~ > e+ e-", simplify=False),
            "u u~ > e+ e-",
        )
    )
    assert unsimplified[0] == pytest.approx([0.000594378368], rel=1e-9)
    assert [*unsimplified[0], *unsimplified[1]] == pytest.approx(
        [*shipped_cms_reference[0], *shipped_cms_reference[1]], rel=1e-12
    )
    # The same model in the real scheme keeps CMSParam = 0: nothing revived.
    real = _born_and_finite(
        _generate(
            _card(
                tmp_path / "r",
                electron_z_switched,
                "u u~ > e+ e-",
                mass_scheme="real-on-shell",
            ),
            "u u~ > e+ e-",
        )
    )
    assert real[0][0] != pytest.approx(shipped_cms_reference[0][0], rel=1e-3)


@pytest.mark.loop_physics
def test_a_loop_dressed_coupling_the_scheme_revives_is_refused_at_admission(
    tmp_path,
) -> None:
    """The photon-down coupling times CMSParam: QCD loops of d d~ > e+ e-
    dress the vertex, so the loop generation used to fail late
    (``loop-vertex-outside-tree-model``); the record refuses it at
    admission, before any tree or loop."""

    model = _switched_loop_sm(tmp_path / "loop_sm_gc1", _PHOTON_DOWN)
    message = _refused(_card(tmp_path / "s", model, "d d~ > e+ e-"), "d d~ > e+ e-")
    assert "GC_1 = " in message
    assert "loop-vertex-outside-tree-model" not in message


@pytest.mark.loop_physics
def test_a_revived_coupling_zero_only_in_binary64_is_refused(tmp_path) -> None:
    """The electron-Z coupling replaced by an order-one constant that cancels
    in binary64, times CMSParam: 2e8 i (sqrt(10000000000000001) - 10^8) is
    about i, but 0 in binary64. Removed at CMSParam = 0 (exactly zero there),
    revived under the complex-mass scheme, where its binary64 value is still
    0: a numerical test would accept it and compute without it. The exact
    test cannot reduce the square root of a non-square: refused."""

    model = _switched_loop_sm(tmp_path / "loop_sm_cancel", _ELECTRON_Z)
    couplings = model / "couplings.py"
    text = couplings.read_text(encoding="utf-8")
    switched = "'(ee*complex(0,1)*sw)/(2.*cw)*CMSParam'"
    assert text.count(switched) == 1
    couplings.write_text(
        text.replace(
            switched,
            "'2.e8*complex(0,1)*CMSParam*(cmath.sqrt(10000000000000001.)-100000000.)'",
        ),
        encoding="utf-8",
    )
    message = _refused(_card(tmp_path / "s", model, "u u~ > e+ e-"), "u u~ > e+ e-")
    assert "GC_24 (zero in binary64 here, but not proven exactly zero" in message


@pytest.mark.loop_physics
def test_a_coupling_zero_by_a_pole_mass_identity_stays_removed(tmp_path) -> None:
    """The electron-Z coupling times CMSParam ((MT+WT)^2 - MT^2 - 2 MT WT -
    WT^2): under the complex-mass scheme MT is the pole mass CMASS_MT =
    sqrt(MT^2 - i MT WT), and the factor is an identity in it, whose binary64
    value is rounding. Proven exactly zero: the request generates without
    the coupling, and equals the model without the electron-Z coupling (the
    reviewer's simplified value). The unsimplified twin keeps a vertex whose
    coupling is pure rounding, which the native export refuses
    (``plane-mismatch``): no silent value either way."""

    from pyamplicol.loops.v2.refusals import NativeExportRefused

    model = _switched_loop_sm(
        tmp_path / "loop_sm_identity",
        _ELECTRON_Z,
        "CMSParam*((MT+WT)**2-MT**2-2*MT*WT-WT**2)",
    )
    born, finite = _born_and_finite(
        _generate(_card(tmp_path / "s", model, "u u~ > e+ e-"), "u u~ > e+ e-")
    )
    assert born == pytest.approx([0.0014102944360971175], rel=1e-12)
    assert finite == pytest.approx([6.602378073479062e-05], rel=1e-9)
    with pytest.raises(NativeExportRefused, match="plane-mismatch"):
        _generate(
            _card(tmp_path / "u", model, "u u~ > e+ e-", simplify=False),
            "u u~ > e+ e-",
        )


@pytest.mark.loop_physics
def test_the_shipped_test_card_is_refused_with_its_revived_yukawas(tmp_path) -> None:
    """loop_sm's card "test" zeroes the Yukawa inputs while the b and t masses
    are not zero; under the complex-mass scheme the Yukawas follow the
    masses, which revives the eight couplings simplification removed with
    them. Refused at admission (b b~ > h g failed late before, with
    ``loop-vertex-outside-tree-model``; u u~ > e+ e-, which meets none of
    them, is refused too: the record is the model's)."""

    for index, process in enumerate(("b b~ > h g", "u u~ > e+ e-")):
        message = _refused(
            _card(tmp_path / f"t{index}", "loop_sm", process, restriction="test"),
            process,
        )
        assert "the Yukawa inputs follow the masses" in message
        named = sorted(
            part.split(" = ")[0].strip()
            for part in message.split("): ", 1)[1]
            .split(". The simplified")[0]
            .split(", ")
        )
        assert named == sorted(_TEST_CARD_REVIVED)


@pytest.mark.loop_physics
def test_every_shipped_loop_card_but_test_transforms(tmp_path) -> None:
    """Every restriction card of the shipped loop models (widths fixed to
    zero, so that loop_sm's internal W mass is admitted) passes the
    complex-mass transform with its removed couplings evaluated again, but
    loop_sm's card "test". The G_mu UFO's card "parallel_test" does not load
    (its SLHA card assigns SMINPUTS 1 twice), with or without this record."""

    from pyamplicol.loops.model_cms import (
        ComplexMassSchemeUnsupported,
        complex_mass_model,
    )
    from pyamplicol.models.loading import compile_model_source

    assets = Path(str(resources.files("pyamplicol").joinpath("assets/models/ufo")))
    refused = []
    for name in ("loop_sm", "loop_qcd_qed_sm", "loop_qcd_qed_sm_Gmu"):
        for card in sorted((assets / name).glob("restrict_*.dat")):
            restriction = card.stem.removeprefix("restrict_")
            if (name, restriction) == ("loop_qcd_qed_sm_Gmu", "parallel_test"):
                with pytest.raises(Exception, match="already define"):
                    compile_model_source(
                        name, restriction=restriction, cache_dir=tmp_path
                    )
                continue
            compiled = compile_model_source(
                name,
                restriction=restriction,
                cache_dir=tmp_path,
                require_supported=False,
            )
            assert compiled.specialization_record
            widths = {
                particle["width"]
                for particle in compiled.model["particles"]
                if particle["width"] in compiled.parameter_defaults
            }
            try:
                complex_mass_model(
                    compiled,
                    fixed_parameters={width: "0" for width in widths},
                    cache_dir=tmp_path,
                )
            except ComplexMassSchemeUnsupported as error:
                refused.append((name, restriction, error.key))
    assert refused == [("loop_sm", "test", "cms-revived-coupling")]
