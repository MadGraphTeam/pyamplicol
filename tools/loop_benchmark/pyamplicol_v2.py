# SPDX-License-Identifier: 0BSD
"""pyAmpliCol v2 timing for gate G1 (DESIGN §14, REQUIREMENTS_ADDENDUM D).

One run measures one process at one colour accuracy on one checkout:

1. **Generation** (reported separately, MASTER_PLAN §5.8 item 8): the
   compiled loop_sm model (cached), ``LoopSlice.generate`` and the plan v4
   export of ``plan_export.NativeExecutor``, each with its wall time and the
   peak resident memory of that stage (``/proc/self/clear_refs`` resets the
   high-water mark between stages).
2. **Accuracy at the frozen points**: the stream's first block in the
   timed configuration, its Born and finite part against every provider of
   the committed reference (``tests/fixtures/loop/required/<key>.json``) with
   the fixture's metric; the finite parts of every timed point are kept for
   ``gate.py``'s comparison with the providers' own runs on the stream.
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
   no escalation), so its rescue rate is zero by construction.

After the timing, the same generated process can also be checked
(``--stability-points``: stability estimates as ``check_points`` makes
them, written to ``--stability-json``; ``--physical-points``: one evaluation
with every pole, its components per Laurent coefficient and Catani's
prediction of the poles), so a seven-leg process is generated once. The
``ward`` subcommand (``ward``) probes the Ward identity: one external
gluon's polarisation replaced by its momentum on the loop side.

The compiled model lives in a temporary directory under ``--scratch`` (the
system's temporary directory by default) that the run removes at its end.

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

from . import streams

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


def _request(key: str, accuracy: str, compiled: Any) -> Any:
    from pyamplicol.loops.v2.assemble import SliceRequest
    from pyamplicol.models.loop_color_declaration import LoopColorDeclaration

    process = streams.spec(key)
    text = process_text(key, compiled)
    declaration = None
    if accuracy != "full":
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from tools.loop_reference import legacy_capture

        declaration = LoopColorDeclaration.from_dict(
            json.loads(legacy_capture.COLOUR_DECLARATION.read_text())
        )
    return SliceRequest(
        text,
        dict(process["born_orders"]),
        dict(process["loop_orders"]),
        fixed_parameters=dict(process["scheme_data"]["fixed_parameters"]),
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
            "one thread on one pinned core, warm-up excluded, paired blocks",
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
        compiled = compile_loop_sm(UFO, scratch)
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

    def _install_timers(self) -> None:
        from pyamplicol.loops.v2 import assemble
        from pyamplicol.loops.v2.plan_export import NativeExecutor

        wrap = self.timers.wrap
        slice_ = self.slice
        wrap(type(slice_.tree_rows), "evaluate", "python trees")
        wrap(assemble.LoopSlice, "scalars", "python scalars")
        if slice_.counterterm_program is not None:
            wrap(
                type(slice_.counterterm_program), "point", "python counterterm program"
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
        fixture_path = streams.FIXTURES / f"{self.key}.json"
        if not fixture_path.exists() or self.options.accuracy != "full":
            self.record["accuracy_check"] = None
            return
        fixture = json.loads(fixture_path.read_text())
        count = len(fixture["points"])
        block = self.evaluate(0, count)
        alpha = float(self.parameters["aS"])
        rows = []
        worst = 0.0
        for index, (born, finite) in sorted(block["values"].items()):
            floor = abs(born) * alpha / (2 * math.pi)
            errors = {}
            for provider, values in fixture["rows"][index]["providers"].items():
                errors[provider] = {
                    "born": _relative(born, float(values["born"])),
                    "finite": _relative(finite, float(values["finite"]), floor),
                }
                worst = max(worst, *errors[provider].values())
            rows.append(
                {"index": index, "born": born, "finite": finite, "errors": errors}
            )
        self.record["accuracy_check"] = {
            "points": count,
            "metric": fixture["error_metric"],
            "tolerance": float(fixture["tolerance"]),
            "max_error": worst,
            "passed": worst <= float(fixture["tolerance"]),
            "rows": rows,
        }
        print(self.key, "accuracy vs providers: max", f"{worst:.2e}", flush=True)

    def timing(self) -> None:
        options = self.options
        batches = sorted(set(options.batches))
        warm: dict[int, float] = {}
        skipped: dict[int, str] = {}
        for size in batches:
            start = time.perf_counter()
            self.evaluate(0, size)
            warm[size] = time.perf_counter() - start
            # The warm-up includes lazy compilation; the estimate scales the
            # cheapest B per point.
        per_point = min(warm[b] / b for b in batches)
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
        runs: dict[int, list[dict[str, Any]]] = {size: [] for size, _ in planned}
        offsets = {size: 0 for size, _ in planned}
        for _round in range(options.reps):
            for size, blocks in planned:
                for _ in range(blocks):
                    run = self.evaluate(offsets[size], size)
                    offsets[size] += size
                    runs[size].append(run)
            print(self.key, "round", _round + 1, "done", flush=True)
        self.record["warm_up_seconds"] = warm
        self.record["skipped_batches"] = skipped
        self.record["batches"] = {
            str(size): _summary(runs[size]) for size, _ in planned
        }
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

    def physical(self, indices: list[int]) -> None:
        """One binary64 evaluation with every pole per stream point: the
        components per Laurent coefficient (the scale of the Ward check) and
        the poles against Catani's prediction."""

        rows = []
        for index in indices:
            points, scales = self._batch(index, 1)
            begin = time.perf_counter()
            (result,) = self.executor.evaluate(
                points, scales, parameters=self.parameters, poles=_all_poles()
            )
            born, finite = _totals(result)
            rows.append(
                {
                    "index": index,
                    "born": born,
                    "finite": finite,
                    "components": components(result),
                    "catani": catani(result),
                    "seconds": time.perf_counter() - begin,
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
            self.accuracy()
            self.timing()
            if getattr(self.options, "physical_points", None):
                self.physical(self.options.physical_points)
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


CHECKS = "rotation about z by (3/5, 4/5) and the reduction direction"


def stability_rows(run: Run, indices: list[int], arithmetics: list[str]) -> list:
    """Stream points of a generated run evaluated with one rotation about z
    by (3/5, 4/5) and the reduction-direction check, finite part only: the
    estimate E and each check's relative deviation (``checks``: the rotated
    evaluation's is the rotational-invariance test)."""

    from pyamplicol.loops.v2.assemble import Precision
    from pyamplicol.loops.v2.stability import Rotation, StabilityChecks

    precisions = {
        "double": Precision.double(),
        "double-double": Precision.double_double(),
    }
    checks = StabilityChecks(
        rotations=(Rotation.about("z", "3/5", "4/5"),), reduction_direction=True
    )
    rows = []
    for index in indices:
        points, scales = run._batch(index, 1)
        for arithmetic in arithmetics:
            begin = time.perf_counter()
            (result,) = run.executor.evaluate(
                points,
                scales,
                parameters=run.parameters,
                precision=precisions[arithmetic],
                poles=_finite_only(),
                stability=checks,
            )
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
                    "seconds_with_checks": time.perf_counter() - begin,
                }
            )
            print(run.key, json.dumps(rows[-1]), flush=True)
    return rows


def check_points(options: Any) -> int:
    """Evaluate chosen stream points with stability checks (one rotation about
    z by (3/5, 4/5) and the reduction-direction check) in the configuration
    of a run, in each arithmetic of ``--arithmetic`` (binary64 and/or
    double-double): the estimate E beside the value, for the points where the
    timed binary64 values deviate most from the providers (``gate.py``). The
    double-double values separate pyAmpliCol's binary64 loss from the
    providers' own (they read the points rounded to binary64)."""

    run = Run(options)
    try:
        run.generate()
        rows = stability_rows(run, options.points, options.arithmetic)
    finally:
        run.close()
    run.record["kind"] = "stability"
    run.record["checks"] = CHECKS
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
        compiled = compile_loop_sm(UFO, scratch)
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
        for index in options.points:
            points, scales = run._batch(index, 1)
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
    record = Run(options).run()
    if options.json:
        options.json.parent.mkdir(parents=True, exist_ok=True)
        options.json.write_text(json.dumps(record, indent=1) + "\n")
    if "generation_error" in record:
        print(record["process"], "not generated:", record["generation_error"])
        return 3
    return 0
