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


def multiplicity(key: str) -> int:
    return len(streams.spec(key)["pdgs"]) - 2


def label(key: str) -> str:
    """The process in the specification's provider-independent particle
    names (its Recola process string); the text the pyAmpliCol run generated
    from the model's names is kept as ``process_text``."""

    spec = streams.spec(key)
    return spec["recola"]["process"].replace("->", ">")


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
    the configuration's at B = 128), ``seconds`` by default."""

    verdict = _verdict(
        seconds,
        times,
        uncertainty=uncertainty,
        reference_uncertainty=reference_uncertainty,
        means=means,
        missing=missing,
        outside=outside,
    )
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
    factor = (
        provider_module.universal_double_pole(spec)
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
    key: str, mine: dict[int, tuple], theirs: dict[str, dict[int, tuple]]
) -> dict[str, Any]:
    alpha = float(streams.spec(key)["scheme_data"]["parameters"]["aS"])
    result: dict[str, Any] = {}
    for provider, values in theirs.items():
        common = sorted(set(values) & set(mine))
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
    paths: list[Path], reference_root: Path | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The gate document and the per-point values document. Provider files
    are resolved relative to ``reference_root`` only (``_export_of``): the
    absolute paths stored in the records are never read."""

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
            name = _configuration(record)
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
    host_spread = max((s for s in spreads if s is not None), default=0.0)
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
        times = _times(entry["providers"], "median_seconds_per_point")
        means = _times(entry["providers"], "mean_seconds_per_point")
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
                "failed_points": 0,
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
                "values_vs_providers": compare_values(key, mine, provider_values)
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


def main(options: Any) -> int:
    import os

    root = options.reference_root or os.environ.get("LOOP_REFERENCE_ROOT")
    document, values = build(options.records, Path(root) if root else None)
    for item in options.meta or ():
        key, _, value = item.partition("=")
        document[key] = value
    options.json.parent.mkdir(parents=True, exist_ok=True)
    options.json.write_text(json.dumps(document, indent=1) + "\n")
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
