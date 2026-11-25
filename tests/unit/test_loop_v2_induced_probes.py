# SPDX-License-Identifier: 0BSD
"""The loop-induced generation-time probes as an opt-in (m-lit Q12 as ruled
on 2026-11-08 22:34 (3), package lit-probe).

* **Default off**: a loop-induced generation reaches none of the probes'
  stages (``induced.generation_probes``, ``ward.ward_slice``,
  ``goldstone.goldstone_slice``, ``induced._goldstone_probes``); the
  helicity-zero filter's binary64 pre-screen still runs through
  ``induced.probe_point`` / ``_probe_runs`` / ``physical_floors`` (m-lit
  Q10, it changes the artifact), and only from ``helicity_filter``; the
  record reads ``{"status": "off"}``; the stored plan, the filter record,
  its dropped rows and the binary64 values equal those of the opt-in
  artifact bitwise (g g > h: counterterm kets, no screening; g g > h z:
  screened).
* **Opt-in** ``generation.loop_induced_probes`` in the run config, the CLI
  and the Python config object; any other value refused with one message.
  Every probe runs first in binary64; only a probe binary64 does not pass
  (R < K S, ``checks.threshold``) or refuses runs again in double-double (a
  test seam forces either); a probe that fails after the fallback refuses
  the process unless ``generation.allow_failed_probes``, which stores it
  with the failure; a probe refused in every carrier is recorded
  inconclusive (never a pass) and generation continues.
* **A real gauge check**: g g > a a (massless quarks, nf5) generated from a
  test-only copy of the shipped loop_sm without the R2 vertex whose legs are
  the row's external particles (selected by PDG codes from the model's own
  files): the finite part changes far beyond its estimate, the finiteness
  probe still passes (R2 is finite), the binary64 Ward probe fails (R / S
  70 times K),
  the double-double fallback fails too (a defect, not rounding), and the
  public generation refuses (``loop-induced-probe``) unless allowed; the
  unmodified copy passes in binary64 with no fallback.
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from .loop_r2_dropped import declaration as _declaration
from .loop_r2_dropped import drop_r2_vertex as _drop_r2_vertex

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "loop" / "required" / "li"
FILTER = "pyamplicol.loops.v2.helicity_filter"
# The one message of an invalid value (card, CLI and Python config).
MESSAGE = r"^generation\.loop_induced_probes must be true or false$"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _card(output: Path, expression: str, fixture: dict, source: str = "loop_sm") -> str:
    fixed = ", ".join(
        f"{key} = {json.dumps(value)}"
        for key, value in fixture["scheme_data"]["fixed_parameters"].items()
    )
    return f"""
action = "generate"
[model]
source = {json.dumps(source)}
restriction = "no_b_mass"
[process]
entries = [{{expression = {json.dumps(expression)}, name = "p"}}]
loop_coupling_orders = ["QCD"]
[loop]
r2_strategy = "model"
{_declaration(source)}[loop.preparation]
fixed_parameters = {{{fixed}}}
[generation]
output = {json.dumps(str(output))}
emit_api_bundle = false
[generation.validation]
post_build_validation = false
"""


def _config(root: Path, expression: str, fixture: dict, **generation):
    """The run config of a one-process loop-induced card, with generation
    settings set on the Python config object (``generation``)."""

    from pyamplicol.config import resolve_config

    root.mkdir(parents=True, exist_ok=True)
    card = root / "card.toml"
    source = generation.pop("source", "loop_sm")
    card.write_text(_card(root / "artifact", expression, fixture, source))
    config = resolve_config(card).effective
    if generation:
        config = replace(config, generation=replace(config.generation, **generation))
    return config


def _generate(config, expression: str) -> Path:
    from pyamplicol.api import Generator, ProcessRequest, ProcessSet

    output = Path(config.generation.output)
    Generator(config).generate(
        ProcessSet((ProcessRequest.parse(expression, name="p"),)), output
    )
    return output


def _filters(artifact: Path) -> dict:
    manifest = json.loads((artifact / "artifact.json").read_text())
    (filters,) = (
        record["filters"]
        for record in manifest["extensions"]["generation"]["concrete_processes"]
        if record["id"] == "p"
    )
    return filters


def _values(artifact: Path, fixture: dict, count: int = 2) -> list:
    """The binary64 values at the fixture's first points, as bit patterns."""

    from pyamplicol import Runtime

    runtime = Runtime.load(artifact, process="p")
    out = []
    for point, mu in list(zip(fixture["points"], fixture["mu_r"], strict=True))[:count]:
        value = runtime.evaluate([point], mu_r2=[str(Fraction(mu) ** 2)])
        out.append([[float(x).hex() for x in laurent] for laurent in value.values[0]])
    return out


# ------------------------------------------------------------------ option


@pytest.mark.loop_fast
def test_the_option_is_off_by_default_and_set_in_config_cli_and_python(tmp_path):
    """``generation.loop_induced_probes``: off by default; enabled by the run
    config (TOML), the CLI (``--loop-induced-probes``, ``--no-...``) and the
    Python config object; any non-boolean value is refused with the one
    message; ``allow_failed_probes`` stays its own setting."""

    from pyamplicol.cli import parse_cli
    from pyamplicol.config import ConfigurationError, GenerationConfig, resolve_config

    fixture = _fixture("li_gg_h")
    default = _config(tmp_path / "default", "g g > h", fixture)
    assert default.generation.loop_induced_probes is False
    card = tmp_path / "on.toml"
    card.write_text(
        _card(tmp_path / "out", "g g > h", fixture).replace(
            "[generation]\n", "[generation]\nloop_induced_probes = true\n"
        )
    )
    assert resolve_config(card).effective.generation.loop_induced_probes is True
    bad = tmp_path / "bad.toml"
    bad.write_text(card.read_text().replace("= true", '= "yes"'))
    with pytest.raises(ConfigurationError, match=MESSAGE):
        resolve_config(bad)
    cli = parse_cli(("generate",)).resolve().effective.generation
    assert cli.loop_induced_probes is False
    on = parse_cli(("generate", "--loop-induced-probes")).resolve().effective
    assert on.generation.loop_induced_probes is True
    off = parse_cli(("generate", "--no-loop-induced-probes")).resolve().effective
    assert off.generation.loop_induced_probes is False
    assert not on.generation.allow_failed_probes
    python = GenerationConfig(loop_induced_probes=True, allow_failed_probes=True)
    assert python.loop_induced_probes and python.allow_failed_probes
    with pytest.raises(ConfigurationError, match=MESSAGE):
        GenerationConfig(loop_induced_probes="true")


# ------------------------------------------------------------ default off


def _caller_modules() -> set[str]:
    frame = sys._getframe(2)
    modules = set()
    while frame is not None:
        modules.add(frame.f_globals.get("__name__", ""))
        frame = frame.f_back
    return modules


@pytest.mark.loop_physics
@pytest.mark.parametrize(
    ("expression", "name", "screened"),
    [("g g > h", "li_gg_h", False), ("g g > h z", "li_gg_hz", True)],
    ids=["gg_h-kets", "gg_hz-screened"],
)
def test_default_generation_runs_no_probe_and_equals_the_opt_in_artifact(
    tmp_path, monkeypatch, expression, name, screened
):
    """DECISIONS 2026-11-08 22:34 (3): the default generation of a
    loop-induced process calls none of the probes' stages and records them
    as not run; the helicity-zero filter's binary64 pre-screen (Q10) runs
    the shared probe machinery only from ``helicity_filter`` (g g > h has
    counterterm kets: nothing is screened); the stored plan, the filter
    record (less its timings), the dropped rows and the binary64 values at
    two points are bitwise those of the opt-in generation, whose probes
    pass in binary64 alone."""

    from pyamplicol.loops.v2 import goldstone, induced, ward

    fixture = _fixture(name)

    def refused(*args, **kwargs):
        raise AssertionError("a probe stage ran in a default generation")

    calls: list[str] = []

    def screened_only(function):
        def wrapper(*args, **kwargs):
            assert FILTER in _caller_modules(), function.__name__
            calls.append(function.__name__)
            return function(*args, **kwargs)

        return wrapper

    with monkeypatch.context() as patch:
        patch.setattr(induced, "generation_probes", refused)
        patch.setattr(induced, "_goldstone_probes", refused)
        patch.setattr(ward, "ward_slice", refused)
        patch.setattr(goldstone, "goldstone_slice", refused)
        for function in ("probe_point", "_probe_runs", "physical_floors"):
            patch.setattr(induced, function, screened_only(getattr(induced, function)))
        default = _generate(
            _config(tmp_path / "default", expression, fixture), expression
        )
    assert bool(calls) is screened
    on = _generate(
        _config(tmp_path / "on", expression, fixture, loop_induced_probes=True),
        expression,
    )
    off_filters, on_filters = _filters(default), _filters(on)
    assert off_filters["loop_induced_probes"] == {"status": "off"}
    probes = on_filters["loop_induced_probes"]
    assert probes["status"] == "run" and "failed" not in probes
    # g g > h keeps the helicity rows that vanish by angular momentum (no
    # screening: counterterm kets): their physical reference is an exact
    # computed zero from cancelling terms, which double-double settles (the
    # finiteness probe's one fallback).
    zero_rows = not screened
    assert probes["fallbacks"] == int(zero_rows) and probes["finiteness"]["passed"]
    assert probes["ward"]["passed"] and probes["ward"]["legs"] == [1]
    assert probes["finiteness"]["carrier"] == (
        "double-double" if zero_rows else "double"
    )
    assert probes["reduction"] == {
        "requested": "ninjars",
        "effective": "ninjars",
        "reason": induced.PROBE_REDUCTION_REASON,
    }
    helicity = {
        key: value
        for key, value in off_filters["loop_induced_helicity_filter"].items()
        if key != "seconds"
    }
    assert helicity == {
        key: value
        for key, value in on_filters["loop_induced_helicity_filter"].items()
        if key != "seconds"
    }
    assert (helicity["counterterms"] == "absent") is screened
    plan = Path("processes") / "p" / "loop-runtime.pacbin"
    assert (default / plan).read_bytes() == (on / plan).read_bytes()
    assert _values(default, fixture) == _values(on, fixture)


# ---------------------------------------------------- binary64 + fallback


@pytest.fixture(scope="module")
def gg_h(tmp_path_factory):
    """g g > h on the shipped loop_sm (no_b_mass, zero widths): compiled
    model, native, slice and candidate points (generated once)."""

    from pyamplicol.loops.native import load_loop_native
    from pyamplicol.loops.v2.assemble import LoopSlice, SliceRequest
    from pyamplicol.models.loading import compile_model_source

    fixture = _fixture("li_gg_h")
    compiled = compile_model_source(
        "loop_sm",
        restriction="no_b_mass",
        cache_dir=tmp_path_factory.mktemp("probes-gg-h") / "model-cache",
    )
    native = load_loop_native()
    orders = dict(fixture["loop_orders"])
    fixed = {
        key: value
        for key, value in fixture["scheme_data"]["fixed_parameters"].items()
        if key in compiled.parameter_defaults
    }
    slice_ = LoopSlice.generate(
        compiled,
        SliceRequest(
            "g g > h",
            orders,
            orders,
            contribution="loop-induced",
            fixed_parameters=fixed,
        ),
        native,
    )
    candidates = [[[float(x) for x in p] for p in point] for point in fixture["points"]]
    return SimpleNamespace(
        compiled=compiled, native=native, slice=slice_, candidates=candidates
    )


def _seam(monkeypatch, force):
    """Wrap ``induced.probe_results``: ``force(carrier, ward, result)``
    returns the result the generation-time probes see (a refusal text or a
    ``ProbeResult``); every pass is recorded as (carrier, probe kinds)."""

    from pyamplicol.loops.v2 import induced

    original = induced.probe_results
    passes: list[tuple[str, list[str]]] = []

    def wrapper(executor, point, scale, wards, **kwargs):
        found = original(executor, point, scale, wards, **kwargs)
        carrier = kwargs["precision"].arithmetic
        passes.append((carrier, ["finiteness" if w is None else "ward" for w in wards]))
        return [
            force(carrier, ward, result)
            for ward, result in zip(wards, found, strict=True)
        ]

    monkeypatch.setattr(induced, "probe_results", wrapper)
    return passes


@pytest.mark.loop_physics
def test_only_the_probe_refused_in_binary64_runs_in_double_double(gg_h, monkeypatch):
    """A Ward run the backend refuses in binary64 (a test seam) is re-run in
    double-double on the same lifted point, and only it: the finiteness probe
    keeps its binary64 verdict; the record names the deciding carriers and
    the refusal."""

    from pyamplicol.loops.v2 import induced

    def force(carrier, ward, result):
        if carrier == "double" and ward is not None:
            return "the probe point failed: forced refusal (test seam)"
        return result

    passes = _seam(monkeypatch, force)
    record = induced.generation_probes(
        gg_h.slice, gg_h.compiled, gg_h.native, gg_h.candidates
    )
    # The finiteness probe's rows that vanish by angular momentum (an exact
    # computed zero P) are settled in double-double too, with the Ward probe.
    assert passes == [
        ("double", ["finiteness", "ward"]),
        ("double-double", ["finiteness", "ward"]),
    ]
    assert record["finiteness"] == {
        "worst": record["finiteness"]["worst"],
        "passed": True,
        "verdict": "pass",
        "carrier": "double-double",
    }
    assert record["ward"]["passed"] and record["ward"]["carriers"] == {
        "1": "double-double"
    }
    finiteness, ward = record["probes"]
    assert finiteness["fallback"]["verdict"] == "inconclusive"
    assert ward["fallback"] == {
        "carrier": "double",
        "reason": "refused",
        "detail": "the probe point failed: forced refusal (test seam)",
    }
    assert record["fallbacks"] == 2 and "failed" not in record
    assert set(record["seconds"]) >= {"double", "double-double", "total"}


@pytest.mark.loop_physics
def test_only_the_probe_failing_in_binary64_runs_in_double_double(gg_h, monkeypatch):
    """A finiteness verdict failed in binary64 (a test seam: R / S 1e3) is
    re-run in double-double, where it passes, which decides it; the Ward
    probe keeps its binary64 verdict."""

    from dataclasses import replace

    from pyamplicol.loops.v2 import checks, induced

    def force(carrier, ward, result):
        if carrier == "double" and ward is None:
            # Every row's residue 1e3 times its physical reference.
            cells = {
                key: checks.judge(
                    replace(cell.measure, residue=1e3 * cell.measure.physical),
                    result.tolerance,
                )
                for key, cell in result.cells.items()
            }
            return replace(result, cells=cells)
        return result

    passes = _seam(monkeypatch, force)
    record = induced.generation_probes(
        gg_h.slice, gg_h.compiled, gg_h.native, gg_h.candidates
    )
    assert passes == [
        ("double", ["finiteness", "ward"]),
        ("double-double", ["finiteness"]),
    ]
    finiteness, ward = record["probes"]
    assert finiteness["carrier"] == "double-double" and finiteness["passed"]
    assert finiteness["fallback"] == {
        "carrier": "double",
        "reason": "verdict",
        "verdict": "fail",
        "worst": 1000.0,
    }
    assert ward["carrier"] == "double" and "fallback" not in ward
    assert record["finiteness"]["carrier"] == "double-double"
    assert record["fallbacks"] == 1 and "failed" not in record


@pytest.mark.loop_physics
def test_a_probe_refused_in_every_carrier_is_recorded_inconclusive(
    gg_h, monkeypatch, caplog
):
    """A probe without R and S in any carrier (refused everywhere) is
    inconclusive, never a pass: recorded with the carrier that last refused
    it and logged as a warning by the generation; generation continues (only
    a decisive failure refuses the process, ``ProbeFailure``)."""

    from pyamplicol.loops.v2 import induced

    def force(carrier, ward, result):
        if ward is not None:
            return f"the probe point failed: forced refusal in {carrier}"
        return result

    _seam(monkeypatch, force)
    record = induced.generation_probes(
        gg_h.slice, gg_h.compiled, gg_h.native, gg_h.candidates
    )
    assert "failed" not in record and "allowed_failure" not in record
    assert not record["ward"]["passed"]
    (ward,) = (entry for entry in record["probes"] if entry["probe"] == "ward")
    assert ward["carrier"] == "double-double" and not ward["passed"]
    assert ward["verdict"] == "inconclusive"
    assert ward["refused"].endswith("forced refusal in double-double")
    assert ward["fallback"]["reason"] == "refused"
    (line,) = record["inconclusive"]
    assert line.startswith("ward probe (leg 1): inconclusive, refused in")
    assert record["finiteness"]["passed"]
    json.dumps(record, allow_nan=False)


@pytest.mark.loop_fast
def test_a_probe_verdict_is_the_threshold_rule():
    """A probe's verdict is its rows' (``checks.judge`` per (loop order,
    row) and Laurent coefficient, then ``checks.aggregate``): R the
    colour-metric residue, P the row's physical finite-amplitude norm at the
    same carrier (with E_P), T its term floor. The required rows are the
    union of the evaluation's and the floors' rows at every coefficient of
    the required width: a row or coefficient one operand lacks, or a
    non-finite residue, is inconclusive, never skipped; a row without any
    term is vacuous; a probe every row of which is vacuous has nothing to
    test. Its failure is the keyed ``loop-induced-probe`` refusal."""

    from pyamplicol.loops.v2 import induced
    from pyamplicol.loops.v2.refusals import LoopEngineRefusal, keyed_error

    typed = keyed_error(induced.ProbeFailure("'g g > a a': ward probe failed"))
    assert isinstance(typed, LoopEngineRefusal) and typed.key == "loop-induced-probe"

    def probe(estimates, floors, references, width=3, first=1):
        measures = induced.probe_measures(estimates, floors, first, references, width)
        return induced.ProbeResult(
            "finiteness", induced.judged_cells(measures, 1e-5), tolerance=1e-5
        )

    references = {"a": (1.0, 1e-14), "b": (1.0, 1e-14), "d": (1.0, 1e-14)}
    floors = {"a": [1e5] * 3, "b": [1.0] * 3, "d": [1.0] * 3}
    estimates = {
        "a": ((1.0, 0.1), (1e-15, 0.1), (0.0, 0.1)),
        "b": ((1.0, 0.1), (float("nan"), 0.1), (0.0, 0.1)),
        "c": ((1.0, 0.1), (1e-15, 0.1), (0.0, 0.1)),
    }
    result = probe(estimates, floors, references)
    assert result.verdict == "inconclusive"
    assert result.ratios == {"a": 1e-15, "b": 0.0}
    # b k=1 (NaN), c k=1, c k=2 (no floor), d k=1, d k=2 (no amplitude row).
    assert len(result.undefined) == 5
    assert any(text.startswith("d k=1") for text in result.undefined)
    # A coefficient the evaluation does not supply (width 3, two given).
    short = probe({"a": ((1.0, 0.1), (1e-15, 0.1))}, {"a": [1.0] * 3}, references)
    assert short.verdict == "inconclusive"
    # A resolved row with T / P 1e7 and a 1e-3 violation fails (the reviewer's
    # case: the term scale never hides a physical miss).
    heavy = probe(
        {"a": ((1.0, 0.1), (1e-3, 0.1))},
        {"a": [1e7, 1e7]},
        {"a": (1.0, 1e-12)},
        width=2,
    )
    assert heavy.verdict == "fail" and heavy.worst == pytest.approx(1e-3)
    # Every row vacuous (no term: the amplitude vanishes identically).
    empty = probe(
        {"z": ((0.0, 0.0), (0.0, 0.0))}, {"z": [0.0, 0.0]}, {"z": (0.0, 0.0)}, width=2
    )
    assert empty.verdict == "vacuous" and empty.passed and empty.vacuous == 1
    assert empty.reason.startswith("nothing to test")


@pytest.mark.loop_fast
def test_a_goldstone_probe_refused_in_binary64_runs_in_double_double(monkeypatch):
    """The Goldstone probe of a species takes the same carriers: refused in
    binary64 (a test seam), it runs in double-double, which decides it; a
    species passing in binary64 runs once; the Goldstone slice's generation
    and each probe are timed in the record."""

    from pyamplicol.loops.v2 import goldstone, induced, plan_export
    from pyamplicol.loops.v2.goldstone import GoldstoneResult

    calls: list[tuple[int, str]] = []

    from pyamplicol.loops.v2.checks import Measure

    def probe(vector, partner, point, scale, leg, *, precision, physical, tolerance):
        calls.append((leg, precision.arithmetic))
        if leg == 3 and precision.arithmetic == "double":
            raise induced.ProbePointRefused("the probe point failed: forced (seam)")
        cells = induced.judged_cells(
            {(("o", "r"), 0): Measure("x", 1e-13, 1.0, 1.0)}, 1e-5, precision
        )
        return GoldstoneResult(leg, cells, None, 0.1, tolerance=1e-5)

    monkeypatch.setattr(
        goldstone, "massive_vector_legs", lambda target: {3: 250, 4: 251}
    )
    monkeypatch.setattr(goldstone, "goldstone_slice", lambda *args, **options: object())
    monkeypatch.setattr(goldstone, "probe", probe)
    monkeypatch.setattr(plan_export, "NativeExecutor", lambda *a, **k: object())
    target = SimpleNamespace(
        compiled=SimpleNamespace(ir=SimpleNamespace(gauge="feynman"))
    )
    found = induced._goldstone_probes(target, None, None, None, None, None, None, {})
    assert calls == [(3, "double"), (3, "double-double"), (4, "double")]
    record = found["record"]
    assert record["passed"] and record["carriers"] == {
        "3": "double-double",
        "4": "double",
    }
    three, four = found["entries"]
    assert three["fallback"] == {
        "carrier": "double",
        "reason": "refused",
        "detail": "the probe point failed: forced (seam)",
    }
    assert "fallback" not in four
    assert set(found["seconds"]["goldstone_slices"]) == {"3", "4"}
    assert set(found["seconds"]["goldstone"]) == {"3", "4"}


# --------------------------------------------------- a dropped R2 vertex


@pytest.mark.loop_physics
def test_the_binary64_ward_probe_catches_a_dropped_r2_vertex(tmp_path):
    """DECISIONS 2026-11-08 22:34 (3): g g > a a (massless quarks, nf5) from a
    copy of the shipped loop_sm without the R2 vertex whose legs are the
    row's external particles (by PDG code), generated through the production
    path (ADDENDUM J: R2 vertices are plain tree-level vertices). The vertex
    contributes (the finite part at the probe point moves far beyond its
    estimate); the finiteness probe still passes in binary64 (R2 is finite);
    the binary64 Ward probe fails by far, and its double-double fallback on
    the same lifted point too (a defect, not rounding); the public
    generation with the option refuses (``loop-induced-probe``) and with
    ``allow_failed_probes`` stores the artifact with the failure recorded.
    The unmodified copy passes in binary64 with no fallback."""

    from importlib import resources

    from pyamplicol.loops.native import load_loop_native
    from pyamplicol.loops.v2 import induced
    from pyamplicol.loops.v2.assemble import LoopSlice, Precision, SliceRequest
    from pyamplicol.loops.v2.plan_export import NativeExecutor
    from pyamplicol.loops.v2.refusals import LoopEngineRefusal
    from pyamplicol.loops.v2.stability import RECOMMENDED_CHECKS
    from pyamplicol.models.loading import compile_model_source

    fixture = _fixture("li_gg_aa_nf5")
    shipped = Path(
        str(resources.files("pyamplicol").joinpath("assets", "models", "ufo"))
    )
    intact, dropped = tmp_path / "loop_sm", tmp_path / "loop_sm_r2_dropped"
    shutil.copytree(shipped / "loop_sm", intact)
    shutil.copytree(shipped / "loop_sm", dropped)
    assert _drop_r2_vertex(dropped, fixture["pdgs"])
    native = load_loop_native()
    orders = dict(fixture["loop_orders"])
    candidates = [[[float(x) for x in p] for p in point] for point in fixture["points"]]
    slices, records = {}, {}
    for label, ufo in (("intact", intact), ("dropped", dropped)):
        compiled = compile_model_source(
            ufo,
            restriction="no_b_mass",
            require_supported=False,
            cache_dir=tmp_path / f"cache-{label}",
        )
        fixed = {
            key: value
            for key, value in fixture["scheme_data"]["fixed_parameters"].items()
            if key in compiled.parameter_defaults
        }
        slices[label] = slice_ = LoopSlice.generate(
            compiled,
            SliceRequest(
                "g g > a a",
                orders,
                orders,
                contribution="loop-induced",
                fixed_parameters=fixed,
                particle_veto=(6,),
            ),
            native,
        )
        records[label] = induced.generation_probes(
            slice_, compiled, native, candidates, allow_failure=True
        )
    intact_record, dropped_record = records["intact"], records["dropped"]
    # The unmodified model: binary64 alone, every probe passes.
    assert "failed" not in intact_record and intact_record["fallbacks"] == 0
    assert {e["carrier"] for e in intact_record["probes"]} == {"double"}
    assert intact_record["ward"]["legs"] == [1, 3]
    # The vertex contributes: the finite part at the probe point moves far
    # beyond the binary64 estimate.
    digits = intact_record["lift_digits"]
    point, _distance = induced.probe_point(
        slices["intact"], candidates[intact_record["candidate"]], digits
    )
    scale = induced._point_scale(point, 2)
    finite, estimate = {}, {}
    for label, slice_ in slices.items():
        executor = NativeExecutor(slice_, forward=False, inputs="native")
        (result,) = executor.evaluate(
            [point],
            [scale],
            precision=Precision.double(),
            stability=RECOMMENDED_CHECKS,
        )
        (sector,) = result.stability.absolute
        finite[label] = float(result.totals[1])
        estimate[label] = result.stability.absolute[sector].coefficients[0]
    moved = abs(finite["dropped"] - finite["intact"])
    assert moved > 1e3 * (estimate["intact"] + estimate["dropped"])
    assert moved > 1e-3 * abs(finite["intact"])
    # The modified model: finiteness passes in binary64; each Ward probe
    # fails by far in binary64 and again in double-double.
    assert dropped_record["finiteness"] == {
        "worst": dropped_record["finiteness"]["worst"],
        "passed": True,
        "verdict": "pass",
        "carrier": "double",
    }
    wards = [e for e in dropped_record["probes"] if e["probe"] == "ward"]
    assert [e["leg"] for e in wards] == [1, 3]
    for entry in wards:
        assert entry["fallback"]["carrier"] == "double"
        assert entry["fallback"]["reason"] == "verdict"
        # R / S 7e-4 at K 1e-5 in both carriers (a defect, not rounding).
        assert entry["fallback"]["worst"] > 10 * dropped_record["tolerance"]
        assert entry["carrier"] == "double-double" and not entry["passed"]
        assert entry["verdict"] == "fail"
        assert entry["worst"] > 10 * dropped_record["tolerance"]
    assert dropped_record["allowed_failure"] and dropped_record["fallbacks"] == 2
    # The public route with the option: refused, or stored with the failure.
    expression = "g g > a a"
    with pytest.raises(LoopEngineRefusal) as refused:
        _generate(
            _config(
                tmp_path / "refused",
                expression,
                fixture,
                source=str(dropped),
                particle_veto=("t",),
                loop_induced_probes=True,
            ),
            expression,
        )
    assert refused.value.key == "loop-induced-probe"
    stored = _generate(
        _config(
            tmp_path / "allowed",
            expression,
            fixture,
            source=str(dropped),
            particle_veto=("t",),
            loop_induced_probes=True,
            allow_failed_probes=True,
        ),
        expression,
    )
    probes = _filters(stored)["loop_induced_probes"]
    assert probes["allowed_failure"] and not probes["ward"]["passed"]
    assert probes["ward"]["carriers"] == {"1": "double-double", "3": "double-double"}
    assert all("in double-double" in failure for failure in probes["failed"])


@pytest.mark.loop_physics
def test_g_g_to_z_generates_with_its_rows_below_resolution_inconclusive(
    tmp_path, caplog
):
    """g g > Z (a Landau-Yang zero) at the generator's probe point: the
    helicity rows (-,+,-) and (+,-,+) that angular momentum forbids have a
    term floor of 1e-30 against the k = 1 maximum 23.5 of the same order, and
    R, P of 1e-31 in both carriers. Their otherwise failing miss is deferred
    ("helicity row below numerical resolution"): generation succeeds with
    the finiteness probe recorded inconclusive and a warning, never a pass;
    ``pyamplicol check`` on the artifact is inconclusive (exit 4) with the
    same rows, their operands and T_max recorded."""

    import logging

    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.api.services import check
    from pyamplicol.config import resolve_config
    from pyamplicol.loops.v2 import checks, induced
    from tools.loop_benchmark import li_manifest as lm

    data = lm.fixture("li_gg_z")
    compiled = lm.compile_model(data, tmp_path / "model-cache")
    output = tmp_path / "artifact"
    process = lm.expression(data, compiled)
    card = tmp_path / "card.toml"
    card.write_text(lm.card(data, output, set(compiled.parameter_defaults), process))
    with caplog.at_level(logging.WARNING):
        Generator(resolve_config(card)).generate(
            ProcessSet((ProcessRequest.parse(process, name="p"),)), output
        )
    record = lm._artifact_probes(output)
    (finiteness,) = [p for p in record["probes"] if p["probe"] == "finiteness"]
    assert finiteness["verdict"] == "inconclusive" and not finiteness["passed"]
    assert finiteness["below_resolution"] == 2 and record["rule"] == checks.RULE
    assert "failed" not in record
    assert any(
        "finiteness probe: inconclusive" in m and "generation continues" in m
        for m in caplog.messages
    )
    report = check(output, points=1, seed=12345)
    assert report.exit_code == checks.EXIT_INCONCLUSIVE, report
    (poles,) = [r for r in report.processes[0].rows if r.check == "poles"]
    assert poles.verdict == checks.INCONCLUSIVE
    deferred = [
        c
        for c in poles.cells
        if (c["reason"] or "").startswith(induced.BELOW_RESOLUTION)
    ]
    assert len(deferred) == 2
    for cell in deferred:
        assert cell["carrier"] == "double-double" and cell["terms"] < 1e-29
        assert max(cell["residue"], cell["physical"]) < 1e-30
        # the comparable coefficient's maximum, verified: (-,-,0) at k = 1
        assert "T_max 23.5 over the helicities of" in cell["reason"]
        assert "k=1" in cell["reason"]
