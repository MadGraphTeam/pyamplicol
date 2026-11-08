# SPDX-License-Identifier: 0BSD
"""Gate G1 from the benchmark records (DESIGN §14, REQUIREMENTS_ADDENDUM D).

Reads ``pyamplicol``, ``providers`` and ``stability`` records (``python -m
tools.loop_benchmark``) and writes one JSON document for the live report
(``docs/performance_reports/loop/data/g1.json``):

- per process (every recorded process of ``processes.json``, in its order;
  a record of an unknown process is refused) its label (the process text the
  pyAmpliCol run generated, else the specification's), its multiplicity
  class (the gate applies from 2->3 upward; 2->2 is reported without a gate),
  the providers' production-mode times per point and their setup (a provider
  the specification marks unavailable keeps its reason), every pyAmpliCol
  record (path, colour, B, stage split, generation, accuracy check), and the
  speed gate per pyAmpliCol configuration and B;
- the **gate statistic**: the median per point on both sides (pyAmpliCol:
  over the timed blocks of one B; providers: over the timed points of the run
  paired with the pyAmpliCol configuration, the last run of the provider in
  the record list). The gate is t < t_MadLoop and t <= 1.30 t for each
  matched Recola and OpenLoops time; with no matched provider it is "no
  matched provider timing" (never extrapolated, addendum F). A provider
  that could compute the process but whose production-mode timing is not
  obtainable under HANDOFF §0.1 (``matched`` in its specification, or an
  imported campaign timing outside the protocol, ``protocol_mode`` false) is
  *missing*: the gate is taken on the available providers (addendum D,
  "each available Recola / OpenLoops"; the verdicts published on loop, e.g.
  u u~ > g g g g without MadLoop), the missing ones are listed beside the
  verdict with their reasons (``missing``), and the timing outside the
  protocol is kept beside it as ``outside_protocol``, never in it;
- its **uncertainty** (MASTER_PLAN §5.8 item 9): the relative standard error
  of pyAmpliCol's median over its blocks (1.2533 x 1.4826 MAD / sqrt(n);
  half the range for fewer than five blocks) plus each provider's relative
  half-range over its repeated runs (for a single run, the largest
  half-range of any provider in the campaign, marked "assumed"). The time
  over the limit with that band decides: pass if the whole band passes, fail
  if the whole band fails, otherwise "inconclusive" (to be repeated once,
  item 10). The ratio with the providers' means is kept beside it;
- the **gate batch** (the user's rule of 2026-10-28, slice-status DECISIONS
  ~08:20 item 2, MASTER_PLAN §5.8 amendment): G1 is the batched
  B = ``GATE_BATCH`` (128) verdict only. Every other timed batch (B = 1, the
  2->5 rows' B = 16, any other) keeps its checks, ratios, band and
  uncertainty under the non-gating status ``GATE_REPORTED_STATUS``
  ("reported", with ``gate_batch``), the checks' own verdict as
  ``measured_status``. The 5 ms floor (the user's rule of 2026-10-24) is
  decided on the B = 128 median (``floor_bases``). A configuration's verdict
  (its ``gate``) is its B = 128 one; without a B = 128 timing it is
  ``GATE_MISSING_STATUS`` with the reason, never one taken from another
  batch size;
- a configuration measured twice (a repeat) keeps the earlier run's batch
  times as ``earlier_runs``; the later run, with its paired provider run,
  decides; a later run without an accuracy check or physical rows keeps the
  earlier run's (``checks_from_earlier_run`` names their revision); a run's
  checkpoint (``partial``: the rounds it completed) is marked as such;
- the value comparison of pyAmpliCol and the providers on the same stream
  points (Born and finite part, metric |a-b| / max(|a|, |b|, |Born|
  alpha_s/(2 pi)) for the finite part; Recola's finite part converted to
  MadLoop's convention with the universal double pole, since Recola returns
  no poles in production mode) and the stability rows (binary64 and
  double-double at the worst points; the rows at a reference fixture's own
  points, e.g. NJet's for g g > g g g g g, apart as ``fixture_stability``);
- the schedule B/M comparison on the schedule-dependent stages (seeds,
  factors, dressing, scatter, reduction) and end to end, with the design's
  adoption rule (M where at least 15 % faster, the reduction included);
- the Ward rows (``ward`` records: one gluon's polarisation replaced by its
  momentum on the loop side) divided by the physical scale of the same
  point (``physical`` rows of a pyAmpliCol record: the largest component per
  Laurent coefficient), with the binary64 bound of the O10 test
  (``WARD_RELATIVE`` of the scale, or of the R2 part where it is larger,
  plus ``WARD_LANES`` of the lanes' absolute sum), and the physical rows
  themselves (the poles against Catani's prediction);
- with ``--values-json``, a second document with the per-point values of
  every configuration and provider run, from which the comparison and the
  provider statistics can be re-derived.

Usage:
    python -m tools.loop_benchmark gate RECORD.json ... --json g1.json \\
        [--values-json g1-values.json]
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

from . import providers as provider_module
from . import streams

# The verdict of a specification with role "indicative" (``processes.json``).
INDICATIVE = "indicative: not gated (EW, m-sm/PLAN.md [U5]: the gate binds in M-FINAL)"

GATE_FACTOR = 1.30
# The user's rule of 2026-10-28 (slice-status DECISIONS ~08:20 item 2,
# MASTER_PLAN §5.8 amendment): the speed gate is taken at B = 128 only; every
# other batch is reported with its checks and ratios, without a verdict.
GATE_BATCH = 128
GATE_REPORTED_STATUS = "reported"
GATE_MISSING_STATUS = "missing"
# The user's rule of 2026-10-24 (slice-status DECISIONS ~22:35): a process
# whose pyAmpliCol batched time per point (at B = 128, ``floor_bases``) is
# below 5 ms has no blocking gate; its ratio is still shown.
GATE_FLOOR_SECONDS = 5e-3
GATE_FLOOR_STATUS = "below 5 ms: not gated (user 2026-10-24)"
ADOPT_M = 0.85
NO_PROVIDER_NOTE = (
    "no matched provider timing (HANDOFF 0.1): the speed is reported without"
    " a gate (addenda F and H); its rotation and Ward checks, or why one is"
    " pending, are summary.json's sanity_checks"
)
# The checks of a configuration's run that a later run of it without them
# keeps (``build``).
CARRIED_CHECKS = ("accuracy_check", "physical")
# The binary64 bound of the Ward test (test_loop_v2_observables, O10).
WARD_RELATIVE = 1e-11
WARD_LANES = 1e-12
WARD_PARTS = ("virtual", "uv_local", "uv_external_fields")
SCHEDULE_STAGES = ("seeds", "factors", "dressing", "scatter", "reduction")
# Loop-induced rows (``processes.json`` ``loop_induced``; m-lit PLAN §5.1,
# §5.2). The gate is taken on the loop-induced default backend TIRust (RULED
# Q35, Q40); NinjaRS per amplitude, the second mode, is reported with its
# ratios. The value metric is Born-free (|a - b| / max(|a|, |b|), PLAN §4.0
# L1) and the physical rows give the amplitude-level finiteness ratio
# instead of Catani's poles. The amplitude-mode stage split (PLAN §5.1)
# keeps these names; schedule M has no amplitude mode, so the schedule
# comparison's stages are unchanged.
INDUCED_GATE_BACKEND = "tirust"
INDUCED_METRIC = "|a - b| / max(|a|, |b|) (Born-free; m-lit PLAN §4.0 L1)"
INDUCED_STAGES = (
    "trees + CT kets",
    "seeds",
    "factors",
    "dressing",
    "scatter",
    "reduction",
    "reduction: tensor moments",
    "reduction: contraction",
    "reduction: TIR masters",
    "reduction: masters",
    "squaring",
    "transport",
    "input conversion",
    "python point parameters",
    "assembly",
    "other",
)
SECOND_MODE_STATUS = "reported (NinjaRS per amplitude: the second mode, PLAN §5.2)"
# A configuration whose B = 128 calls failed points closed: its time is a
# whole-call time, not a served-point time, so it carries no verdict; how a
# verdict is given on such a row is not ruled (the gap is a finding, with
# the served fraction and the time on the served points beside it).
FAILED_CLOSED_STATUS = "failed closed on part of the stream: no verdict (gap)"


def multiplicity(key: str) -> int:
    return len(streams.spec(key)["pdgs"]) - 2


def label(key: str) -> str:
    """The process in the specification's provider-independent particle
    names (its Recola process string); the text the pyAmpliCol run generated
    from the model's names is kept as ``process_text``."""

    spec = streams.spec(key)
    return spec["recola"]["process"].replace("->", ">")


# A block's process CPU time over its wall time (``cpu_share``, the
# loop-induced harness's, one thread): about 0.99 on a core of its own; a
# block whose core was shared, or whose job a host guard stopped, falls far
# below and its wall time is no measurement of the call. Overridable
# (``build(min_cpu_share=...)``, ``gate --min-cpu-share``).
MIN_CPU_SHARE = 0.9


def valid_blocks(summary: dict[str, Any], min_share: float) -> dict[str, Any]:
    """A batch summary on its blocks with at least ``min_share`` CPU share
    (``MIN_CPU_SHARE``): median, range and samples over those, the others
    listed (``dropped_blocks``: block index -> share); unchanged without the
    shares."""

    shares = summary.get("cpu_share")
    if not shares:
        return summary
    samples = summary["samples_seconds_per_point"]
    keep = [i for i, share in enumerate(shares) if share >= min_share]
    if len(keep) == len(samples) or not keep:
        return summary
    kept = [samples[i] for i in keep]
    out = {
        **summary,
        "samples_seconds_per_point": kept,
        "median_seconds_per_point": statistics.median(kept),
        "min_seconds_per_point": min(kept),
        "max_seconds_per_point": max(kept),
        "blocks": len(kept),
        "dropped_blocks": {
            str(i): round(share, 3)
            for i, share in enumerate(shares)
            if share < min_share
        },
    }
    if "failed_points" in summary:
        out["failed_points"] = [summary["failed_points"][i] for i in keep]
    return out


def loop_induced(key: str) -> bool:
    return bool(streams.spec(key).get("loop_induced"))


def value_annotations(key: str, record: dict[str, Any] | None) -> dict[str, dict]:
    """Per provider its value annotations (``providers.VALUE_ANNOTATIONS``:
    ``values_excluded``, the reason its values are no reference;
    ``value_exceptions``, the stream points whose values are none), from
    the specification and the provider record."""

    spec = streams.spec(key)
    known = record["providers"] if record else {}
    out: dict[str, dict] = {}
    for name in ("madloop", "recola", "openloops"):
        found = {
            field: value
            for source in (spec.get(name, {}), known.get(name, {}))
            for field, value in source.items()
            if field in provider_module.VALUE_ANNOTATIONS
        }
        if found:
            out[name] = found
    return out


def unmatched_providers(key: str, record: dict[str, Any] | None) -> dict[str, str]:
    """Providers timed on the row whose values are no reference
    (``values_excluded``): not matched providers of the gate. A matched
    provider evaluates the row's process in its scheme, its values within
    the L1 rule (m-lit PLAN §4.0; §4.1 names the providers of each row):
    one excluded by its own value record (e.g. Recola's on-shell width
    convention on the fixed-width rows LI-43 and LI-51) is timed and
    reported beside the verdict, never a limit."""

    return {
        name: found["values_excluded"]
        for name, found in value_annotations(key, record).items()
        if found.get("values_excluded")
    }


def median_uncertainty(samples: list[float]) -> float:
    """Relative standard error of the median of ``samples`` (module
    docstring)."""

    if len(samples) < 2:
        return 0.0
    median = statistics.median(samples)
    if len(samples) < 5:
        return (max(samples) - min(samples)) / (2 * median)
    mad = statistics.median(abs(x - median) for x in samples)
    return 1.2533 * 1.4826 * mad / math.sqrt(len(samples)) / median


def half_range(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    middle = statistics.median(values)
    return (max(values) - min(values)) / (2 * middle)


def gate_verdict(
    seconds: float,
    times: dict[str, float],
    *,
    uncertainty: float = 0.0,
    reference_uncertainty: dict[str, tuple[float, bool]] | None = None,
    means: dict[str, float] | None = None,
    missing: dict[str, str] | None = None,
    outside: dict[str, dict[str, Any]] | None = None,
    floor_basis: float | None = None,
    batch: int = GATE_BATCH,
    unmatched: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The speed gate of one pyAmpliCol time against the matched providers.

    ``uncertainty``: pyAmpliCol's relative uncertainty; ``reference_uncertainty``:
    per provider (relative uncertainty, assumed). The verdict of each check is
    taken on the band ratio x (1 -+ u), u the sum of both. ``missing``: the
    matched providers without a protocol-mode timing (reason); ``outside``:
    their timings outside the protocol (seconds, mode), reported as ratios
    beside the verdict. ``batch``: the time's batch size; at any other than
    ``GATE_BATCH`` the time is reported, not gated (the user's rule of
    2026-10-28): its status is ``GATE_REPORTED_STATUS`` with every check and
    ratio kept and the checks' own verdict as ``measured_status``. A batched
    time below ``GATE_FLOOR_SECONDS`` is not gated (the user's rule of
    2026-10-24): its verdict is ``GATE_FLOOR_STATUS``, the checks' own as
    ``measured_status``. ``floor_basis`` is that batched time (``floor_bases``:
    the configuration's at B = 128), ``seconds`` by default. ``unmatched``:
    the providers timed on the row that are no matched provider
    (``unmatched_providers``: seconds and reason), reported as ratios beside
    the verdict."""

    verdict = _verdict(
        seconds,
        times,
        uncertainty=uncertainty,
        reference_uncertainty=reference_uncertainty,
        means=means,
        missing=missing,
        outside=outside,
    )
    if unmatched:
        verdict["not_matched"] = {
            name: {**value, "ratio": seconds / value["seconds"]}
            for name, value in unmatched.items()
        }
    if batch != GATE_BATCH:
        return {
            **verdict,
            "status": GATE_REPORTED_STATUS,
            "measured_status": verdict["status"],
            "gate_batch": GATE_BATCH,
        }
    basis = seconds if floor_basis is None else floor_basis
    if basis < GATE_FLOOR_SECONDS:
        # Below the floor the checks and ratios stay, the verdict does not
        # block; ``measured_status`` keeps what the checks alone say.
        return {
            **verdict,
            "status": GATE_FLOOR_STATUS,
            "measured_status": verdict["status"],
            "floor_seconds": GATE_FLOOR_SECONDS,
            "floor_basis_seconds": basis,
        }
    return verdict


def floor_bases(configurations: dict[str, dict[str, Any]]) -> dict[str, float | None]:
    """The batched time per point that decides the 5 ms floor of each
    configuration of a process (the user's rule concerns the batched time):
    its median at B = ``GATE_BATCH``, the only batch with a verdict; None
    without a B = 128 timing (no verdict, ``configuration_gate``)."""

    return {
        name: record.get("batches", {})
        .get(str(GATE_BATCH), {})
        .get("median_seconds_per_point")
        for name, record in configurations.items()
    }


def configuration_gate(
    record: dict[str, Any], batches: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """The G1 verdict of one configuration: its B = ``GATE_BATCH`` verdict
    (``batch``, ``status``; the checks are that batch's ``gate``). Without a
    B = 128 timing a gated configuration has none (``GATE_MISSING_STATUS``
    with the reason); the verdict of another batch is never taken."""

    if str(GATE_BATCH) in batches:
        return {
            "batch": GATE_BATCH,
            "status": batches[str(GATE_BATCH)]["gate"]["status"],
        }
    if record.get("generation_error"):
        why = f"generation refused: {record['generation_error'].split(':')[0]}"
    elif str(GATE_BATCH) in record.get("skipped_batches", {}):
        why = f"skipped: {record['skipped_batches'][str(GATE_BATCH)]}"
    else:
        timed = ", ".join(str(size) for size in sorted(map(int, batches))) or "none"
        why = f"timed at B = {timed}"
    return {
        "status": GATE_MISSING_STATUS,
        "reason": f"no B = {GATE_BATCH} timing ({why}); G1 is taken at "
        f"B = {GATE_BATCH} only (user 2026-10-28)",
    }


def induced_verdict(
    verdict: dict[str, Any],
    summary: dict[str, Any],
    effective: str | None,
    served: dict[str, Any] | None,
    times: dict[str, float],
) -> dict[str, Any]:
    """A loop-induced configuration's verdict at one batch (module
    constants): on the gate backend (``INDUCED_GATE_BACKEND``) the gate's
    own, unless a block failed points closed (``FAILED_CLOSED_STATUS``: the
    whole-call ratio and, where timed, the ratio of the time on the served
    points beside it, ``measured_status`` the checks'); on the other backend
    the ratios reported (``SECOND_MODE_STATUS``)."""

    failed = summary.get("failed_points") or []
    if any(failed) and verdict["status"] in (GATE_FLOOR_STATUS, GATE_REPORTED_STATUS):
        # Not gated anyway (the 5 ms rule, or not the gate batch): the
        # failed points are stated beside the status.
        points = summary["points_per_block"]
        verdict = {
            **verdict,
            "failed_points": failed,
            "served_fraction": 1 - sum(failed) / (points * len(failed)),
            "whole_call": True,
        }
        failed = []
    if any(failed):
        points = summary["points_per_block"]
        out = {
            key: value
            for key, value in verdict.items()
            if key
            not in (
                "ratio_to_binding_limit",
                "band_to_binding_limit",
                "ratio_to_fastest",
                "ratio_to_binding_limit_of_means",
                "central",
            )
        }
        out.update(
            status=FAILED_CLOSED_STATUS,
            measured_status=verdict["status"],
            failed_points=failed,
            served_fraction=1 - sum(failed) / (points * len(failed)),
            failure_causes=summary.get("failure_causes", {}),
            whole_call_seconds_per_point=summary["median_seconds_per_point"],
        )
        if "ratio_to_binding_limit" in verdict:
            out["whole_call_ratio_to_binding_limit"] = verdict["ratio_to_binding_limit"]
        if served is not None and "binding_limit" in verdict:
            t = served["median_seconds_per_point"]
            out["served_points"] = {
                "points": served["points_per_block"],
                "seconds_per_point": t,
                "ratio_to_binding_limit": t / verdict["binding_limit"],
                "batch": served["points_per_block"],
            }
        if effective != INDUCED_GATE_BACKEND:
            out["status"] = SECOND_MODE_STATUS
            out["failed_closed"] = True
        return out
    if effective != INDUCED_GATE_BACKEND and verdict["status"] not in (
        GATE_REPORTED_STATUS,
    ):
        return {
            **verdict,
            "status": SECOND_MODE_STATUS,
            "measured_status": verdict.get("measured_status", verdict["status"]),
        }
    return verdict


def finiteness(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The finiteness column of a loop-induced configuration (instead of
    Catani's poles): over its physical rows the largest amplitude-level
    finiteness ratio (``PointResult.finiteness``: the largest ||a_-k||_G /
    S_k over loop orders, rows and k) and the largest finite-part estimate
    E, the points it failed closed counted."""

    served = [row for row in rows if "finiteness" in row]
    if not rows:
        return None
    ratios = [row["finiteness"] for row in served if row["finiteness"] is not None]
    return {
        "points": len(served),
        "failed_points": len(rows) - len(served),
        "max_finiteness": max(ratios, default=None),
        "max_estimate": max(
            (row["estimate"] for row in served if row.get("estimate") is not None),
            default=None,
        ),
    }


def _verdict(
    seconds: float,
    times: dict[str, float],
    *,
    uncertainty: float,
    reference_uncertainty: dict[str, tuple[float, bool]] | None,
    means: dict[str, float] | None,
    missing: dict[str, str] | None,
    outside: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    """The verdict of the checks alone (``gate_verdict`` without the floor)."""

    missing = missing or {}
    extra: dict[str, Any] = {}
    if missing:
        extra["missing"] = dict(missing)
    if outside:
        extra["outside_protocol"] = {
            name: {**value, "ratio": seconds / value["seconds"]}
            for name, value in outside.items()
        }
    if not times:
        return {"status": "no matched provider timing", **extra}
    reference_uncertainty = reference_uncertainty or {}
    checks = {}
    for provider, reference in times.items():
        limit = reference if provider == "madloop" else GATE_FACTOR * reference
        strict = provider == "madloop"
        ratio = seconds / limit
        u_ref, assumed = reference_uncertainty.get(provider, (0.0, True))
        u = uncertainty + u_ref
        low, high = ratio * (1 - u), ratio * (1 + u)
        if (high < 1) if strict else (high <= 1):
            status = "pass"
        elif (low >= 1) if strict else (low > 1):
            status = "fail"
        else:
            status = "inconclusive"
        checks[provider] = {
            "reference": reference,
            "limit": limit,
            "ratio_to_limit": ratio,
            "band": [low, high],
            "uncertainty": u,
            "reference_uncertainty": u_ref,
            "reference_uncertainty_assumed": assumed,
            "passed": (seconds < limit) if strict else (seconds <= limit),
            "status": status,
        }
    states = {c["status"] for c in checks.values()}
    if "fail" in states:
        status = "fail"
    elif "inconclusive" in states:
        status = "inconclusive"
    else:
        status = "pass"
    fastest = min(times, key=times.get)
    binding = min(checks, key=lambda name: checks[name]["limit"])
    verdict = {
        "status": status,
        **extra,
        "central": "pass" if all(c["passed"] for c in checks.values()) else "fail",
        "statistic": "median per point (pyAmpliCol blocks, provider points)",
        "checks": checks,
        "fastest_provider": fastest,
        "ratio_to_fastest": seconds / times[fastest],
        "binding_provider": binding,
        "binding_limit": checks[binding]["limit"],
        "ratio_to_binding_limit": checks[binding]["ratio_to_limit"],
        "band_to_binding_limit": checks[binding]["band"],
    }
    if means:
        limits = [
            means[n] if n == "madloop" else GATE_FACTOR * means[n]
            for n in times
            if n in means
        ]
        if limits:
            verdict["ratio_to_binding_limit_of_means"] = seconds / min(limits)
    return verdict


def _provider_values(key: str, record: dict[str, Any]) -> dict[str, dict[int, tuple]]:
    """(born, finite in MadLoop's convention) per provider and stream index."""

    spec = streams.spec(key)
    # Recola's finite part takes pi^2/6 x the universal double pole, which
    # ``universal_double_pole`` implements for QCD only; for an EW
    # correction (the indicative EW row; QED has double poles where charged
    # legs are massless) that conversion is not implemented, so its Recola
    # values are not compared (MadLoop's and OpenLoops' are).
    # A loop-induced row has no Born: its |A|^2 has no universal pole to
    # convert (Recola's finite part is MadLoop's).
    factor = (
        0.0
        if spec.get("loop_induced")
        else provider_module.universal_double_pole(spec)
        if spec["correction"] == "QCD"
        else None
    )
    out: dict[str, dict[int, tuple]] = {}
    for name, result in record["providers"].items():
        rows = result.get("rows")
        if not rows or (name == "recola" and factor is None):
            continue
        values = {}
        for index, row in enumerate(rows):
            finite = row["finite"]
            if name == "recola":
                raw = row["raw"]["finite"]
                finite = raw + math.pi**2 / 6 * factor * row["born"]
            values[index] = (row["born"], finite)
        out[name] = values
    return out


def _madloop_generation(export: Path | None) -> dict[str, Any] | None:
    """Graph generation, Fortran export and compilation seconds of a MadLoop
    export (``madloop_export.py``'s ``<export>.generation.json``)."""

    if export is None:
        return None
    path = export.parent / f"{export.name}.generation.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    keys = ("graph_generation_s", "source_export_s", "compile_s")
    if not all(isinstance(data.get(key), int | float) for key in keys):
        return None
    return {key: data[key] for key in keys} | {
        "total_s": sum(data[key] for key in keys),
        "loops": data.get("loops"),
    }


def compare_values(
    key: str,
    mine: dict[int, tuple],
    theirs: dict[str, dict[int, tuple]],
    annotations: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """pyAmpliCol's values against each provider's on the common stream
    points: the Born and the finite part (metric |a - b| / max(|a|, |b|,
    |Born| alpha_s/(2 pi)); for a loop-induced row Born-free, ``INDUCED_
    METRIC``). A provider whose values are excluded (``values_excluded``)
    is not compared, its reason kept; the points of its ``value_exceptions``
    are left out, listed."""

    alpha = float(streams.spec(key)["scheme_data"]["parameters"]["aS"])
    annotations = annotations or {}
    result: dict[str, Any] = {}
    for provider, values in theirs.items():
        notes = annotations.get(provider, {})
        if notes.get("values_excluded"):
            result[provider] = {"excluded": notes["values_excluded"]}
            continue
        excepted = set((notes.get("value_exceptions") or {}).get("points", ()))
        common = sorted((set(values) & set(mine)) - excepted)
        if not common:
            continue
        born_dev, finite_dev = 0.0, 0.0
        worst = None
        deviations = []
        for index in common:
            b0, f0 = mine[index]
            b1, f1 = values[index]
            floor = abs(b0) * alpha / (2 * math.pi)
            db = abs(b0 - b1) / max(abs(b0), abs(b1)) if (b0 or b1) else 0.0
            df = abs(f0 - f1) / max(abs(f0), abs(f1), floor) if (f0 or f1) else 0.0
            born_dev = max(born_dev, db)
            deviations.append(df)
            if df >= finite_dev:
                finite_dev, worst = df, index
        result[provider] = {
            "points": len(common),
            "max_born_deviation": born_dev,
            "max_finite_deviation": finite_dev,
            "median_finite_deviation": statistics.median(deviations),
            "worst_point": worst,
            **({"metric": INDUCED_METRIC} if loop_induced(key) else {}),
            **(
                {
                    "excepted_points": sorted(excepted & set(values)),
                    "exception": notes["value_exceptions"].get("reason"),
                }
                if excepted
                else {}
            ),
        }
    return result


def _times(record: dict[str, Any] | None, field: str) -> dict[str, float]:
    """Protocol-mode times (an imported campaign timing outside the protocol
    is not one, ``providers.imported``)."""

    if record is None:
        return {}
    return {
        name: result[field]
        for name, result in record["providers"].items()
        if field in result and result.get("protocol_mode", True)
    }


def missing_providers(key: str, record: dict[str, Any] | None) -> dict[str, str]:
    """Matched providers without a protocol-mode timing, with the reason
    (module docstring): ``matched`` and ``unavailable`` in the specification,
    or only a timing outside the protocol."""

    spec = streams.spec(key)
    known = record["providers"] if record else {}
    out = {}
    for name in ("madloop", "recola", "openloops"):
        entry = spec.get(name, {})
        result = known.get(name, {})
        if "median_seconds_per_point" in result and result.get("protocol_mode", True):
            continue
        if entry.get("matched") and "unavailable" in entry:
            out[name] = entry["unavailable"]
        elif result.get("protocol_mode") is False:
            out[name] = result.get("mode", "timing outside the protocol")
    return out


def outside_protocol(record: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Imported timings outside the protocol: median seconds and mode, and
    the reason where the time bounds the provider's production time from
    above (``providers.imported``: never a limit)."""

    if record is None:
        return {}
    return {
        name: {
            "seconds": result["median_seconds_per_point"],
            "mode": result["mode"],
            **(
                {"production_upper_bound": result["production_upper_bound"]}
                if "production_upper_bound" in result
                else {}
            ),
        }
        for name, result in record["providers"].items()
        if result.get("protocol_mode") is False and "median_seconds_per_point" in result
    }


def _configuration(record: dict[str, Any]) -> str:
    parts = [record["inputs"], record["accuracy"]]
    if record.get("schedule", "B") != "B":
        parts.append("M")
    if record.get("lanes", 16) != 16:
        parts.append(f"L{record['lanes']}")
    return "/".join(parts)


def configurations_of(record: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """The configurations of a pyAmpliCol record: the record itself, or for
    a loop-induced run (``InducedRun``: ``backend_runs``) one per requested
    reduction backend, named ``<inputs>/<accuracy>/<requested>``, each with
    its request as the runtime resolved it (``reduction``: requested,
    effective, reason), its batches, its served-points and profiled arms
    and its own accuracy check."""

    runs = record.get("backend_runs")
    if runs is None:
        return [(_configuration(record), record)]
    base = {k: v for k, v in record.items() if k not in ("backend_runs", "batches")}
    check = record.get("accuracy_check") or {}
    out = []
    for requested, run in runs.items():
        out.append(
            (
                f"{_configuration(record)}/{requested}",
                {
                    **base,
                    "reduction": {
                        k: run[k]
                        for k in ("requested", "effective", "reason", "refused")
                        if k in run
                    },
                    "batches": run.get("batches", {}),
                    "served": run.get("served", {}),
                    "profiled": run.get("profiled", {}),
                    "accuracy_check": None
                    if not check
                    else {
                        **{k: v for k, v in check.items() if k != "backends"},
                        **check.get("backends", {}).get(requested, {}),
                    },
                    "physical": [
                        row
                        for row in record.get("physical", [])
                        if row.get("requested") == requested
                    ],
                },
            )
        )
    return out


def _schedule_stages(batch: dict[str, Any]) -> float:
    stages = batch["stages_per_point"]
    return sum(stages.get(name, 0.0) for name in SCHEDULE_STAGES)


def schedule_comparison(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """M against B per colour accuracy and common batch: the schedule-
    dependent stages (``SCHEDULE_STAGES``, the reduction included) and end to
    end; M is adopted where it is at least 15 % faster on the schedule-
    dependent stages at every common batch (DESIGN §1.6 item 5)."""

    rows = []
    for name, config in entry.items():
        if not name.endswith("/M"):
            continue
        base = entry.get(name[: -len("/M")])
        if base is None:
            continue
        batches = sorted(set(config["batches"]) & set(base["batches"]), key=int)
        per_batch = {}
        for size in batches:
            b, m = base["batches"][size], config["batches"][size]
            per_batch[size] = {
                "schedule_stages_b": _schedule_stages(b),
                "schedule_stages_m": _schedule_stages(m),
                "schedule_stages_ratio": _schedule_stages(m) / _schedule_stages(b),
                "total_b": b["median_seconds_per_point"],
                "total_m": m["median_seconds_per_point"],
                "total_ratio": m["median_seconds_per_point"]
                / b["median_seconds_per_point"],
                "uncertainty": median_uncertainty(b["samples_seconds_per_point"])
                + median_uncertainty(m["samples_seconds_per_point"]),
            }
        if not per_batch:
            continue
        ratios = [row["schedule_stages_ratio"] for row in per_batch.values()]
        rows.append(
            {
                "configuration": name[: -len("/M")],
                "accuracy": config["accuracy"],
                "batches": per_batch,
                "adopt_m": all(r <= ADOPT_M for r in ratios),
                "rule": f"M/B <= {ADOPT_M} on the schedule-dependent stages at every "
                "common batch",
            }
        )
    return rows


def ward_rows(rows: list[dict[str, Any]], physical: list[dict[str, Any]]) -> list:
    """The Ward rows against the physical scale of their point (module
    docstring); a row without a physical evaluation of its point keeps no
    ratio."""

    scales = {}
    for row in physical:
        if "components" not in row:
            # A loop-induced physical row of a point its backend failed
            # closed: no scale.
            continue
        width = max(len(v) for v in row["components"].values())
        scales[row["index"]] = [
            max(v[k] for v in row["components"].values() if k < len(v))
            for k in range(width)
        ]
    out = []
    for row in rows:
        scale = scales.get(row["index"])
        entry = {**row, "scale": scale}
        if scale is not None:
            parts = row["components"]
            r2 = parts.get("r2", [0.0] * len(scale))
            lanes = row.get("lanes") or [0.0] * len(scale)
            bound = [
                WARD_RELATIVE * max(scale[k], r2[k] if k < len(r2) else 0.0)
                + WARD_LANES * (lanes[k] if k < len(lanes) else 0.0)
                for k in range(len(scale))
            ]
            entry["bound"] = bound
            entry["ratios"] = {
                name: [v / scale[k] for k, v in enumerate(values) if k < len(scale)]
                for name, values in parts.items()
            }
            entry["lanes_ratio"] = [
                v / scale[k] for k, v in enumerate(lanes) if k < len(scale)
            ]
            entry["passed"] = all(
                parts[name][k] <= bound[k]
                for name in WARD_PARTS
                if name in parts
                for k in range(min(len(scale), len(parts[name])))
            )
        out.append(entry)
    return out


def _values_of(summary: dict[str, Any]) -> dict[int, tuple]:
    return {int(i): tuple(v) for i, v in summary.get("values", {}).items()}


def build(
    paths: list[Path],
    reference_root: Path | None = None,
    host_spread: float | None = None,
    min_cpu_share: float = MIN_CPU_SHARE,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The gate document and the per-point values document. Provider files
    are resolved relative to ``reference_root`` only (``_export_of``): the
    absolute paths stored in the records are never read.

    A provider without repeats is assigned the host's provider spread: the
    largest half-range of this run's provider repeats, or ``host_spread``
    where that is larger (another campaign's ``host_provider_spread`` on the
    same host, for a run whose own providers have no repeats: the EW row
    gated beside G1)."""

    records = [json.loads(path.read_text()) for path in paths]
    order = streams.keys()
    processes: dict[str, dict[str, Any]] = {}
    for record in records:
        key = record["process"]
        if key not in order:
            raise KeyError(f"{key}: a record of a process not in processes.json")
        if record.get("generate_only"):
            # A storing run (``pyamplicol --store --generate-only``) times
            # nothing: its generation is in the records of the runs that
            # load it (``stored``).
            raise ValueError(
                f"{key}: a generate-only record is no gate input; give the runs "
                "of its stored process"
            )
        entry = processes.setdefault(
            key,
            {
                "key": key,
                "text": None,
                "pyamplicol": {},
                "providers": None,
                "repeats": {},
                "provider_runs": [],
            },
        )
        if record["kind"] == "ward":
            entry.setdefault("ward", []).extend(
                {**row, "revision": record["revision"]} for row in record["rows"]
            )
            entry.setdefault("ward_runs", []).append(
                {
                    "revision": record["revision"],
                    "native": record.get("native"),
                    "generation": record.get("generation"),
                    "max_rss_gib": record.get("max_rss_gib"),
                }
            )
            # A Ward run's own evaluations without the substitution (``ward
            # --physical``) are physical scales of its points too.
            entry.setdefault("ward_physical", []).extend(record.get("physical", []))
            continue
        if record["kind"] == "stability":
            # A later record's row of the same point, arithmetic and
            # configuration replaces an earlier one. The rows of a record at
            # the reference fixture's points (``stability --fixture``) are
            # indexed by the fixture, not the stream: they stay apart
            # (``fixture_stability``), with their deviations from the
            # fixture's references.
            fixture = record.get("fixture")
            rows = entry.setdefault(
                "stability" if fixture is None else "fixture_stability", []
            )

            def identity(r: dict[str, Any]) -> tuple:
                return (
                    r.get("fixture"),
                    r["index"],
                    r["arithmetic"],
                    r["configuration"],
                )

            for row in record["rows"]:
                new = {
                    "arithmetic": "double",
                    **row,
                    **({"fixture": fixture} if fixture is not None else {}),
                    "configuration": _configuration(record),
                    "revision": record["revision"],
                }
                rows[:] = [r for r in rows if identity(r) != identity(new)]
                rows.append(new)
            continue
        if record["kind"] == "providers":
            entry["provider_runs"].append(record)
            # A later record of the same provider (the run paired with the
            # pyAmpliCol configuration) replaces an earlier one; every run's
            # median and mean are kept as repeats.
            for name, result in record["providers"].items():
                if "mean_seconds_per_point" in result:
                    entry["repeats"].setdefault(name, []).append(
                        {
                            "cpu": result.get("cpu", record["cpu"]),
                            "median_seconds_per_point": result[
                                "median_seconds_per_point"
                            ],
                            "mean_seconds_per_point": result["mean_seconds_per_point"],
                            "points": result["points"],
                        }
                    )
            if entry["providers"] is None:
                entry["providers"] = json.loads(json.dumps(record))
            else:
                known = entry["providers"]["providers"]
                for name, result in record["providers"].items():
                    if "mean_seconds_per_point" not in result:
                        known.setdefault(name, result)
                        continue
                    # Keep an earlier run's stage split (instrumented MadLoop).
                    stages = known.get(name, {}).get("stages")
                    known[name] = {
                        **({"stages": stages} if stages else {}),
                        **result,
                        "cpu": result.get("cpu", record["cpu"]),
                    }
                entry["providers"]["cpu"] = record["cpu"]
            for result in entry["providers"]["providers"].values():
                result.setdefault("cpu", entry["providers"]["cpu"])
        else:
            entry["text"] = entry["text"] or record.get("process_text")
            for name, record in configurations_of(record):  # noqa: B020
                earlier = entry["pyamplicol"].get(name)
                if earlier is not None:
                    record["earlier_runs"] = [
                        *earlier.get("earlier_runs", []),
                        {
                            "revision": earlier["revision"],
                            "host_cpus": earlier.get("host_cpus"),
                            "batches": {
                                size: {
                                    k: summary[k]
                                    for k in (
                                        "median_seconds_per_point",
                                        "min_seconds_per_point",
                                        "max_seconds_per_point",
                                        "samples_seconds_per_point",
                                    )
                                }
                                for size, summary in earlier.get("batches", {}).items()
                            },
                        },
                    ]
                    # A repeat that times another batch only (the seven-gluon
                    # row's B = 64 after B = 16) keeps the earlier run's checks
                    # of the same configuration, with the run they come from.
                    for check in CARRIED_CHECKS:
                        if not record.get(check) and earlier.get(check):
                            record[check] = earlier[check]
                            record.setdefault("checks_from_earlier_run", {})[check] = (
                                earlier.get("checks_from_earlier_run", {}).get(check)
                                or earlier["revision"]
                            )
                entry["pyamplicol"][name] = record
    spreads = [
        half_range([r["median_seconds_per_point"] for r in runs])
        for entry in processes.values()
        for runs in entry["repeats"].values()
    ]
    own_spread = max((s for s in spreads if s is not None), default=0.0)
    assumed_spread = host_spread
    host_spread = (
        own_spread if assumed_spread is None else max(own_spread, assumed_spread)
    )
    out = []
    values_document: dict[str, Any] = {"processes": {}}
    for key in order:
        entry = processes.get(key)
        if entry is None:
            continue
        legs = multiplicity(key)
        # A specification with role "indicative" (the M-SM EW row: timed and
        # reported, its gate binds in M-FINAL, m-sm/PLAN.md [U5]) is not gated.
        indicative = streams.spec(key).get("role") == "indicative"
        # A provider whose values are no reference is no matched provider:
        # its time is reported beside the verdict (``unmatched_providers``).
        unmatched_reasons = unmatched_providers(key, entry["providers"])
        timed = _times(entry["providers"], "median_seconds_per_point")
        times = {n: t for n, t in timed.items() if n not in unmatched_reasons}
        unmatched = {
            n: {"seconds": timed[n], "reason": why}
            for n, why in unmatched_reasons.items()
            if n in timed
        }
        means = {
            n: t
            for n, t in _times(entry["providers"], "mean_seconds_per_point").items()
            if n not in unmatched_reasons
        }
        annotations = value_annotations(key, entry["providers"])
        induced_row = loop_induced(key)
        missing = missing_providers(key, entry["providers"])
        outside = outside_protocol(entry["providers"])
        reference_uncertainty = {}
        for name in times:
            spread = half_range(
                [r["median_seconds_per_point"] for r in entry["repeats"].get(name, [])]
            )
            reference_uncertainty[name] = (
                (host_spread, True) if spread is None else (spread, False)
            )
        provider_values = (
            _provider_values(key, entry["providers"]) if entry["providers"] else {}
        )
        configurations = {}
        point_values: dict[str, Any] = {}
        bases = floor_bases(entry["pyamplicol"])
        for name, record in entry["pyamplicol"].items():
            batches = {}
            mine: dict[int, tuple] = {}
            ungated = None
            if legs < 3:
                ungated = "no gate (2->2)"
            elif indicative:
                ungated = INDICATIVE
            elif record["accuracy"] != "full":
                # Providers time full colour: LC/NLC carry no ratio.
                ungated = "no gate (colour approximation)"
            effective = (record.get("reduction") or {}).get("effective")
            if induced_row:
                # Only the blocks that had their core (``valid_blocks``).
                record["batches"] = {
                    size: valid_blocks(summary, min_cpu_share)
                    for size, summary in record.get("batches", {}).items()
                }
                for arm in ("served", "profiled"):
                    record[arm] = {
                        size: valid_blocks(summary, min_cpu_share)
                        for size, summary in (record.get(arm) or {}).items()
                    }
            for size, summary in record.get("batches", {}).items():
                samples = summary["samples_seconds_per_point"]
                uncertainty = median_uncertainty(samples)
                if ungated is not None:
                    verdict = {"status": ungated}
                else:
                    verdict = gate_verdict(
                        summary["median_seconds_per_point"],
                        times,
                        uncertainty=uncertainty,
                        reference_uncertainty=reference_uncertainty,
                        means=means,
                        missing=missing,
                        outside=outside,
                        floor_basis=bases[name],
                        batch=int(size),
                        unmatched=unmatched,
                    )
                    if induced_row:
                        verdict = induced_verdict(
                            verdict,
                            summary,
                            effective,
                            (record.get("served") or {}).get(size),
                            times,
                        )
                for index, value in _values_of(summary).items():
                    mine.setdefault(index, value)
                # The per-point values go to the values document.
                batches[size] = {
                    **{k: v for k, v in summary.items() if k != "values"},
                    "uncertainty": uncertainty,
                    "gate": verdict,
                }
            point_values[name] = {str(i): list(v) for i, v in sorted(mine.items())}
            accuracy_check = record.get("accuracy_check")
            configurations[name] = {
                "revision": record["revision"],
                "branch": record["branch"],
                "dirty": record["dirty"],
                "host_cpus": record.get("host_cpus"),
                **({"host": record["host"]} if "host" in record else {}),
                **({"date": record["date"]} if "date" in record else {}),
                **(
                    {"eval_peak_gib": record["eval_peak_gib"]}
                    if "eval_peak_gib" in record
                    else {}
                ),
                "native": record.get("native"),
                "inputs": record["inputs"],
                "accuracy": record["accuracy"],
                "schedule": record.get("schedule", "B"),
                "lanes": record.get("lanes", 16),
                "generation": record.get("generation"),
                # A run of a stored process (``pyamplicol --load``): its
                # generation is the storing run's, the load is stated.
                **({"stored": record["stored"]} if "stored" in record else {}),
                "structure": record.get("structure"),
                "accuracy_check": accuracy_check,
                "physical": record.get("physical", []),
                "skipped_batches": record.get("skipped_batches", {}),
                "max_rss_gib": record.get("max_rss_gib"),
                "generation_error": record.get("generation_error"),
                "failed_points": {
                    size: summary.get("failed_points", [0])
                    for size, summary in record.get("batches", {}).items()
                }
                if induced_row
                else 0,
                **(
                    {
                        "reduction": record.get("reduction"),
                        "served": record.get("served") or {},
                        "profiled": record.get("profiled") or {},
                        "finiteness": finiteness(record.get("physical", [])),
                        "stages": {
                            size: {
                                stage: summary["stages_per_point"][stage]
                                for stage in INDUCED_STAGES
                                if stage in summary["stages_per_point"]
                            }
                            for size, summary in record.get("batches", {}).items()
                        },
                    }
                    if induced_row
                    else {}
                ),
                "rescue": "off (no stability check, no escalation)",
                "earlier_runs": record.get("earlier_runs", []),
                **(
                    {"checks_from_earlier_run": record["checks_from_earlier_run"]}
                    if "checks_from_earlier_run" in record
                    else {}
                ),
                # A run's checkpoint (written after every round but the last)
                # standing for a run that did not finish: its batches hold the
                # completed rounds (``blocks``).
                **({"partial": True} if record.get("partial") else {}),
                # The configuration's G1 verdict: its B = 128 one (module
                # docstring, the gate batch).
                "gate": {"status": ungated}
                if ungated is not None
                else configuration_gate(record, batches),
                "batches": batches,
                "values_vs_providers": compare_values(
                    key, mine, provider_values, annotations
                )
                if record["accuracy"] == "full"
                else None,
            }
        alpha = float(streams.spec(key)["scheme_data"]["parameters"]["aS"])
        for row in entry.get("stability", []):
            # The finite part at this point against each provider (finite
            # metric): binary64 and double-double separate pyAmpliCol's
            # binary64 loss from the providers' own.
            row["deviation_vs_providers"] = {
                name: abs(row["finite"] - values[row["index"]][1])
                / max(
                    abs(row["finite"]),
                    abs(values[row["index"]][1]),
                    abs(row["born"]) * alpha / (2 * math.pi),
                )
                for name, values in provider_values.items()
                if row["index"] in values
            }
        provider_summary = None
        if entry["providers"] is not None:
            provider_summary = {
                name: {k: v for k, v in result.items() if k != "rows"}
                for name, result in entry["providers"]["providers"].items()
            }
            madloop = provider_summary.get("madloop")
            if madloop and (
                "export" in madloop
                # An imported campaign timing (``providers.imported``) names
                # no export: its generation is the specification's export's.
                or ("imported_from" in madloop and _specified_export(key))
            ):
                export, name = _export_of(
                    key, madloop.get("export", ""), reference_root
                )
                madloop["generation"] = _madloop_generation(export)
                madloop["export"] = name
        values_document["processes"][key] = {
            "pyamplicol": point_values,
            "providers": [
                {
                    "cpu": run["cpu"],
                    "providers": {
                        name: [
                            {
                                "index": index,
                                "born": row["born"],
                                "finite": row["finite"],
                                **(
                                    {"raw_finite": row["raw"]["finite"]}
                                    if "raw" in row
                                    else {}
                                ),
                                "seconds": row["seconds"],
                            }
                            for index, row in enumerate(result.get("rows") or [])
                        ]
                        for name, result in run["providers"].items()
                    },
                }
                for run in entry["provider_runs"]
            ],
        }
        out.append(
            {
                "key": key,
                "label": label(key),
                "process_text": entry["text"],
                "outgoing": legs,
                # From 2 -> 3 upward, wherever a provider timing exists: with
                # none (g g > g g g g g, every provider beyond HANDOFF 0.1)
                # the speed is reported without a gate (addenda F and H).
                "gated": legs >= 3 and bool(times) and not indicative,
                **({"not_matched": unmatched} if unmatched else {}),
                **(
                    {"loop_induced": True, "gate_backend": INDUCED_GATE_BACKEND}
                    if induced_row
                    else {}
                ),
                **({"gate_note": NO_PROVIDER_NOTE} if legs >= 3 and not times else {}),
                "providers": provider_summary,
                "provider_cpu": entry["providers"]["cpu"]
                if entry["providers"]
                else None,
                "provider_repeats": entry["repeats"],
                "provider_uncertainty": {
                    name: {"relative": u, "assumed": assumed}
                    for name, (u, assumed) in reference_uncertainty.items()
                },
                "stability": entry.get("stability", []),
                **(
                    {"fixture_stability": entry["fixture_stability"]}
                    if entry.get("fixture_stability")
                    else {}
                ),
                "ward": ward_rows(
                    entry.get("ward", []),
                    [
                        row
                        for config in configurations.values()
                        if config["accuracy"] == "full"
                        for row in config["physical"]
                    ]
                    + entry.get("ward_physical", []),
                ),
                "ward_runs": entry.get("ward_runs", []),
                "schedules": schedule_comparison(configurations),
                "pyamplicol": configurations,
            }
        )
    document = {
        "gate_factor": GATE_FACTOR,
        "host_provider_spread": host_spread,
        "processes": out,
    }
    if assumed_spread is not None:
        document["host_provider_spread_of_run"] = own_spread
    if str(streams.ROOT) not in sys.path:
        sys.path.insert(0, str(streams.ROOT))
    from tools.loop_v2_costmodel import g1_estimates, g1_recalibration

    document["recalibration"] = g1_recalibration(document)
    document["estimates"] = g1_estimates(document)
    return document, values_document


def _export_of(key: str, recorded: str, root: Path | None) -> tuple[Path | None, str]:
    """The MadLoop export of a provider run under the reference root and its
    name relative to that root.

    A record's ``export`` is the absolute path of the run, which may point
    into a root that has moved (or must not be read): it is never opened or
    stat'ed. Its ``runs/...`` part (``_relative_export``) under ``root`` is
    the export, else the specification's ``madloop.export`` (an export that
    moved since the run); without a root, or where neither exists under it,
    only the name is kept (no generation times)."""

    names = [
        name for name in (_relative_export(recorded), _specified_export(key)) if name
    ]
    if root is not None:
        for name in names:
            if (root / name).exists():
                return root / name, name
    return None, names[0] if names else Path(recorded).name


def _specified_export(key: str) -> str | None:
    """The MadLoop export of ``processes.json`` (relative to the reference
    root), or None."""

    return streams.spec(key).get("madloop", {}).get("export")


def _relative_export(path: str) -> str | None:
    """A MadLoop export path relative to the reference root (its ``runs/...``
    part), or None for a path outside a reference root's ``runs``."""

    parts = Path(path).parts
    return str(Path(*parts[parts.index("runs") :])) if "runs" in parts else None


# The registry of the loop-induced rows (the report's milestone.json
# ``loop_induced``): the li-timing records are keyed by its row keys.
REGISTRY = (
    streams.ROOT / "docs" / "performance_reports" / "loop" / "data" / "milestone.json"
)
TIR_COUNTS = (
    "tensor moment rows",
    "contracted lanes",
    "moment rows shared",
    "TIR gate refusals",
    "TIR method-choice rows",
    "TIR method-choice rows with expansions",
    "TIR method-choice check rows",
    "TIR method-choice lanes refused by their check",
    "TIR capability refusals",
)


def _process_words(text: str) -> str:
    """A process text without its order limits and loop brackets
    ('u u~ > h g g QED=1 [sqrvirt=QCD]' -> 'u u~ > h g g')."""

    words = text.split("[")[0].split()
    return " ".join(word for word in words if "=" not in word)


def registry_key(key: str, rows: list[dict[str, Any]]) -> str:
    """The registry row of a loop-induced specification: the row with the
    specification's id (``li_row``) whose process is the specification's
    MadLoop process (order limits and brackets dropped); exactly one."""

    spec = streams.spec(key)
    process = _process_words(spec["madloop"]["process"])
    found = [
        row["key"]
        for row in rows
        if spec.get("li_row") in row.get("ids", ())
        and _process_words(row.get("process") or "") == process
    ]
    if len(found) != 1:
        raise KeyError(f"{key}: {len(found)} registry rows match {process!r}")
    return found[0]


# The short causes of failed points in the li-timing records (Table 2's
# words), from the reasons the executor records (``plan_export.
# FailedPoints``, numbers masked): (fragment, cause), first match.
FAILURE_CLASSES = (
    (
        "method-choice lane refused by its check",
        "TIRust acceptance (method-choice lane off its second frame)",
    ),
    ("method-choice lane unverified", "TIRust acceptance row refused"),
    ("ill-conditioned Gram matrix", "TIRust gates and method choice"),
    ("ImpreciseResult", "imprecise master"),
    ("not finite", "non-finite numerator"),
    (": Unstable", "NinjaRS lane unstable"),
)


def failure_class(reason: str) -> str:
    """The short cause of a recorded failure reason (``FAILURE_CLASSES``;
    otherwise the reason itself, shortened)."""

    for fragment, cause in FAILURE_CLASSES:
        if fragment in reason:
            return cause
    return reason[:80]


def failure_classes(causes: dict[str, int]) -> dict[str, int]:
    """Points per short cause (a point counted once per cause)."""

    out: dict[str, int] = {}
    for reason, points in causes.items():
        cause = failure_class(reason)
        out[cause] = max(out.get(cause, 0), points)
    return out


# The TirOptions of the harness's TIRust runs (the li-timing records'
# ``tir_options``): the shipped defaults.
TIR_OPTIONS = "shipped"


def li_timing_records(document: dict[str, Any], rows: list[dict[str, Any]]) -> list:
    """The gate tool's loop-induced records of ``data/li-timing.json`` (the
    report builder's format, ``build_summary`` LI_TIMING): per loop-induced
    configuration and timed batch one record with the request as resolved
    (requested / effective / reason verbatim), the core, per block the
    points failed closed and the served fraction, the time per point only
    where every block served every point (else the whole-call time), the
    time on the served points, the stage split, the TIR counts of the last
    block, the generation (generate + filter + export, the probes and their
    split, peaks) and the gate verdict."""

    out = []
    for process in document["processes"]:
        if not process.get("loop_induced"):
            continue
        key = registry_key(process["key"], rows)
        for name, config in process["pyamplicol"].items():
            reduction = config.get("reduction") or {}
            if "effective" not in reduction:
                continue
            native = config.get("native") or {}
            cpus = config.get("host_cpus") or []
            generation = config.get("generation") or {}
            stage = {
                n: (generation.get(n) or {}).get("seconds", 0.0)
                for n in ("generate", "export", "filter", "probes")
            }
            probes = generation.get("probes") or {}
            gen = {
                "seconds": stage["generate"] + stage["export"] + stage["filter"],
                "generate_seconds": stage["generate"],
                "dressed_frame_seconds": (generation.get("generate") or {}).get(
                    "dressed_frame_seconds"
                ),
                "export_seconds": stage["export"],
                "filter_seconds": stage["filter"],
                "probes_seconds": stage["probes"],
                "probes_split_seconds": probes.get("split_seconds"),
                "peak_gib": max(
                    (v.get("peak_gib") or 0.0)
                    for v in generation.values()
                    if isinstance(v, dict)
                ),
                "plan_mb": generation.get("plan_mb"),
                "filter_dropped_rows": (generation.get("filter") or {}).get(
                    "dropped_rows"
                ),
                "model_seconds": (generation.get("model") or {}).get("seconds"),
            }
            cpu = [
                (generation.get("generate") or {}).get("cpu_seconds_with_export"),
                (generation.get("filter") or {}).get("cpu_seconds"),
                probes.get("cpu_seconds"),
            ]
            if all(x is not None for x in cpu):
                # The process's CPU share of the generation's wall time (one
                # thread: below 1 a shared core or a stopped job).
                wall = gen["seconds"] + gen["probes_seconds"]
                gen["cpu_share"] = round(sum(cpu) / wall, 3) if wall else None
            for size, batch in sorted(
                config["batches"].items(), key=lambda x: int(x[0])
            ):
                failed = batch.get("failed_points") or [0] * batch["blocks"]
                record: dict[str, Any] = {
                    "key": key,
                    "revision": config["revision"],
                    "requested": reduction["requested"],
                    "backend": reduction["effective"],
                    "effective": reduction["effective"],
                    "reason": reduction["reason"],
                    "native_build": native.get("directory"),
                    "native_digest": native.get("digest"),
                    "batch": int(size),
                    "blocks": batch["blocks"],
                    "failed_points": failed,
                    "served_fraction": 1 - sum(failed) / (int(size) * len(failed)),
                    "host": config.get("host"),
                    "date": config.get("date"),
                    "core": cpus[0] if len(cpus) == 1 else cpus,
                    "eval_peak_gib": config.get("eval_peak_gib"),
                }
                if reduction["effective"] == "tirust":
                    # m-lit F4 (DECISIONS 2026-11-08 16:01): TIRust at the
                    # slice's shipped TirOptions; its re-time at the F3
                    # target accuracy is lit-tirust-default's.
                    record["tir_options"] = TIR_OPTIONS
                if any(failed):
                    record["whole_call_seconds_per_point"] = batch[
                        "median_seconds_per_point"
                    ]
                    record["block_whole_call_seconds_per_point"] = batch[
                        "samples_seconds_per_point"
                    ]
                    # The short causes (Table 2's words) and the recorded
                    # reasons, numbers masked.
                    record["failure_causes"] = failure_classes(
                        batch.get("failure_causes", {})
                    )
                    record["failure_reasons"] = batch.get("failure_causes", {})
                    served = (config.get("served") or {}).get(size)
                    if served is not None:
                        record["served_points"] = {
                            "points": served["points_per_block"],
                            "seconds_per_point": served["median_seconds_per_point"],
                            "blocks": served["blocks"],
                        }
                else:
                    record["seconds_per_point"] = batch["median_seconds_per_point"]
                    record["block_seconds_per_point"] = batch[
                        "samples_seconds_per_point"
                    ]
                if "dropped_blocks" in batch:
                    record["dropped_blocks"] = batch["dropped_blocks"]
                if "cpu_share" in batch:
                    # The process's CPU share of each block's wall time (one
                    # thread: below 1 the core was shared).
                    record["cpu_share"] = [round(x, 3) for x in batch["cpu_share"]]
                record["stages_per_point"] = {
                    n: batch["stages_per_point"][n]
                    for n in INDUCED_STAGES
                    if n in batch["stages_per_point"]
                }
                counts = batch.get("counts_per_block") or {}
                tir = {n: counts[n] for n in TIR_COUNTS if n in counts}
                if tir:
                    record["tir_counts_last_block"] = tir
                if int(size) == GATE_BATCH:
                    record["generation"] = gen
                    gate = batch["gate"]
                    record["gate"] = {
                        k: gate[k]
                        for k in (
                            "status",
                            "measured_status",
                            "binding_provider",
                            "binding_limit",
                            "fastest_provider",
                            "served_fraction",
                            "whole_call_ratio_to_binding_limit",
                            "served_points",
                            "not_matched",
                            "missing",
                            "floor_basis_seconds",
                        )
                        if k in gate
                    }
                    if "ratio_to_binding_limit" in gate:
                        record["gate"]["ratio_to_limit"] = gate[
                            "ratio_to_binding_limit"
                        ]
                        record["gate"]["band"] = gate["band_to_binding_limit"]
                    # The settings of each provider timing the verdict uses
                    # (providers.py: "optimistic" = m-lit F4's most
                    # optimistic settings, "production" otherwise).
                    record["gate"]["provider_protocols"] = {
                        n: x.get("protocol", "production")
                        for n, x in sorted((process.get("providers") or {}).items())
                        if "median_seconds_per_point" in x
                    }
                record["source"] = (
                    f"lit-perf gate tool (tools/loop_benchmark gate; process "
                    f"{process['key']}, configuration {name}): PLAN §5.1 protocol, "
                    "binary64, finite part, checks off, native inputs, full "
                    "colour, production route R2, one pinned thread; the 128 "
                    "distinct points of the frozen stream "
                    f"(tools/loop_benchmark/streams/{process['key']}.json); "
                    f"median of {batch['blocks']} paired blocks after an untimed "
                    "warm-up; requested backend resolved as the runtime resolves "
                    "a call (reduction.resolve, SUMMED, double); pyAmpliCol "
                    "most optimistic (m-lit F4: no poles, no stability checks, "
                    "distinct points, batched as shipped), TIRust at the slice's "
                    "shipped TirOptions"
                )
                out.append(record)
    return out


def write_li_timing(path: Path, records: list[dict[str, Any]]) -> None:
    """Merge ``records`` into ``data/li-timing.json``: a row's records at the
    same revision are replaced, every other record is kept."""

    data = json.loads(path.read_text()) if path.exists() else {"records": []}
    new = {(r["key"], r["revision"][:8]) for r in records}
    kept = [r for r in data["records"] if (r["key"], r["revision"][:8]) not in new]
    data["records"] = kept + records
    path.write_text(json.dumps(data, indent=1) + "\n")


def main(options: Any) -> int:
    import os

    root = options.reference_root or os.environ.get("LOOP_REFERENCE_ROOT")
    document, values = build(
        options.records,
        Path(root) if root else None,
        getattr(options, "host_spread", None),
        getattr(options, "min_cpu_share", None) or MIN_CPU_SHARE,
    )
    for item in options.meta or ():
        key, _, value = item.partition("=")
        document[key] = value
    options.json.parent.mkdir(parents=True, exist_ok=True)
    options.json.write_text(json.dumps(document, indent=1) + "\n")
    if getattr(options, "li_timing", None):
        registry = json.loads(Path(options.registry or REGISTRY).read_text())
        write_li_timing(
            options.li_timing,
            li_timing_records(document, registry["loop_induced"]["rows"]),
        )
    if options.values_json:
        options.values_json.write_text(json.dumps(values, separators=(",", ":")) + "\n")
    for process in document["processes"]:
        line = [process["key"]]
        for name, config in process["pyamplicol"].items():
            for size, batch in sorted(
                config["batches"].items(), key=lambda x: int(x[0])
            ):
                gate = batch["gate"]
                line.append(
                    f"{name} B={size} {batch['median_seconds_per_point'] * 1e3:.2f} ms "
                    f"{gate['status']}"
                    + (
                        f" ({gate['ratio_to_binding_limit']:.3g} x limit, band "
                        f"{gate['band_to_binding_limit'][0]:.3g}-"
                        f"{gate['band_to_binding_limit'][1]:.3g})"
                        if "ratio_to_binding_limit" in gate
                        else ""
                    )
                )
            if config["gate"]["status"] == GATE_MISSING_STATUS:
                line.append(
                    f"{name} G1 {GATE_MISSING_STATUS}: {config['gate']['reason']}"
                )
        print("; ".join(line))
    return 0
