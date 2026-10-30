# SPDX-License-Identifier: 0BSD
"""pyAmpliCol v2 timing for gate G1 (DESIGN §14, REQUIREMENTS_ADDENDUM D).

One run measures one process at one colour accuracy on one checkout:

1. **Generation** (reported separately, MASTER_PLAN §5.8 item 8): the
   compiled loop_sm model (cached), ``LoopSlice.generate`` and the plan v4
   export of ``plan_export.NativeExecutor``, each with its wall time and the
   peak resident memory of that stage (``/proc/self/clear_refs`` resets the
   high-water mark between stages).
2. **Accuracy at the frozen points** (untimed): the reference fixture's
   points (``tests/fixtures/loop/required/<key>.json``, the stream's first
   points) in the timed configuration with the recommended stability checks
   on, their Born and finite part against every provider of the fixture with
   its metric and tolerance. The binary64 finite part is asserted where its
   estimate E (the O1 rule's, ``mqcd``) is at most ``mqcd.O1_CAP`` = 1e-9;
   above it (the user's ruling of 2026-10-29 on E1: g g > g g g g point 1)
   a double-double evaluation of the point is asserted instead, and E and
   the binary64 errors are recorded (``accuracy_record``). The finite parts
   of every timed point are kept for ``gate.py``'s comparison with the
   providers' own runs on the stream.
3. **Event timing**: the public runtime's evaluation call
   (``NativeExecutor.evaluate``, which ``loops.v2.artifact.V2VirtualRuntime``
   calls) in the speed-gate configuration: binary64, finite part only (the
   pole selection ``poles="none"``, or ``poles=False`` on a checkout before
   poles-uvir), no stability check, one thread (``threads=1`` and the
   process pinned to one core by the caller), the default 16 SIMD lanes,
   batches of ``B`` distinct points of the frozen stream
   (``streams.py``). Batches alternate between the B values in every round
   (paired blocks), after one untimed warm-up per B; per B the median per
   point over the blocks is reported with its spread. A B whose estimated
   cost exceeds ``--budget`` seconds is skipped and recorded as such. A
   failed point raises ``plan_export.FailedPoints`` and ends the run, so a
   completed record has no failed point; rescue is off (no stability check,
   no escalation), so its rescue rate is zero by construction. Before the
   warm-up the run collects and then freezes the heap it holds
   (``gc.freeze``: the model, the generated slice or the loaded process and
   the executor move to the collector's permanent generation). A runtime that
   loads an artifact holds none of the generation's objects; without the
   freeze, a full collection triggered by an evaluation's garbage walks them
   all inside a timed block (u u~ > e- e+ d d~ g, leading colour: about
   0.2-0.3 s per collection, 11-20 ms per point at B = 16 on slice
   ``7db32901``). The evaluations' own garbage is still collected.

After the timing, the same generated process can also be checked
(``--stability-points``: stability estimates as ``check_points`` makes
them, written to ``--stability-json``; ``--physical-points``: one evaluation
with every pole, its components per Laurent coefficient and Catani's
prediction of the poles), so a seven-leg process is generated once. The
``ward`` subcommand (``ward``) probes the Ward identity: one external
gluon's polarisation replaced by its momentum on the loop side.

The compiled model lives in a temporary directory under ``--scratch`` (the
system's temporary directory by default) that the run removes at its end.

Stored processes (``--store``, ``--load``): a generation can be stored as the
artifact's own loop runtime member (``artifact.write_plan`` with the native
point inputs, ``point_inputs`` = ``LOOP_V2_NATIVE_POINT_INPUTS``: the plan v4
and the native process, ``loop-runtime.pacbin``) beside a ``generation.json``
with the run's generation stages; ``--generate-only`` stops there. A later run
with ``--load`` reads it as ``V2VirtualRuntime`` does (``artifact.read_plan``,
``artifact.read_native_process``, ``NativeProcess.executor``: nothing is
regenerated) and times that executor, the integrated configuration of a loaded
artifact, whose values equal the slice's native executor's bitwise
(``tests/unit/test_loop_v2_native_process.py``). Its record keeps the stored
generation and states the load (``stored``). This splits a seven-gluon row
(about an hour of generation, then an hour of timing) into bounded jobs and
lets its checks reuse one generation.

Stage split of each block (seconds per point; MASTER_PLAN's report rules):

- ``python trees``, ``python counterterm program``, ``python scalars``,
  ``python Born and counterterm components``: the per-point inputs that the
  integrated slice still forms in Python (``assemble._PointEvaluation``);
- ``python point parameters``: their native-input replacement's Python part
  (``inputs="native"``, work/v2-generation-scale);
- ``input conversion``: ``NativeExecutor._inputs`` (carrier values);
- the native executor's own report: ``seeds``, ``factors``, ``dressing``,
  ``scatter``, ``reduction`` (NinjaRS), of which ``reduction: masters`` is the
  master-integral stage (canonicalisation, cache and oneloopmaster) and
  ``reduction: masters (oneloopmaster)`` oneloopmaster alone;
- ``assembly``: ``_PointEvaluation._assemble`` (Python);
- ``native trees``: with native inputs, the trees, Born and counterterm
  inputs that the executor forms itself (reported as ``trees`` by a native
  build that times them; otherwise part of ``other``);
- ``other``: the rest of the call (Python glue).

The native report also counts the modelled dressing work (complex MAC per
lane of the chosen kernel forms) and the master rows; the kernel throughput is
that work times the lane count over the dressing time, the useful throughput
the work times the points.

Usage:
    python -m tools.loop_benchmark pyamplicol gg_gggg --accuracy full \\
        --batches 1 8 32 128 --reps 3 --budget 900 --json OUT.json
"""

from __future__ import annotations

import contextlib
import gc
import inspect
import json
import math
import resource
import shutil
import statistics
import sys
import tempfile
import time
from fractions import Fraction
from pathlib import Path
from typing import Any

from tools.loop_v2_generate import LEADING_CASIMIRS

from . import providers, streams
from .mqcd import O1_CAP, check_configuration

ROOT = streams.ROOT
STAGES = (
    "python trees",
    "python counterterm program",
    "python scalars",
    "python Born and counterterm components",
    "python point parameters",
    "input conversion",
    "native trees",
    "seeds",
    "factors",
    "dressing",
    "scatter",
    "reduction",
    "assembly",
    "other",
)
NATIVE = ("seeds", "factors", "dressing", "scatter", "reduction")
MASTERS = "reduction: masters"
ONELOOPMASTER = "reduction: masters (oneloopmaster)"
WORK = "dressing work (modelled complex MAC per lane)"
# The required fixtures' tolerance (``tools/loop_v2_generate.py validate``),
# for a reference fixture that states none (NJet's).
REQUIRED_TOLERANCE = "2e-8"
# A stored process (``--store``/``--load``): the artifact's loop runtime
# member and the generation record beside it.
STORED_RUNTIME = "loop-runtime.pacbin"
STORED_META = "generation.json"


def _status(field: str) -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(field + ":"):
            return int(line.split()[1]) * 1024
    return 0


def _reset_peak() -> None:
    with contextlib.suppress(OSError):
        Path("/proc/self/clear_refs").write_text("5")


def _gib(value: int) -> float:
    return round(value / 2**30, 3)


class Timers:
    """Wall-time accumulators around the per-point Python stages.

    A timed call inside another timed call is part of the outer stage (the
    counterterm program evaluates its own tree rows, for instance), so the
    stages never overlap and their sum stays below the wall time."""

    def __init__(self) -> None:
        self.seconds: dict[str, float] = {}
        self.depth = 0

    def wrap(self, owner: Any, name: str, label: str) -> None:
        original = getattr(owner, name)
        seconds = self.seconds
        timers = self

        def timed(*args: Any, **kwargs: Any) -> Any:
            if timers.depth:
                return original(*args, **kwargs)
            timers.depth += 1
            start = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                timers.depth -= 1
                seconds[label] = seconds.get(label, 0.0) + time.perf_counter() - start

        timed.__wrapped__ = original  # type: ignore[attr-defined]
        setattr(owner, name, timed)

    def clear(self) -> None:
        self.seconds.clear()


def particle_names(compiled: Any) -> dict[int, str]:
    """PDG code -> particle name of the compiled model (UFO ``name`` and
    ``antiname``); auxiliary and ghost fields are not external states."""

    names: dict[int, str] = {}
    for record in compiled.ir.particles:
        if record.ghost_number or record.auxiliary_kind:
            continue
        names.setdefault(record.pdg_code, record.name)
        names.setdefault(-record.pdg_code, record.antiname)
    return names


def process_text(key: str, compiled: Any) -> str:
    """The process of ``key`` as the slice's process text, from its PDG codes
    and the model's particle names (``particle_names``)."""

    names = particle_names(compiled)
    pdgs = streams.spec(key)["pdgs"]
    missing = [p for p in pdgs if p not in names]
    if missing:
        raise KeyError(f"{key}: PDG codes {missing} are not particles of the model")
    legs = [names[p] for p in pdgs]
    return " ".join(legs[:2]) + " > " + " ".join(legs[2:])


def electroweak(key: str) -> bool:
    """Whether ``key`` takes the QCD and QED corrections on an EW UFO
    (``correction`` "EW", e.g. the M-SM G1 row gg_ttxemepg_ew; m-sm/PLAN.md
    §3.2 MS-VALIDATE item 5)."""

    return streams.spec(key)["correction"] == "EW"


def ew_model(key: str, scratch: Path) -> Any:
    """The EW UFO of ``key``'s scheme (``madloop_model``: ``{reference}``
    the reference root, ``$LOOP_REFERENCE_ROOT`` or the workspace's;
    ``$PYAMPLICOL_EW_UFO_REFERENCE`` overrides), compiled."""

    import os

    from pyamplicol.models.loading import compile_model_source

    ufo = os.environ.get("PYAMPLICOL_EW_UFO_REFERENCE")
    if not ufo:
        root = os.environ.get("LOOP_REFERENCE_ROOT") or str(
            Path(os.environ.get("PYAMPLICOL_LOOP_WORKSPACE", ROOT.parent)) / "reference"
        )
        ufo = streams.spec(key)["scheme_data"]["madloop_model"].replace(
            "{reference}", root
        )
    return compile_model_source(
        Path(ufo), require_supported=False, cache_dir=scratch / "model-cache"
    )


def _request(key: str, accuracy: str, compiled: Any) -> Any:
    from pyamplicol.loops.v2.assemble import SliceRequest
    from pyamplicol.models.loop_color_declaration import (
        resolve_loop_color_declaration,
    )

    process = streams.spec(key)
    text = process_text(key, compiled)
    if electroweak(key):
        # QCD and QED corrections on the EW UFO, its compatibility profile
        # and scale parameter, the fixed parameters the model has (as
        # ``loop_v2_generate._fixture_request``; the providers' WTau is not
        # a G_mu parameter).
        from tools.loop_v2_generate import (
            _EW_COMPATIBILITY,
            _EW_SCALE_PARAMETER,
            _external_parameters,
        )

        externals = _external_parameters(compiled)
        fixed = process["scheme_data"]["fixed_parameters"]
        return SliceRequest(
            text,
            dict(process["born_orders"]),
            dict(process["loop_orders"]),
            corrections=("QCD", "QED"),
            fixed_parameters={k: v for k, v in fixed.items() if k in externals},
            particle_veto=tuple(int(p) for p in process.get("particle_veto", ())),
            accuracy=accuracy,
            compatibility=_EW_COMPATIBILITY,
            scale_parameter=_EW_SCALE_PARAMETER,
        )
    declaration = None
    if accuracy != "full":
        # The model's declaration: for loop_sm the shipped one (MQ-NC), which
        # covers every counterterm vertex (the example QCD subset does not
        # cover the closed quark loops with electroweak legs).
        declaration = resolve_loop_color_declaration(compiled.raw_loop_model)
    return SliceRequest(
        text,
        dict(process["born_orders"]),
        dict(process["loop_orders"]),
        fixed_parameters=dict(process["scheme_data"]["fixed_parameters"]),
        # The public particle_veto (``particle_veto`` of the specification):
        # g g > g g g g g without the top is NJet's massless five-flavour QCD.
        particle_veto=tuple(int(p) for p in process.get("particle_veto", ())),
        accuracy=accuracy,
        colour_declaration=declaration,
    )


def _parameters(key: str) -> dict[str, str]:
    return dict(streams.spec(key)["scheme_data"]["parameters"])


def _native_inputs_supported() -> bool:
    from pyamplicol.loops.v2.plan_export import NativeExecutor

    return "inputs" in inspect.signature(NativeExecutor).parameters


def _finite_only() -> Any:
    """``NativeExecutor.evaluate``'s finite-only pole argument: the pole
    selection ``"none"`` (poles-uvir, WP2.10), or ``False`` before it."""

    from pyamplicol.loops.v2.plan_export import NativeExecutor

    default = inspect.signature(NativeExecutor.evaluate).parameters["poles"].default
    return False if isinstance(default, bool) else "none"


def _all_poles() -> Any:
    """``NativeExecutor.evaluate``'s pole argument with every pole."""

    from pyamplicol.loops.v2.plan_export import NativeExecutor

    default = inspect.signature(NativeExecutor.evaluate).parameters["poles"].default
    return True if isinstance(default, bool) else "all"


def components(result: Any) -> dict[str, list[float]]:
    """Per component of a point result (``assemble.COMPONENTS``) and Laurent
    coefficient (finite, single, double pole): the largest magnitude over its
    squared-order sectors."""

    from pyamplicol.loops.v2.assemble import COMPONENTS

    out = {}
    for name in COMPONENTS:
        sectors = result.components.get(name)
        if not sectors:
            continue
        width = max(len(laurent.coefficients) for laurent in sectors.values())
        out[name] = [
            max(
                abs(complex(laurent.coefficients[k]))
                for laurent in sectors.values()
                if k < len(laurent.coefficients)
            )
            for k in range(width)
        ]
    return out


def lane_scale(result: Any, average: int) -> list[float]:
    """Per Laurent coefficient the absolute sum of the reduction lanes' bare
    contributions, 2 |Omega| / (16 pi^2 average): the conditioning of a
    cancellation across families (``test_loop_v2_observables._lane_scale``)."""

    from pyamplicol.loops.v2.conventions import LOOP_FACTOR_DENOMINATOR

    factor = 2 / (LOOP_FACTOR_DENOMINATOR * math.pi**2 * average)
    lanes = list(result.families.values())
    width = max((len(lane.coefficients) for lane in lanes), default=0)
    return [
        factor * sum(abs(complex(lane.coefficients[k])) for lane in lanes)
        for k in range(width)
    ]


def catani(result: Any) -> dict[str, float] | None:
    """The virtual's poles against Catani's prediction (``ir_poles``): the
    largest relative deviation of the single and the double pole over the
    sectors."""

    poles = getattr(result, "ir_poles", None)
    if not poles:
        return None
    single = double = 0.0
    for sector, (c1, c2) in poles.items():
        laurent = result.components["virtual"][sector]
        v1, v2 = complex(laurent.single_pole), complex(laurent.double_pole)
        c1, c2 = complex(c1), complex(c2)
        single = max(single, abs(v1 - c1) / max(abs(v1), abs(c1), 1e-300))
        double = max(double, abs(v2 - c2) / max(abs(v2), abs(c2), 1e-300))
    return {"single_pole": single, "double_pole": double}


def _totals(result: Any) -> tuple[float, float]:
    born = sum(complex(v).real for v in result.born.values())
    virtual = result.components["virtual"]
    finite = sum(complex(laurent.finite).real for laurent in virtual.values())
    return float(born), float(finite)


def _relative(a: float, b: float, floor: float = 0.0) -> float:
    scale = max(abs(a), abs(b), floor)
    return 0.0 if scale == 0 else abs(a - b) / scale


def reference_errors(
    born: float, finite: float, providers: dict[str, Any], alpha: float
) -> dict[str, dict[str, float]]:
    """The Born and finite part against each provider entry of a fixture row,
    with the fixture's metric (the finite part's floor |Born| alpha_s/2pi).
    A quantity an entry does not state is not compared: the NJet fixture's
    ``catani`` entry (Catani's poles from the colour-correlated Borns) has a
    Born and the poles but no finite part."""

    floor = abs(born) * alpha / (2 * math.pi)
    errors: dict[str, dict[str, float]] = {}
    for provider, reference in providers.items():
        row = {}
        if "born" in reference:
            row["born"] = _relative(born, float(reference["born"]))
        if "finite" in reference:
            row["finite"] = _relative(finite, float(reference["finite"]), floor)
        if row:
            errors[provider] = row
    return errors


BINARY64 = "double"
DOUBLE_DOUBLE = "double-double"


def finite_estimate(result: Any) -> float:
    """The binary64 relative estimate E of a point's finite part, the O1
    rule's (``mqcd``: the recommended checks' absolute budget of the
    coefficient over its value), with the budgets summed over the
    squared-order sectors and taken over the summed finite part G1 compares.
    Without an estimate, or for a nonzero budget of a vanishing finite part,
    inf."""

    stability = result.stability
    if stability is None:
        return math.inf
    budget = sum(abs(float(b.coefficients[0])) for b in stability.absolute.values())
    finite = abs(_totals(result)[1])
    if finite:
        return budget / finite
    return 0.0 if budget == 0 else math.inf


def asserted_carrier(estimate: float) -> str:
    """The carrier the accuracy check asserts at a point (the user's ruling
    of 2026-10-29 on E1, m-qcd PLAN §1.4 rule 2): binary64 where E <= O1_CAP,
    double-double above it (or for a NaN estimate)."""

    return BINARY64 if estimate <= O1_CAP else DOUBLE_DOUBLE


def accuracy_record(
    name: str,
    fixture: dict[str, Any],
    binary64: dict[int, tuple[float, float]],
    estimates: dict[int, float],
    double_double: dict[int, tuple[float, float]],
    alpha: float,
) -> dict[str, Any]:
    """The accuracy check of the fixture's points ``binary64`` (index ->
    (Born, finite)) with their finite parts' estimates E (``estimates``) and
    the double-double values of the points above ``O1_CAP``
    (``double_double``). Per row: the binary64 errors against every provider
    (``errors``, as before), E, the carrier asserted per quantity
    (``asserted``; the Born, a tree outside the loop estimate, in binary64),
    the double-double values and errors where evaluated and the row's
    largest asserted error. ``max_error`` and ``passed`` are those of the
    asserted carriers against ``tolerance``; ``max_error_binary64`` is the
    largest binary64 error at any point."""

    tolerance = float(fixture.get("tolerance", REQUIRED_TOLERANCE))
    rows = []
    worst = worst_binary64 = 0.0
    for index, (born, finite) in sorted(binary64.items()):
        references = fixture["rows"][index]["providers"]
        errors = reference_errors(born, finite, references, alpha)
        estimate = estimates[index]
        carrier = asserted_carrier(estimate)
        row: dict[str, Any] = {
            "index": index,
            "mu_r": fixture["mu_r"][index],
            "born": born,
            "finite": finite,
            "errors": errors,
            "estimate": {"finite": estimate},
            "asserted": {"born": BINARY64, "finite": carrier},
        }
        asserted = [e["born"] for e in errors.values() if "born" in e]
        finites = errors
        if carrier == DOUBLE_DOUBLE:
            dd_born, dd_finite = double_double[index]
            finites = reference_errors(dd_born, dd_finite, references, alpha)
            row["double_double"] = {
                "born": dd_born,
                "finite": dd_finite,
                "errors": finites,
            }
        asserted += [e["finite"] for e in finites.values() if "finite" in e]
        row["max_error"] = max(asserted, default=0.0)
        worst = max(worst, row["max_error"])
        worst_binary64 = max(
            [worst_binary64, *(e for r in errors.values() for e in r.values())]
        )
        rows.append(row)
    return {
        "fixture": name,
        "metric": fixture["error_metric"],
        "tolerance": tolerance,
        "tolerance_source": "fixture" if "tolerance" in fixture else "required",
        "checks": CHECKS,
        "estimate_cap": O1_CAP,
        "double_double_points": [
            row["index"] for row in rows if row["asserted"]["finite"] == DOUBLE_DOUBLE
        ],
        "max_error": worst,
        "max_error_binary64": worst_binary64,
        "passed": worst <= tolerance,
        "rows": rows,
    }


def reference_fixture(key: str) -> tuple[str, dict[str, Any]] | None:
    """The reference fixture of ``key`` (``streams.fixture_name``: its
    required fixture, or the specification's ``reference_fixture``, e.g.
    NJet's) with its content, or None if it has none."""

    name = streams.fixture_name(key)
    path = streams.FIXTURES / f"{name}.json"
    if not path.exists():
        return None
    return name, json.loads(path.read_text())


def fixture_batch(fixture: dict[str, Any], indices: list[int]) -> tuple[list, list]:
    """The exact points and squared scales of a fixture's points ``indices``
    (each at the fixture's own scale)."""

    points = [
        [[Fraction(x) for x in leg] for leg in fixture["points"][i]] for i in indices
    ]
    scales = [str(Fraction(fixture["mu_r"][i]) ** 2) for i in indices]
    return points, scales


def universal_double_pole(key: str, accuracy: str) -> float | None:
    """D / Born = -(alpha_s/2pi) sum_i C_i over the massless coloured legs of
    ``key`` at colour ``accuracy``. Full colour: the providers' conversion
    (``providers.universal_double_pole``, the toolkit's
    ``required_spec.double_pole_factor``); leading colour: the leading parts
    of the Casimirs (C_F -> N_c/2) of ``tools/loop_v2_generate.py``'s table,
    the one the generator's ``poles`` check uses; None at NLC, where it holds
    only with adjoint legs. A non-QCD correction raises at every accuracy,
    like the providers' conversion."""

    process = streams.spec(key)
    if process["correction"] != "QCD":
        raise ValueError("the G1 value comparison converts QCD corrections only")
    if accuracy == "full":
        return providers.universal_double_pole(process)
    if accuracy != "lc":
        return None
    _, required_spec = streams._toolkit()
    total = sum(
        (
            LEADING_CASIMIRS[abs(required_spec.particle(pdg)["colour"])]
            for pdg, mass in zip(
                process["pdgs"], required_spec.masses(process), strict=True
            )
            if not mass
        ),
        Fraction(0),
    )
    # double_pole_factor's arithmetic: equal at both accuracies without quarks.
    return -float(total) * providers.alpha_s(process) / (2 * math.pi)


def _git(*args: str) -> str:
    import subprocess

    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _native_build(directory: Path | None) -> dict[str, Any] | None:
    """The staged native build's ``build-info.json`` (``--native-build``)."""

    if directory is None:
        return None
    info = json.loads((directory / "build-info.json").read_text())
    return {
        "directory": directory.name,
        "digest": info["native_build_inputs_sha256"],
        "source_revision": info["source_revision"],
        "profile": info["profile"],
    }


class Run:
    """One process, accuracy and checkout (module docstring)."""

    def __init__(self, options: Any) -> None:
        self.options = options
        self.key = options.process
        self.stream = streams.load(self.key)
        self.parameters = _parameters(self.key)
        self.timers = Timers()
        self.record: dict[str, Any] = {
            "kind": "pyamplicol-v2",
            "process": self.key,
            "accuracy": options.accuracy,
            "inputs": options.inputs,
            "lanes": options.lanes,
            "schedule": options.schedule,
            "revision": _git("rev-parse", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
            "host_cpus": sorted(_affinity()),
            "protocol": "binary64, finite part only (poles off), no stability check, "
            "one thread on one pinned core, warm-up excluded, paired blocks, "
            "setup heap frozen out of the cyclic collector",
        }

    # -- generation ---------------------------------------------------------

    def generate(self) -> None:
        from pyamplicol.loops.native import load_loop_native
        from pyamplicol.loops.v2.assemble import LoopSlice
        from pyamplicol.loops.v2.plan_export import NativeExecutor

        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from tools.loop_v2_operation_counts import UFO, compile_loop_sm

        native = load_loop_native()
        self.record["native"] = _native_build(self.options.native_build)
        stages: dict[str, Any] = {}
        scratch = Path(tempfile.mkdtemp(prefix="g1-model-", dir=self.options.scratch))
        self.scratch = scratch
        _reset_peak()
        start = time.perf_counter()
        compiled = (
            ew_model(self.key, scratch)
            if electroweak(self.key)
            else compile_loop_sm(UFO, scratch)
        )
        stages["model"] = {
            "seconds": time.perf_counter() - start,
            "peak_gib": _gib(_status("VmHWM")),
        }
        _reset_peak()
        start = time.perf_counter()
        request = _request(self.key, self.options.accuracy, compiled)
        self.record["process_text"] = request.process
        slice_ = LoopSlice.generate(compiled, request, native)
        stages["generate"] = {
            "seconds": time.perf_counter() - start,
            "peak_gib": _gib(_status("VmHWM")),
        }
        _reset_peak()
        start = time.perf_counter()
        options: dict[str, Any] = {
            "forward": False,
            "lanes": self.options.lanes,
            "threads": 1,
            "merged": self.options.schedule == "M",
        }
        if self.options.inputs == "native":
            options["inputs"] = "native"
        self.executor = NativeExecutor(slice_, **options)
        stages["export"] = {
            "seconds": time.perf_counter() - start,
            "peak_gib": _gib(_status("VmHWM")),
            "plan_mb": round(len(self.executor._plan_json) / 1e6, 3),
        }
        self.slice = slice_
        self.record["generation"] = stages
        self.record["structure"] = {
            "families": len(slice_.plan.schedules),
            "b_trie_nodes": sum(
                len(s.trie.nodes) for s in slice_.plan.schedules.values()
            ),
        }
        self._install_timers()
        print(self.key, "generation", json.dumps(stages), flush=True)
        if getattr(self.options, "store", None) is not None:
            self.store(self.options.store)

    # -- stored processes ---------------------------------------------------

    def _configuration(self) -> dict[str, Any]:
        return {
            "process": self.key,
            "accuracy": self.options.accuracy,
            "inputs": self.options.inputs,
            "lanes": self.options.lanes,
            "schedule": self.options.schedule,
        }

    def store(self, directory: Path) -> None:
        """Write the generated process as the artifact's loop runtime member
        with its native point inputs (module docstring) and
        ``generation.json``; a stored process is never overwritten."""

        from pyamplicol.generation.loop_artifact import LOOP_V2_NATIVE_POINT_INPUTS
        from pyamplicol.loops.v2.artifact import plan_digest, write_plan
        from pyamplicol.loops.v2.native_process import NativeProcess

        if self.options.inputs != "native" or self.options.schedule != "B":
            raise SystemExit("a stored process has native inputs and schedule B")
        directory.mkdir(parents=True, exist_ok=False)
        _reset_peak()
        start = time.perf_counter()
        native = NativeProcess.of(self.executor)
        # With the companion of the certified-scaleless families (its plan
        # and tree program), as the artifact writer stores it.
        companion = native.scaleless
        write_plan(
            native.plan_json,
            directory / STORED_RUNTIME,
            native,
            None if companion is None else companion.plan_json,
        )
        written = {
            "seconds": time.perf_counter() - start,
            "peak_gib": _gib(_status("VmHWM")),
            "bytes": (directory / STORED_RUNTIME).stat().st_size,
        }
        meta = {
            "kind": "stored-process",
            **self._configuration(),
            "plan_sha256": plan_digest(native.plan_json),
            "point_inputs": LOOP_V2_NATIVE_POINT_INPUTS,
            "store": written,
            **{
                k: self.record[k]
                for k in (
                    "revision",
                    "branch",
                    "dirty",
                    "host_cpus",
                    "native",
                    "process_text",
                    "generation",
                    "structure",
                )
            },
        }
        (directory / STORED_META).write_text(json.dumps(meta, indent=1) + "\n")
        print(self.key, "stored", json.dumps(written), flush=True)

    def load(self, directory: Path) -> None:
        """Read a stored process (``--load``) as the public runtime does and
        build its native executor; the record keeps the stored generation."""

        from pyamplicol.generation.loop_artifact import LOOP_V2_NATIVE_POINT_INPUTS
        from pyamplicol.loops.native import load_loop_native
        from pyamplicol.loops.v2.artifact import (
            plan_digest,
            read_native_process,
            read_plan,
        )

        meta = json.loads((directory / STORED_META).read_text())
        if meta.get("kind") != "stored-process":
            raise SystemExit(f"{directory} holds no stored process")
        wanted = self._configuration()
        stored = {k: meta.get(k) for k in wanted}
        if stored != wanted:
            raise SystemExit(f"stored process {stored} is not this run's {wanted}")
        build = _native_build(self.options.native_build)
        if build is None or meta["native"] is None:
            raise SystemExit("a stored process needs --native-build on both sides")
        if build["digest"] != meta["native"]["digest"]:
            raise SystemExit(
                "the stored process was generated with another native build "
                f"({meta['native']['digest'][:12]}...)"
            )
        native = load_loop_native()
        self.record["native"] = build
        _reset_peak()
        start = time.perf_counter()
        runtime = directory / STORED_RUNTIME
        plan_json = read_plan(runtime)
        if plan_json is None or plan_digest(plan_json) != meta["plan_sha256"]:
            raise SystemExit("the stored plan does not have its recorded digest")
        process = read_native_process(runtime, plan_json)
        self.executor = process.executor(native, lanes=self.options.lanes, threads=1)
        loaded = {
            "seconds": time.perf_counter() - start,
            "peak_gib": _gib(_status("VmHWM")),
        }
        self.slice = None
        self.record["process_text"] = meta["process_text"]
        self.record["generation"] = meta["generation"]
        self.record["structure"] = meta["structure"]
        # No absolute path: the store's directory name and its generation's
        # provenance (``generation`` is that run's).
        # The native point inputs this build reads (read_native_process reads
        # no other format); a store's label written by a harness before
        # 2026-10-25 fix round 3 (the literal "native-v1") is kept beside it.
        self.record["stored"] = {
            "directory": directory.name,
            "plan_sha256": meta["plan_sha256"],
            "point_inputs": LOOP_V2_NATIVE_POINT_INPUTS,
            **(
                {"store_label": meta["point_inputs"]}
                if meta["point_inputs"] != LOOP_V2_NATIVE_POINT_INPUTS
                else {}
            ),
            "generated_revision": meta["revision"],
            "generated_dirty": meta["dirty"],
            "generated_host_cpus": meta["host_cpus"],
            "load": loaded,
        }
        self._install_timers()
        print(self.key, "loaded", json.dumps(loaded), flush=True)

    def _install_timers(self) -> None:
        from pyamplicol.loops.v2 import assemble
        from pyamplicol.loops.v2.plan_export import NativeExecutor

        wrap = self.timers.wrap
        slice_ = self.slice
        if slice_ is not None:
            # A loaded process has no slice: its inputs are all native.
            wrap(type(slice_.tree_rows), "evaluate", "python trees")
            wrap(assemble.LoopSlice, "scalars", "python scalars")
            if slice_.counterterm_program is not None:
                wrap(
                    type(slice_.counterterm_program),
                    "point",
                    "python counterterm program",
                )
            wrap(
                assemble._PointEvaluation,
                "_born_and_counterterms",
                "python Born and counterterm components",
            )
        wrap(assemble._PointEvaluation, "_assemble", "assembly")
        wrap(NativeExecutor, "_inputs", "input conversion")
        if hasattr(NativeExecutor, "_native_points"):
            wrap(NativeExecutor, "_native_points", "python point parameters")

    # -- evaluation -----------------------------------------------------------

    def _batch(self, start: int, size: int) -> tuple[list, list]:
        count = len(self.stream["points"])
        indices = [(start + k) % count for k in range(size)]
        points = [streams.exact(self.stream, i) for i in indices]
        scales = [str(Fraction(self.stream["mu_r"][i]) ** 2) for i in indices]
        return points, scales

    def evaluate(self, start: int, size: int) -> dict[str, Any]:
        points, scales = self._batch(start, size)
        self.timers.clear()
        options: dict[str, Any] = {
            "parameters": self.parameters,
            "poles": _finite_only(),
        }
        if self.options.schedule == "M":
            options["schedule"] = "M"
        begin = time.perf_counter()
        results = self.executor.evaluate(points, scales, **options)
        wall = time.perf_counter() - begin
        report = self.executor.last_report
        seconds = dict(self.timers.seconds)
        for stage in NATIVE:
            seconds[stage] = report["seconds"].get(stage, 0.0)
        for extra in (MASTERS, ONELOOPMASTER):
            if extra in report["seconds"]:
                seconds[extra] = report["seconds"][extra]
        if "trees" in report["seconds"]:
            seconds["native trees"] = report["seconds"]["trees"]
        accounted = sum(seconds.get(stage, 0.0) for stage in STAGES if stage != "other")
        seconds["other"] = wall - accounted
        return {
            "start": start,
            "points": size,
            "wall": wall,
            "seconds": seconds,
            "counts": dict(report["counts"]),
            "lanes": report["lanes"],
            "threads": report["threads"],
            "reals_per_lane": dict(report["reals_per_lane"]),
            "values": {
                (start + k) % len(self.stream["points"]): _totals(r)
                for k, r in enumerate(results)
            },
        }

    def accuracy(self) -> None:
        """The Born and finite part at the reference fixture's points
        (``streams.fixture_name``: the required fixture of the process, or the
        specification's ``reference_fixture``, e.g. NJet's) against each of
        its providers, at the fixture's own points and scales in one batch of
        at most one chunk of lanes, with the recommended stability checks
        (``mqcd.check_configuration``); the points whose finite part's
        binary64 estimate exceeds ``O1_CAP`` are evaluated again in
        double-double, which the check asserts there (``accuracy_record``).
        Untimed. The required fixtures' points and scales are the stream's
        first points (``streams.campaign_agreement``); an NJet fixture's
        points are the stream's first points at its own scale
        (``points_are_stream_points``)."""

        from pyamplicol.loops.v2.assemble import Precision

        found = reference_fixture(self.key)
        if found is None or self.options.accuracy != "full":
            self.record["accuracy_check"] = None
            return
        name, fixture = found
        count = min(len(fixture["points"]), self.options.lanes)
        points, scales = fixture_batch(fixture, list(range(count)))
        options: dict[str, Any] = {
            "parameters": self.parameters,
            "poles": _finite_only(),
        }
        if self.options.schedule == "M":
            options["schedule"] = "M"
        results = self.executor.evaluate(
            points, scales, stability=check_configuration(), **options
        )
        values = {index: _totals(result) for index, result in enumerate(results)}
        estimates = {
            index: finite_estimate(result) for index, result in enumerate(results)
        }
        outside = [
            index
            for index in range(count)
            if asserted_carrier(estimates[index]) == DOUBLE_DOUBLE
        ]
        double_double: dict[int, tuple[float, float]] = {}
        if outside:
            points, scales = fixture_batch(fixture, outside)
            precise = self.executor.evaluate(
                points, scales, precision=Precision.double_double(), **options
            )
            double_double = {
                index: _totals(result)
                for index, result in zip(outside, precise, strict=True)
            }
        same = [
            index
            for index in range(count)
            if index < len(self.stream["points"])
            and self.stream["points"][index] == fixture["points"][index]
        ]
        # NJet fixtures state no tolerance: the required fixtures' (2e-8,
        # tools/loop_v2_generate.py validate).
        check = accuracy_record(
            name,
            fixture,
            values,
            estimates,
            double_double,
            float(self.parameters["aS"]),
        )
        self.record["accuracy_check"] = {
            "fixture": name,
            "points": count,
            "points_are_stream_points": same,
            **{k: v for k, v in check.items() if k != "fixture"},
        }
        print(
            self.key,
            "accuracy vs providers: max",
            f"{check['max_error']:.2e}",
            f"(binary64 {check['max_error_binary64']:.2e}; double-double at",
            f"{check['double_double_points']})",
            flush=True,
        )

    def freeze_heap(self) -> None:
        """Collect, then move every object alive to the cyclic collector's
        permanent generation before the timing (module docstring, step 3);
        the record states the frozen count."""

        gc.collect()
        gc.freeze()
        self.record["gc_frozen_objects"] = gc.get_freeze_count()

    def timing(self) -> None:
        """Paired blocks of every B (module docstring). The warm-up of a B
        evaluates ``--warm-up`` points of it (default: the whole block; one
        chunk of lanes already compiles every kernel, which the heavy rows
        use), and its time per point estimates each B's cost against
        ``--budget``. Every block prints its time (stage-level progress), and
        the record is written after every round, the last included, and after
        the physical rows (``partial``) when a JSON target is given."""

        options = self.options
        batches = sorted(set(options.batches))
        warm: dict[int, float] = {}
        warm_points: dict[int, int] = {}
        skipped: dict[int, str] = {}
        limit = getattr(options, "warm_up", None)
        for size in batches:
            count = size if not limit else min(size, limit)
            start = time.perf_counter()
            self.evaluate(0, count)
            warm[size] = time.perf_counter() - start
            warm_points[size] = count
            print(
                self.key,
                f"warm-up B={size} ({count} points): {warm[size]:.3f} s",
                flush=True,
            )
            # The warm-up includes lazy compilation; the estimate scales the
            # cheapest B per point.
        per_point = min(warm[b] / warm_points[b] for b in batches)
        planned = []
        for size in batches:
            blocks = max(1, math.ceil(options.min_points / size))
            estimate = per_point * size * blocks * options.reps
            if estimate > options.budget:
                skipped[size] = (
                    f"estimated {estimate:.0f} s for {options.reps} rounds of "
                    f"{blocks} block(s) over the budget of {options.budget:.0f} s"
                )
                continue
            planned.append((size, blocks))
        self.record["warm_up_seconds"] = warm
        self.record["warm_up_points"] = warm_points
        self.record["skipped_batches"] = skipped
        runs: dict[int, list[dict[str, Any]]] = {size: [] for size, _ in planned}
        offsets = {size: 0 for size, _ in planned}
        for _round in range(options.reps):
            for size, blocks in planned:
                for _ in range(blocks):
                    run = self.evaluate(offsets[size], size)
                    offsets[size] += size
                    runs[size].append(run)
                    print(
                        self.key,
                        f"round {_round + 1} B={size} block at {run['start']}: "
                        f"{run['wall'] / size * 1e3:.3f} ms/pt",
                        flush=True,
                    )
            print(self.key, "round", _round + 1, "done", flush=True)
            self.record["batches"] = {
                str(size): _summary(runs[size]) for size, _ in planned
            }
            # Also after the last round: the checks that follow (physical,
            # stability) may not finish.
            self.checkpoint(partial=True)
        for size, _ in planned:
            summary = self.record["batches"][str(size)]
            print(
                self.key,
                f"B={size}: {summary['median_seconds_per_point'] * 1e3:.3f} ms/pt",
                json.dumps(
                    {
                        k: round(v * 1e3, 3)
                        for k, v in summary["stages_per_point"].items()
                    }
                ),
                flush=True,
            )

    def checkpoint(self, *, partial: bool) -> None:
        """Write the record so far to ``--json`` (``partial`` while the run
        goes on; the final record replaces it)."""

        target = getattr(self.options, "json", None)
        if target is None:
            return
        record = {**self.record, "partial": partial}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record, indent=1) + "\n")

    def physical(self, indices: list[int]) -> None:
        """One binary64 evaluation with every pole of the stream points
        ``indices`` (one batch): the components per Laurent coefficient (the
        scale of the Ward check), the poles against Catani's prediction where
        the executor forms it, and the virtual's double pole over the Born
        against the universal -(alpha_s/2pi) sum_i C_i of the massless
        coloured legs at the run's colour accuracy
        (``universal_double_pole``)."""

        expected = universal_double_pole(self.key, self.options.accuracy)
        rows = []
        for start in range(0, len(indices), self.options.lanes):
            chunk = indices[start : start + self.options.lanes]
            batches = [self._batch(index, 1) for index in chunk]
            points = [p for batch in batches for p in batch[0]]
            scales = [mu for batch in batches for mu in batch[1]]
            begin = time.perf_counter()
            results = self.executor.evaluate(
                points, scales, parameters=self.parameters, poles=_all_poles()
            )
            seconds = (time.perf_counter() - begin) / len(chunk)
            for index, result in zip(chunk, results, strict=True):
                born, finite = _totals(result)
                double = float(complex(result.totals[3]).real)
                ratio = double / born if born else None
                rows.append(
                    {
                        "index": index,
                        "born": born,
                        "finite": finite,
                        "components": components(result),
                        "catani": catani(result),
                        "double_pole_over_born": ratio,
                        "universal_double_pole": expected,
                        "double_pole_deviation": None
                        if ratio is None or expected is None
                        else abs(ratio - expected) / abs(expected),
                        "seconds": seconds,
                    }
                )
                print(self.key, "physical", json.dumps(rows[-1]), flush=True)
        self.record["physical"] = rows

    def stability(self, indices: list[int]) -> None:
        """``check_points`` on this run's generated process; the record goes
        to ``--stability-json``."""

        rows = stability_rows(self, indices, self.options.stability_arithmetic)
        record = {
            **{k: v for k, v in self.record.items() if k not in ("batches",)},
            "kind": "stability",
            "checks": CHECKS,
            "rows": rows,
        }
        target = self.options.stability_json
        if target is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(record, indent=1) + "\n")

    def close(self) -> None:
        """Remove the run's compiled-model directory."""

        scratch = getattr(self, "scratch", None)
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
            self.scratch = None

    def run(self) -> dict[str, Any]:
        try:
            if getattr(self.options, "load", None) is not None:
                self.load(self.options.load)
            else:
                try:
                    self.generate()
                except Exception as error:
                    # A process this checkout cannot generate is a result: the
                    # record keeps the refusal instead of dropping the row.
                    self.record["generation_error"] = (
                        f"{type(error).__name__}: {str(error)[:600]}"
                    )
                    self.record["batches"] = {}
                    return self.record
            if getattr(self.options, "generate_only", False):
                self.record["batches"] = {}
                self.record["generate_only"] = True
                return self.record
            self.accuracy()
            self.freeze_heap()
            self.timing()
            if getattr(self.options, "physical_points", None):
                self.physical(self.options.physical_points)
                self.checkpoint(partial=True)
            if getattr(self.options, "stability_points", None):
                self.stability(self.options.stability_points)
        finally:
            self.close()
        self.record["max_rss_gib"] = _gib(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        )
        return self.record


def _affinity() -> set[int]:
    import os

    return set(os.sched_getaffinity(0))


def _summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    per_point = [run["wall"] / run["points"] for run in runs]
    median = statistics.median(per_point)
    stages = {}
    names = sorted({name for run in runs for name in run["seconds"]})
    for name in names:
        stages[name] = statistics.median(
            run["seconds"].get(name, 0.0) / run["points"] for run in runs
        )
    counts = runs[0]["counts"]
    points = runs[0]["points"]
    lanes = runs[0]["lanes"]
    chunks = math.ceil(points / lanes)
    work = counts.get(WORK)
    dressing = stages.get("dressing", 0.0) * points
    throughput = None
    if work and dressing > 0:
        per_chunk = work / chunks
        throughput = {
            "work_per_lane_per_chunk": per_chunk,
            "useful_cmac_per_point": per_chunk,
            "kernel_cmac_per_second": work * lanes / dressing,
            "useful_cmac_per_second": per_chunk * points / dressing,
        }
    out = {
        "blocks": len(runs),
        "points_per_block": points,
        "median_seconds_per_point": median,
        "min_seconds_per_point": min(per_point),
        "max_seconds_per_point": max(per_point),
        "samples_seconds_per_point": per_point,
        "stages_per_point": stages,
        "counts_per_block": counts,
        "reals_per_lane": runs[0]["reals_per_lane"],
        "throughput": throughput,
        # (born, finite) per stream index, for the comparison with the
        # providers' runs on the same points (gate.py).
        "values": {
            str(index): value
            for run in runs
            for index, value in sorted(run["values"].items())
        },
    }
    return out


CHECKS = (
    "the recommended checks (loops.v2.stability.RECOMMENDED_CHECKS): one generic "
    "exact rotation and the rescaled reduction check"
)


def stability_rows(
    run: Run,
    indices: list[int],
    arithmetics: list[str],
    fixture: tuple[str, dict[str, Any]] | None = None,
) -> list:
    """Stream points of a generated run evaluated with the recommended checks
    (``RECOMMENDED_CHECKS``: one generic exact rotation and the rescaled
    reduction check; a rotation about the beam axis under-reports, package
    mq-stab), finite part only: the estimate E and each check's relative
    deviation (``checks``: the rotated evaluation's is the
    rotational-invariance test). With ``fixture`` (name,
    content: ``reference_fixture``) the indices are the fixture's points at
    its own scales, and each row also has the finite part's deviation from
    every reference of the fixture that states one
    (``deviation_vs_references``, the fixture metric of ``reference_errors``)."""

    from pyamplicol.loops.v2.assemble import Precision
    from pyamplicol.loops.v2.stability import RECOMMENDED_CHECKS

    precisions = {
        "double": Precision.double(),
        "double-double": Precision.double_double(),
    }
    checks = RECOMMENDED_CHECKS
    rows = []
    # One batch of at most one chunk of lanes per arithmetic: at seven legs
    # a chunk costs as much as one of its points.
    lanes = run.options.lanes
    for start in range(0, len(indices), lanes):
        chunk = indices[start : start + lanes]
        if fixture is None:
            batches = [run._batch(index, 1) for index in chunk]
            points = [p for batch in batches for p in batch[0]]
            scales = [mu for batch in batches for mu in batch[1]]
        else:
            points, scales = fixture_batch(fixture[1], chunk)
        for arithmetic in arithmetics:
            begin = time.perf_counter()
            results = run.executor.evaluate(
                points,
                scales,
                parameters=run.parameters,
                precision=precisions[arithmetic],
                poles=_finite_only(),
                stability=checks,
            )
            seconds = (time.perf_counter() - begin) / len(chunk)
            for index, result in zip(chunk, results, strict=True):
                born, finite = _totals(result)
                rows.append(
                    {
                        "index": index,
                        "arithmetic": arithmetic,
                        "born": born,
                        "finite": finite,
                        "estimate": result.stability.relative,
                        "estimate_finite": (
                            getattr(result.stability, "coefficients", None) or [None]
                        )[0],
                        "checks": {
                            str(name): float(value)
                            for name, value in dict(
                                getattr(result.stability, "checks", {}) or {}
                            ).items()
                        },
                        "seconds_with_checks": seconds,
                        "batch": len(chunk),
                    }
                )
                if fixture is not None:
                    name, content = fixture
                    errors = reference_errors(
                        born,
                        finite,
                        content["rows"][index]["providers"],
                        float(run.parameters["aS"]),
                    )
                    rows[-1]["fixture"] = name
                    rows[-1]["mu_r"] = content["mu_r"][index]
                    rows[-1]["deviation_vs_references"] = {
                        reference: row["finite"]
                        for reference, row in errors.items()
                        if "finite" in row
                    }
                print(run.key, json.dumps(rows[-1]), flush=True)
    return rows


def check_points(options: Any) -> int:
    """Evaluate chosen stream points with stability checks (the recommended
    checks, ``stability_rows``) in the configuration
    of a run, in each arithmetic of ``--arithmetic`` (binary64 and/or
    double-double): the estimate E beside the value, for the points where the
    timed binary64 values deviate most from the providers (``gate.py``). The
    double-double values separate pyAmpliCol's binary64 loss from the
    providers' own (they read the points rounded to binary64). With
    ``--fixture`` the points are the reference fixture's (e.g. NJet's ten
    seven-gluon points at mu_R = 1000 GeV), where the timing run's accuracy
    check compares (``Run.accuracy``)."""

    fixture = None
    if getattr(options, "fixture", False):
        fixture = reference_fixture(options.process)
        if fixture is None:
            raise SystemExit(f"{options.process} has no reference fixture")
        count = len(fixture[1]["points"])
        outside = [i for i in options.points if not 0 <= i < count]
        if outside:
            raise SystemExit(f"{fixture[0]} has {count} points, not {outside}")
    run = Run(options)
    try:
        if getattr(options, "load", None) is not None:
            run.load(options.load)
        else:
            run.generate()
        rows = stability_rows(run, options.points, options.arithmetic, fixture)
    finally:
        run.close()
    run.record["kind"] = "stability"
    run.record["checks"] = CHECKS
    if fixture is not None:
        # The rows are the fixture's points (``index``: the fixture's), at
        # its own scales: no stream point.
        run.record["fixture"] = fixture[0]
        run.record["fixture_metric"] = fixture[1]["error_metric"]
    run.record["rows"] = rows
    if options.json:
        options.json.write_text(json.dumps(run.record, indent=1) + "\n")
    return 0


WARD_FACTORS = {"1": (1, 0), "i": (0, 1)}


def ward(options: Any) -> int:
    """The Ward identity at chosen stream points (ADDENDUM H: one external
    gluon's polarisation replaced by its momentum).

    The process is generated in the asymmetric Ward mode of WP2.5
    (``ObservableSlice.generate(..., ward=True)``: full tree kernels) and its
    inclusive column runs natively (``NativeObservables``); epsilon_j -> c p_j
    acts on the loop side only (blocks, counterterm currents, field
    insertions) against the physical Born, so each part of the renormalised
    interference (bare, UV, R2, local UV, fields) must vanish per Laurent
    coefficient, c = 1 and c = i covering its real and imaginary part. The
    per-point inputs of the Ward mode are formed in Python (the native trees
    take no literal sources), binary64, every pole. Each row keeps the parts'
    magnitudes, the physical Born and the lanes' absolute sum (the
    cancellation's conditioning); ``gate.py`` divides by the physical scale of
    a ``--physical-points`` evaluation of the same point."""

    from pyamplicol.loops.native import load_loop_native
    from pyamplicol.loops.v2.assemble import Precision
    from pyamplicol.loops.v2.observables import (
        INCLUSIVE,
        NativeObservables,
        ObservableSlice,
    )

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tools.loop_v2_operation_counts import UFO, compile_loop_sm

    options.accuracy, options.inputs, options.schedule = "full", "python", "B"
    run = Run(options)
    record = run.record
    record["kind"] = "ward"
    record["native"] = _native_build(options.native_build)
    stages: dict[str, Any] = {}
    scratch = Path(tempfile.mkdtemp(prefix="g1-model-", dir=options.scratch))
    run.scratch = scratch
    rows = []
    try:
        native = load_loop_native()
        compiled = (
            ew_model(run.key, scratch)
            if electroweak(run.key)
            else compile_loop_sm(UFO, scratch)
        )
        _reset_peak()
        start = time.perf_counter()
        request = _request(run.key, "full", compiled)
        record["process_text"] = request.process
        observables = ObservableSlice.generate(compiled, request, native, ward=True)
        stages["generate"] = {
            "seconds": time.perf_counter() - start,
            "peak_gib": _gib(_status("VmHWM")),
        }
        print(run.key, "ward generation", json.dumps(stages["generate"]), flush=True)
        _reset_peak()
        start = time.perf_counter()
        columns = NativeObservables.correlated(
            observables, (INCLUSIVE,), lanes=options.lanes, threads=1
        )
        stages["export"] = {
            "seconds": time.perf_counter() - start,
            "peak_gib": _gib(_status("VmHWM")),
        }
        record["generation"] = stages
        average = observables.slice.normalisation.average
        physical = []
        for index in options.points:
            points, scales = run._batch(index, 1)
            if getattr(options, "physical", False):
                # The physical scale of the point in the same generation
                # (no substitution), for ``gate.ward_rows``.
                begin = time.perf_counter()
                (result,) = columns.evaluate(
                    points,
                    scales,
                    parameters=run.parameters,
                    precision=Precision.double(),
                )
                value = result[INCLUSIVE]
                physical.append(
                    {
                        "index": index,
                        "born": float(complex(value.totals[0]).real),
                        "finite": float(complex(value.totals[1]).real),
                        "components": components(value),
                        "seconds": time.perf_counter() - begin,
                    }
                )
                record["physical"] = physical
                print(run.key, "ward physical", json.dumps(physical[-1]), flush=True)
            for leg in options.legs:
                for name in options.factors:
                    begin = time.perf_counter()
                    (result,) = columns.evaluate(
                        points,
                        scales,
                        ward=(leg, WARD_FACTORS[name]),
                        parameters=run.parameters,
                        precision=Precision.double(),
                    )
                    value = result[INCLUSIVE]
                    rows.append(
                        {
                            "index": index,
                            "leg": leg,
                            "factor": name,
                            "born": float(complex(value.totals[0]).real),
                            "components": components(value),
                            "lanes": lane_scale(value, average),
                            "seconds": time.perf_counter() - begin,
                        }
                    )
                    print(run.key, "ward", json.dumps(rows[-1]), flush=True)
                    record["rows"] = rows
                    if options.json:
                        options.json.parent.mkdir(parents=True, exist_ok=True)
                        options.json.write_text(json.dumps(record, indent=1) + "\n")
    finally:
        run.close()
    record["rows"] = rows
    record["max_rss_gib"] = _gib(
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    )
    if options.json:
        options.json.parent.mkdir(parents=True, exist_ok=True)
        options.json.write_text(json.dumps(record, indent=1) + "\n")
    return 0


def main(options: Any) -> int:
    if options.inputs == "native" and not _native_inputs_supported():
        raise SystemExit("this checkout has no native point inputs (WP3.1)")
    if getattr(options, "load", None) is not None and (
        getattr(options, "store", None) is not None or options.generate_only
    ):
        raise SystemExit("--load times a stored process: no --store or --generate-only")
    if getattr(options, "generate_only", False) and options.store is None:
        raise SystemExit("--generate-only needs --store")
    if getattr(options, "store", None) is not None and options.store.exists():
        # Before an hour of generation, not after it.
        raise SystemExit(
            f"{options.store} exists: a stored process is never overwritten"
        )
    record = Run(options).run()
    if options.json:
        options.json.parent.mkdir(parents=True, exist_ok=True)
        options.json.write_text(json.dumps(record, indent=1) + "\n")
    if "generation_error" in record:
        print(record["process"], "not generated:", record["generation_error"])
        return 3
    return 0
