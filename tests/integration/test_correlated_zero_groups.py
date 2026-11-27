# SPDX-License-Identifier: 0BSD
"""Colour and spin correlations of processes with helicity-dependent zeros.

Correlated generation keeps one coherent amplitude group per retained helicity
and colour sector that has diagrams. When a pairing of the quark lines is
joined only by colour-neutral exchanges (``u u~ > d d~`` at QCD = 0,
``u c~ > d s~ d d~`` at every order), that pairing has diagrams only at the
helicities that keep each of its massless lines at one chirality, and for a W
only at the left-handed ones: there that colour sector's amplitude is an exact
zero. The correlator payload lists each such (helicity, sector) pair as a
certified zero group (correlator schema 2, written only when there is one);
readers take a listed group as an exact zero and refuse any other gap. Where
the chirality selection of the DAG build rests on a coupling that is zero only
at the generation values of runtime parameters, its decision is a
specialisation guard: a binding that would revive the dropped chirality is
refused.

References: the uncorrelated amplitude of independent generations in the
compiled and eager lanes, MadGraph 3.7.0 (``madgraph-split-orders.json``, UFO
``sm`` default restriction), colour conservation
``sum_{j != i} <T_i.T_j> = -C_i <B>`` and the polarisation completeness of a
gluon leg; the native SDKs against the Python reader.
"""

from __future__ import annotations

import json
import math
import subprocess
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from pyamplicol import (
    ColorCorrelator,
    CorrelatedRequest,
    CorrelatorConfig,
    Generator,
    ModelSource,
    ProcessSet,
    Runtime,
)
from pyamplicol.api.errors import ArtifactError, EvaluationError
from pyamplicol.config import (
    ColorConfig,
    EvaluatorConfig,
    EvaluatorOptimizationConfig,
    GenerationConfig,
    GenerationRelationDiscoveryConfig,
    GenerationValidationConfig,
    JITConfig,
    ModelConfig,
    ProcessConfig,
    RunConfig,
)
from pyamplicol.generation.phase_space import massive_rambo_final_state
from tests.integration.test_correlated_native_sdk import (
    _PHYSICS_PROBES,
    _write_physics_input,
)
from tests.integration.test_runtime_selector_api_parity import (
    _compile_probe,
    _source_environment,
)
from tests.integration.test_runtime_selector_api_parity import (
    native_sdk as _native_sdk_fixture,
)

native_sdk = _native_sdk_fixture

REFERENCE = (
    Path(__file__).resolve().parents[1] / "fixtures/tree/madgraph-split-orders.json"
)
ALL_ORDERS = {"QCD": 99, "QED": 99}
QCD_ZERO = {"QCD": 0, "QED": 99}
# The built-in SM serves one Born coupling order per process: "every order"
# is the default order policy there and the explicit limits on the UFO sm.
DEFAULT = None
# (process, coupling-order limits, MadGraph reference entry or None).
CASES = (
    ("u u~ > d d~", QCD_ZERO, "u u~ > d d~"),
    ("u d > u d", QCD_ZERO, "u d > u d"),
    ("u c~ > d s~ d d~", DEFAULT, "u c~ > d s~ d d~"),
    ("u c~ > d s~ d d~", QCD_ZERO, "u c~ > d s~ d d~ QCD=0"),
    ("u u~ > d d~ g", {"QCD": 1, "QED": 99}, None),
)
IDS = ("uux-ddx-qcd0", "ud-ud-qcd0", "ucx-dsxddx", "ucx-dsxddx-qcd0", "uux-ddxg-qcd1")


def _configuration(accuracy: str, limits, execution_mode: str = "compiled"):
    return RunConfig(
        action="generate",
        model=ModelConfig(cache=False),
        color=ColorConfig(accuracy=accuracy),
        process=ProcessConfig()
        if limits is None
        else ProcessConfig(
            coupling_order_policy="explicit", max_coupling_orders=limits
        ),
        generation=GenerationConfig(
            workers=1,
            emit_api_bundle=False,
            relation_discovery=GenerationRelationDiscoveryConfig(mode="off"),
            validation=GenerationValidationConfig(
                enabled=False, samples=1, seed=7, post_build_validation=False
            ),
        ),
        evaluator=EvaluatorConfig(
            execution_mode=execution_mode,
            optimization=EvaluatorOptimizationConfig(cores=1, horner_iterations=1),
            jit=JITConfig(optimization_level=0),
        ),
    )


def _legs(process: str) -> int:
    return len(process.replace(">", " ").split())


def _casimir(name: str) -> Decimal:
    return Decimal(3) if name == "g" else Decimal(4) / 3


def _declarations(process: str) -> CorrelatorConfig:
    names = process.replace(">", " ").split()
    coloured = [leg for leg, name in enumerate(names, 1) if name not in ("a",)]
    gluons = [leg for leg, name in enumerate(names, 1) if name == "g"]
    return CorrelatorConfig(
        color_correlations=tuple(
            ColorCorrelator.dipole(f"T{i}{j}", i, j)
            for i in coloured
            for j in coloured
            if i != j
        ),
        spin_correlations=tuple((leg,) for leg in gluons),
    )


def _points(count: int, seeds=(9001, 9002)):
    return [
        (
            (500.0, 0.0, 0.0, 500.0),
            (500.0, 0.0, 0.0, -500.0),
            *(
                tuple(momentum)
                for momentum in massive_rambo_final_state(
                    count - 2, sqrt_s=1000.0, masses=[0.0] * (count - 2), seed=seed
                )
            ),
        )
        for seed in seeds
    ]


def _transverse(momentum):
    """Two real transverse polarisation vectors of a massless momentum."""

    _, x, y, z = (Decimal(repr(float(value))) for value in momentum)
    with localcontext() as context:
        context.prec = 50
        norm = (x * x + y * y + z * z).sqrt()
        n = (x / norm, y / norm, z / norm)
        planar = (n[0] * n[0] + n[1] * n[1]).sqrt()
        first = (Decimal(0), n[0] * n[2] / planar, n[1] * n[2] / planar, -planar)
        second = (Decimal(0), -n[1] / planar, n[0] / planar, Decimal(0))
        return first, second


@pytest.fixture(scope="module")
def ufo_sm(madgraph_source: Path, tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("correlated-zero-groups-sm")
    bundle = root / "sm.pyamplicol-model"
    ModelSource.from_path(madgraph_source / "models/sm", restriction="default").compile(
        cache_dir=root / "cache", prepared_output=bundle, evaluator=EvaluatorConfig()
    )
    return ModelSource.from_path(bundle)


def _generate(model, process, limits, accuracy, path, **kwargs):
    Generator(_configuration(accuracy, limits)).generate(
        process, path, model=model, correlators=_declarations(process), **kwargs
    )
    return Runtime.load(path)


@pytest.mark.parametrize("accuracy", ("lc", "nlc", "full"))
@pytest.mark.parametrize(("process", "limits", "reference"), CASES, ids=IDS)
@pytest.mark.parametrize("model_name", ("builtin", "ufo"))
def test_helicity_dependent_zeros_build_and_match_independent_references(
    request, tmp_path, model_name, process, limits, reference, accuracy
):
    pytest.importorskip("pyamplicol._rusticol")
    model = (
        ModelSource.built_in_sm()
        if model_name == "builtin"
        else request.getfixturevalue("ufo_sm")
    )
    if limits is DEFAULT and model_name == "ufo":
        limits = ALL_ORDERS
    runtime = _generate(model, process, limits, accuracy, tmp_path / "correlated")
    payload = json.loads((tmp_path / "correlated/correlators.json").read_text())
    manifest = json.loads((tmp_path / "correlated/artifact.json").read_text())
    assert payload["schema_version"] == 2
    assert manifest["extensions"]["correlators"]["schema_version"] == 2
    (record,) = payload["processes"].values()
    zeros = record["zero_coherent_groups"]
    present = {
        (tuple(group["helicities"]), group["color_sector_id"])
        for group in record["coherent_groups"]
    }
    assert zeros and not present & {
        (tuple(item["helicities"]), item["color_sector_id"]) for item in zeros
    }
    # Independent uncorrelated generations: the compiled lane (with its
    # physical-helicity reductions, at 32 digits) and the eager lane (binary64).
    references = {}
    for lane in ("compiled", "eager"):
        Generator(_configuration(accuracy, limits, lane)).generate(
            process, tmp_path / lane, model=model
        )
        references[lane] = Runtime.load(tmp_path / lane)
    points = _points(_legs(process))
    declarations = _declarations(process)
    requests = {"born": CorrelatedRequest("born", {})}
    requests.update(
        {
            item.id: CorrelatedRequest(item.id, {})
            for item in declarations.color_correlations
        }
    )
    values = runtime.evaluate_correlated_many(points, requests, precision=32)
    ordinary = references["compiled"].evaluate(points, precision=32)
    eager = references["eager"].evaluate(points)
    names = process.replace(">", " ").split()
    coloured = [leg for leg, name in enumerate(names, 1) if name != "a"]
    with localcontext() as context:
        context.prec = 40
        for point, expected in enumerate(ordinary):
            born = values["born"][point]
            assert born.real > 0
            assert abs(born.real / Decimal(expected) - 1) < Decimal("1e-26")
            assert float(born.real) == pytest.approx(
                complex(eager[point]).real, rel=1e-12
            )
            assert abs(born.imag / born.real) < Decimal("1e-26")
            if accuracy != "full":
                continue
            # Colour conservation, exactly, for every coloured leg.
            for leg in coloured:
                total = sum(
                    values[f"T{leg}{other}"][point].real
                    for other in coloured
                    if other != leg
                )
                assert abs(total / born.real + _casimir(names[leg - 1])) < Decimal(
                    "1e-26"
                )
    if accuracy == "full" and reference is not None and model_name == "ufo":
        (entry,) = (
            item
            for item in json.loads(REFERENCE.read_text())["processes"]
            if item["process"] == reference
        )
        columns = [
            index
            for index, order in enumerate(entry["squared_orders"])
            if limits["QCD"] != 0 or order.get("QCD", 0) == 0
        ]
        mg_points = [tuple(tuple(p) for p in point) for point in entry["points"]]
        born = runtime.evaluate_correlated(mg_points, precision=32)
        for point, value in enumerate(born):
            expected = sum(entry["partials"][point][column] for column in columns)
            assert float(value.real) == pytest.approx(expected, rel=1e-10, abs=0.0)


def test_spin_correlations_of_a_gluon_with_helicity_dependent_zeros(tmp_path):
    """u u~ > d d~ g at QCD = 1: the gluon's two transverse polarisations sum
    to the Born and to each colour correlation, and its momentum gives zero
    (Ward identity), with the W pairing present for left-handed lines only."""

    pytest.importorskip("pyamplicol._rusticol")
    process = "u u~ > d d~ g"
    runtime = _generate(
        ModelSource.built_in_sm(),
        process,
        {"QCD": 1, "QED": 99},
        "full",
        tmp_path / "correlated",
    )
    payload = json.loads((tmp_path / "correlated/correlators.json").read_text())
    assert payload["processes"][next(iter(payload["processes"]))][
        "zero_coherent_groups"
    ]
    # Exactly lightlike points (float momenta are lightlike only to binary64
    # rounding, which the gauge terms of a polarisation sum would show).
    beams = ((900, 0, 0, 900), (900, 0, 0, -900))
    points = [
        (*beams, (500, 400, 300, 0), (500, 400, -300, 0), (800, -800, 0, 0)),
        (*beams, (500, 0, -400, 300), (500, 0, -400, -300), (800, 0, 800, 0)),
    ]
    polarisations = [
        ((0, 0, 1, 0), (0, 0, 0, 1)),
        ((0, 1, 0, 0), (0, 0, 0, 1)),
    ]
    requests = {
        "born": CorrelatedRequest("born", {}),
        "T51": CorrelatedRequest("T51", {}),
        "ward": CorrelatedRequest("born", {5: [point[4] for point in points]}),
        "ward-T51": CorrelatedRequest("T51", {5: [point[4] for point in points]}),
    }
    for index in range(2):
        vectors = [basis[index] for basis in polarisations]
        requests[f"pol{index}"] = CorrelatedRequest("born", {5: vectors})
        requests[f"pol{index}-T51"] = CorrelatedRequest("T51", {5: vectors})
    values = runtime.evaluate_correlated_many(points, requests, precision=32)
    with localcontext() as context:
        context.prec = 40
        for point in range(len(points)):
            born = values["born"][point].real
            for suffix, total in (("", born), ("-T51", values["T51"][point].real)):
                parts = sum(
                    values[f"pol{index}{suffix}"][point].real for index in (0, 1)
                )
                assert abs((parts - total) / born) < Decimal("1e-26")
            scale = born * Decimal(800) ** 2
            for label in ("ward", "ward-T51"):
                assert abs(values[label][point].real / scale) < Decimal("1e-26")
                assert abs(values[label][point].imag / scale) < Decimal("1e-26")


@pytest.mark.parametrize(
    ("accuracy", "graded", "leading"),
    (("strict-lc", False, "lc"), ("strict-nlc", False, "nlc"), ("full", True, "full")),
)
def test_graded_colour_with_zero_groups(tmp_path, accuracy, graded, leading):
    """Strict and graded colour: each correlation's N_c degrees sum to its
    total, and the Born equals the Born of the corresponding ungraded
    accuracy (the strict correlations themselves are a different truncation)."""

    pytest.importorskip("pyamplicol._rusticol")
    process = "u u~ > d d~"
    config = _configuration("full", QCD_ZERO)
    config = RunConfig(
        action=config.action,
        model=config.model,
        color=ColorConfig(accuracy=accuracy, graded=True)
        if graded
        else ColorConfig(accuracy=accuracy),
        process=config.process,
        generation=config.generation,
        evaluator=config.evaluator,
    )
    Generator(config).generate(
        process,
        tmp_path / "graded",
        model=ModelSource.built_in_sm(),
        correlators=_declarations(process),
    )
    runtime = Runtime.load(tmp_path / "graded")
    assert _zero_set(tmp_path / "graded")
    reference = _generate(
        ModelSource.built_in_sm(), process, QCD_ZERO, leading, tmp_path / "plain"
    )
    points = _points(4)
    with localcontext() as context:
        context.prec = 40
        for identifier in ("born", "T13", "T24"):
            graded_values = runtime.evaluate_correlated_graded(
                points, color_correlation=identifier, precision=32
            )
            totals = runtime.evaluate_correlated(
                points, color_correlation=identifier, precision=32
            )
            expected = reference.evaluate_correlated(
                points, color_correlation=identifier, precision=32
            )
            for point in range(len(points)):
                total = totals[point].real
                parts = sum(value.real for value in graded_values.values[point])
                assert abs((parts - total) / total) < Decimal("1e-26")
                if identifier == "born":
                    assert abs(total / expected[point].real - 1) < Decimal("1e-26")


def test_processes_without_zero_groups_keep_correlator_schema_one(tmp_path):
    """A process whose colour sectors exist at every retained helicity writes
    the payload exactly as before: schema 1, no zero-group record."""

    pytest.importorskip("pyamplicol._rusticol")
    for process, limits in (("u u~ > d d~", DEFAULT), ("d d~ > u u~ g", DEFAULT)):
        path = tmp_path / process.replace(" ", "_").replace(">", "to")
        _generate(ModelSource.built_in_sm(), process, limits, "full", path)
        payload = json.loads((path / "correlators.json").read_text())
        manifest = json.loads((path / "artifact.json").read_text())
        assert payload["schema_version"] == 1
        assert manifest["extensions"]["correlators"]["schema_version"] == 1
        assert all(
            "zero_coherent_groups" not in record
            for record in payload["processes"].values()
        )


def _rewrite_payload(source: Path, destination: Path, edit, version=None) -> None:
    """Copy an artifact with an edited correlator payload under a re-signed
    manifest (optionally another correlator extension version)."""

    import shutil

    from pyamplicol.artifacts import ArtifactBuilder, load_manifest

    shutil.copytree(source, destination)
    manifest = load_manifest(destination)
    (record,) = (item for item in manifest.payloads if item.path == "correlators.json")
    extensions = dict(manifest.extensions)
    if version is not None:
        extensions["correlators"] = {
            **extensions["correlators"],
            "schema_version": version,
        }
    with ArtifactBuilder(destination, mode="append") as builder:
        payload = json.loads((destination / "correlators.json").read_text())
        edit(payload)
        builder.discard_payloads("correlators.json")
        builder.add_json(
            "correlators.json",
            payload,
            role=record.role,
            process_id=record.process_id,
        )
        builder.finalize(
            kind=manifest.kind,
            producer=manifest.producer,
            model=manifest.model,
            configuration=manifest.configuration,
            processes=manifest.processes,
            runtime=manifest.runtime,
            dependencies=manifest.dependencies,
            default_process_id=manifest.default_process_id,
            extensions=extensions,
        )


def test_readers_refuse_an_undeclared_or_misdeclared_gap(tmp_path):
    """The reader takes only a listed group as zero: a gap that is not
    listed, a listed group that has amplitudes, and zero groups under
    correlator schema 1 (what a released reader would read without them) are
    refused."""

    pytest.importorskip("pyamplicol._rusticol")
    path = tmp_path / "correlated"
    _generate(ModelSource.built_in_sm(), "u u~ > d d~", QCD_ZERO, "full", path)
    point = _points(4)[:1]
    baseline = Runtime.load(path).evaluate_correlated(point, precision=32)

    def drop_one(payload):
        for record in payload["processes"].values():
            record["zero_coherent_groups"].pop()

    def drop_all(payload):
        for record in payload["processes"].values():
            del record["zero_coherent_groups"]
        payload["schema_version"] = 1

    def schema_one(payload):
        payload["schema_version"] = 1

    def name_a_live_group(payload):
        for record in payload["processes"].values():
            group = record["coherent_groups"][0]
            record["zero_coherent_groups"].append(
                {
                    "helicities": group["helicities"],
                    "color_sector_id": group["color_sector_id"],
                }
            )

    for edit, version in (
        (drop_one, None),
        (drop_all, 1),
        (schema_one, 1),
        (name_a_live_group, None),
    ):
        copy = tmp_path / edit.__name__
        _rewrite_payload(path, copy, edit, version)
        with pytest.raises(ArtifactError, match="correla"):
            Runtime.load(copy).evaluate_correlated(point, precision=32)
    assert Runtime.load(path).evaluate_correlated(point, precision=32) == baseline


def test_the_zero_groups_are_guarded_against_a_reviving_binding(tmp_path):
    """The zero groups are the W vertex's chirality selection at generation:
    its right-handed coupling component, zero at the card values, is a
    runtime parameter whose zero decided the chiralities the vertex passes.
    The artifact records it as a specialisation guard, so a binding that would
    revive the right-handed W (and the dropped amplitudes) is refused, leaving
    the runtime and its correlations unchanged."""

    pytest.importorskip("pyamplicol._rusticol")
    path = tmp_path / "correlated"
    runtime = _generate(
        ModelSource.built_in_sm(), "u u~ > d d~", QCD_ZERO, "full", path
    )
    guards = json.loads((path / "model/specialization-guards.json").read_text())
    names = sorted(
        name
        for guard in guards["guards"]
        if guard["kind"] == "vanishing" and "chiralities" in guard["subject"]
        for name in guard["parameters"]
    )
    assert names
    point = _points(4)
    before = runtime.evaluate_correlated_many(
        point,
        {"born": CorrelatedRequest("born", {}), "T13": CorrelatedRequest("T13", {})},
        precision=32,
    )
    for name in names:
        with pytest.raises(EvaluationError, match="specialisation-guard"):
            runtime.set_model_parameters({name: 0.5})
        with pytest.raises(EvaluationError, match="specialisation-guard"):
            Runtime.load(path, model_parameters={name: 0.5})
    after = runtime.evaluate_correlated_many(
        point,
        {"born": CorrelatedRequest("born", {}), "T13": CorrelatedRequest("T13", {})},
        precision=32,
    )
    assert after == before


@pytest.fixture(scope="module")
def zero_group_sdk_output(tmp_path_factory: pytest.TempPathFactory):
    """Two processes with certified zero groups, with the Python reader's
    values as the oracle of the native SDKs."""

    pytest.importorskip("pyamplicol._rusticol")
    root = tmp_path_factory.mktemp("correlated-zero-groups-sdk")
    cases = {}
    for name, process, limits in (
        ("uuddg", "u u~ > d d~ g", {"QCD": 1, "QED": 99}),
        ("ucdsdd", "u c~ > d s~ d d~", DEFAULT),
    ):
        declarations = _declarations(process)
        Generator(_configuration("full", limits)).generate(
            ProcessSet.from_expressions((process,), names=(name,)),
            root / name,
            model=ModelSource.built_in_sm(),
            correlators=declarations,
        )
        payload = json.loads((root / name / "correlators.json").read_text())
        assert payload["schema_version"] == 2
        points = _points(_legs(process))
        requests = {"born": CorrelatedRequest("born", {})}
        requests.update(
            {
                item.id: CorrelatedRequest(item.id, {})
                for item in declarations.color_correlations
            }
        )
        if declarations.spin_correlations:
            polarisations = [_transverse(point[4]) for point in points]
            for index in range(2):
                vectors = tuple(
                    tuple(float(component) for component in basis[index])
                    for basis in polarisations
                )
                # (float vectors: the SDKs read binary64)
                requests[f"pol{index}"] = CorrelatedRequest("born", {5: vectors})
                requests[f"pol{index}-T51"] = CorrelatedRequest("T51", {5: vectors})
        runtime = Runtime.load(root / name, process=name)
        oracle = runtime.evaluate_correlated_many(points, requests, precision=45)
        cases[name] = (root / name, points, requests, oracle)
    return cases


@pytest.mark.parametrize("language", ("c", "cpp", "fortran", "rust"))
def test_native_sdks_serve_certified_zero_groups(
    language, native_sdk, zero_group_sdk_output, tmp_path
):
    binary = _compile_probe(language, _PHYSICS_PROBES[language], native_sdk, tmp_path)
    for name, (artifact, points, requests, oracle) in zero_group_sdk_output.items():
        input_path = tmp_path / f"{name}.txt"
        _write_physics_input(input_path, points, requests)
        run = subprocess.run(
            [str(binary), str(artifact), name, str(input_path)],
            capture_output=True,
            text=True,
            env=_source_environment(),
            timeout=120,
        )
        assert run.returncode == 0, run.stdout + run.stderr
        labels = tuple(requests)
        measured = {}
        for line in run.stdout.splitlines():
            if line.startswith("VALUE "):
                _, request, point, real, imag = line.split()
                measured[labels[int(request)], int(point)] = complex(
                    float(real), float(imag)
                )
        assert set(measured) == {(label, p) for label in labels for p in range(2)}
        for point in range(2):
            born = measured["born", point]
            assert born.real > 0 and math.isfinite(born.real)
            for label in labels:
                assert measured[label, point] == pytest.approx(
                    complex(oracle[label][point]), rel=2e-10, abs=abs(born) * 1e-12
                )


def _right_handed_w_model(root: Path, madgraph_source: Path, mt: int) -> Path:
    """The UFO sm whose u-d W vertices also have a right-handed coupling
    proportional to MT - 173, with MT set to ``mt`` on the default card."""

    import re
    import shutil

    model = root / f"sm-right-w-mt{mt}"
    shutil.copytree(
        madgraph_source / "models/sm",
        model,
        ignore=shutil.ignore_patterns("__pycache__", "*.pkl"),
    )
    lorentz = model / "lorentz.py"
    lorentz.write_text(
        lorentz.read_text(encoding="utf-8") + "\nFFVR = Lorentz(name = 'FFVR',\n"
        "               spins = [ 2, 2, 3 ],\n"
        "               structure = 'Gamma(3,2,-1)*ProjP(-1,1)')\n",
        encoding="utf-8",
    )
    couplings = model / "couplings.py"
    text = couplings.read_text(encoding="utf-8")
    for name in ("41", "100"):
        value = re.search(
            rf"GC_{name} = Coupling\(name = 'GC_{name}',\s+value = '([^']+)'", text
        )
        assert value is not None
        text += (
            f"\nGC_R{name} = Coupling(name = 'GC_R{name}',\n"
            f"                 value = '(MT-173)*({value[1]})',\n"
            "                 order = {'QED':1})\n"
        )
    couplings.write_text(text, encoding="utf-8")
    vertices = model / "vertices.py"
    text = vertices.read_text(encoding="utf-8")
    for name in ("41", "100"):
        text, count = re.subn(
            rf"lorentz = \[ L\.FFV2 \],(\s+)couplings = \{{\(0,0\):C\.GC_{name}\}}",
            rf"lorentz = [ L.FFV2, L.FFVR ],\g<1>couplings = "
            rf"{{(0,0):C.GC_{name},(0,1):C.GC_R{name}}}",
            text,
        )
        assert count == 1
    vertices.write_text(text, encoding="utf-8")
    card = model / "restrict_default.dat"
    text = card.read_text(encoding="utf-8")
    assert "1.730000e+02 # MT " in text
    card.write_text(text.replace("1.730000e+02 # MT ", f"{mt}.0 # MT "))
    return model


def _zero_set(path: Path) -> set[tuple[tuple[int, ...], int]]:
    payload = json.loads((path / "correlators.json").read_text())
    return {
        (tuple(item["helicities"]), item["color_sector_id"])
        for record in payload["processes"].values()
        for item in record.get("zero_coherent_groups", ())
    }


def _present_set(path: Path) -> set[tuple[tuple[int, ...], int]]:
    payload = json.loads((path / "correlators.json").read_text())
    return {
        (tuple(item["helicities"]), item["color_sector_id"])
        for record in payload["processes"].values()
        for item in record["coherent_groups"]
    }


def test_a_binding_that_revives_a_zero_group_is_refused(
    madgraph_source: Path, tmp_path: Path
):
    """A right-handed W coupling proportional to MT - 173 vanishes at
    MT = 173, where the restriction removes it: the W pairing of
    u u~ > d d~ at QCD = 0 then exists for left-handed lines only, and its
    right-handed (helicity, sector) amplitudes are certified zero groups
    (besides those helicity conservation gives at every MT).
    The removal is a specialisation guard on MT, so a binding of MT is
    refused (at load and through set_model_parameters) instead of returning
    those zeros where the artifact generated at MT = 174 has amplitudes.
    Unsimplified, the coupling is kept, only the structural zeros are
    certified, and the artifact bound to MT = 174 equals the one generated
    there."""

    pytest.importorskip("pyamplicol._rusticol")
    process = "u u~ > d d~"
    points = _points(4)
    requests = {
        "born": CorrelatedRequest("born", {}),
        "T13": CorrelatedRequest("T13", {}),
        "T14": CorrelatedRequest("T14", {}),
    }
    runtimes = {}
    zeros = {}
    present = {}
    for mt in (173, 174):
        source = _right_handed_w_model(tmp_path, madgraph_source, mt)
        bundle = tmp_path / f"sm-{mt}.pyamplicol-model"
        ModelSource.from_path(source, restriction="default").compile(
            cache_dir=tmp_path / "cache",
            prepared_output=bundle,
            evaluator=EvaluatorConfig(),
        )
        path = tmp_path / f"at-{mt}"
        runtimes[mt] = _generate(
            ModelSource.from_path(bundle), process, QCD_ZERO, "full", path
        )
        zeros[mt] = _zero_set(path)
        present[mt] = _present_set(path)
    # Helicity conservation alone leaves one pairing at some helicities (zero
    # groups at both MT). At MT = 173 the right-handed W amplitudes are absent:
    # certified zero groups, or helicities without any amplitude.
    assert zeros[174] and present[173] < present[174]
    retained = {helicities for helicities, _ in present[173]}
    for helicities, sector in present[174] - present[173]:
        assert (helicities, sector) in zeros[173] or helicities not in retained
    assert zeros[173] - zeros[174]
    at_173 = runtimes[173].evaluate_correlated_many(points, requests, precision=32)
    at_174 = runtimes[174].evaluate_correlated_many(points, requests, precision=32)
    assert float(at_173["born"][0].real) != pytest.approx(
        float(at_174["born"][0].real), rel=1e-6
    )
    refusal = "specialisation-guard: binding MT"
    with pytest.raises(EvaluationError, match=refusal):
        runtimes[173].set_model_parameters({"MT": 174.0})
    with pytest.raises(EvaluationError, match=refusal):
        Runtime.load(tmp_path / "at-173", model_parameters={"MT": 174.0})
    assert (
        runtimes[173].evaluate_correlated_many(points, requests, precision=32) == at_173
    )
    unsimplified = _generate(
        ModelSource.from_path(
            _right_handed_w_model(tmp_path / "plain", madgraph_source, 173),
            restriction="default",
            simplify=False,
        ),
        process,
        QCD_ZERO,
        "full",
        tmp_path / "unsimplified",
    )
    # The coupling is kept (merely zero at MT = 173): only the structural
    # zeros of MT = 174 are certified.
    assert _zero_set(tmp_path / "unsimplified") == zeros[174]
    unsimplified.set_model_parameters({"MT": 174.0})
    bound = unsimplified.evaluate_correlated_many(points, requests, precision=32)
    with localcontext() as context:
        context.prec = 40
        for label in requests:
            for point in range(len(points)):
                expected = at_174[label][point].real
                assert abs(bound[label][point].real / expected - 1) < Decimal("1e-20")
