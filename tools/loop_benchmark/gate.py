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
  matched provider timing" (never extrapolated, addendum F);
- its **uncertainty** (MASTER_PLAN §5.8 item 9): the relative standard error
  of pyAmpliCol's median over its blocks (1.2533 x 1.4826 MAD / sqrt(n),
  half the range for fewer than three blocks) plus each provider's relative
  half-range over its repeated runs (for a single run, the largest
  half-range of any provider in the campaign, marked "assumed"). The time
  over the limit with that band decides: pass if the whole band passes, fail
  if the whole band fails, otherwise "inconclusive" (to be repeated once,
  item 10). The ratio with the providers' means is kept beside it;
- a configuration measured twice (a repeat) keeps the earlier run's batch
  times as ``earlier_runs``; the later run, with its paired provider run,
  decides;
- the value comparison of pyAmpliCol and the providers on the same stream
  points (Born and finite part, metric |a-b| / max(|a|, |b|, |Born|
  alpha_s/(2 pi)) for the finite part; Recola's finite part converted to
  MadLoop's convention with the universal double pole, since Recola returns
  no poles in production mode) and the stability rows (binary64 and
  double-double at the worst points);
- the schedule B/M comparison on the schedule-dependent stages (seeds,
  factors, dressing, scatter, reduction) and end to end, with the design's
  adoption rule (M where at least 15 % faster, the reduction included);
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

GATE_FACTOR = 1.30
ADOPT_M = 0.85
SCHEDULE_STAGES = ("seeds", "factors", "dressing", "scatter", "reduction")


def multiplicity(key: str) -> int:
    return len(streams.spec(key)["pdgs"]) - 2


def label(key: str, text: str | None = None) -> str:
    """The process text: the generated one, else the specification's."""

    if text:
        return text
    spec = streams.spec(key)
    return spec["recola"]["process"].replace("->", ">")


def median_uncertainty(samples: list[float]) -> float:
    """Relative standard error of the median of ``samples`` (module
    docstring)."""

    if len(samples) < 2:
        return 0.0
    median = statistics.median(samples)
    if len(samples) < 3:
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
) -> dict[str, Any]:
    """The speed gate of one pyAmpliCol time against the matched providers.

    ``uncertainty``: pyAmpliCol's relative uncertainty; ``reference_uncertainty``:
    per provider (relative uncertainty, assumed). The verdict of each check is
    taken on the band ratio x (1 -+ u), u the sum of both."""

    if not times:
        return {"status": "no matched provider timing"}
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
    factor = provider_module.universal_double_pole(spec)
    out: dict[str, dict[int, tuple]] = {}
    for name, result in record["providers"].items():
        rows = result.get("rows")
        if not rows:
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


def _madloop_generation(export: Path) -> dict[str, Any] | None:
    """Graph generation, Fortran export and compilation seconds of a MadLoop
    export (``madloop_export.py``'s ``<export>.generation.json``)."""

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
    if record is None:
        return {}
    return {
        name: result[field]
        for name, result in record["providers"].items()
        if field in result
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


def _values_of(summary: dict[str, Any]) -> dict[int, tuple]:
    return {int(i): tuple(v) for i, v in summary.get("values", {}).items()}


def build(paths: list[Path]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The gate document and the per-point values document."""

    records = [json.loads(path.read_text()) for path in paths]
    order = streams.keys()
    processes: dict[str, dict[str, Any]] = {}
    for record in records:
        key = record["process"]
        if key not in order:
            raise KeyError(f"{key}: a record of a process not in processes.json")
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
        if record["kind"] == "stability":
            for row in record["rows"]:
                entry.setdefault("stability", []).append(
                    {
                        "arithmetic": "double",
                        **row,
                        "configuration": _configuration(record),
                        "revision": record["revision"],
                    }
                )
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
                            "cpu": record["cpu"],
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
                        "cpu": record["cpu"],
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
        times = _times(entry["providers"], "median_seconds_per_point")
        means = _times(entry["providers"], "mean_seconds_per_point")
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
        for name, record in entry["pyamplicol"].items():
            batches = {}
            mine: dict[int, tuple] = {}
            for size, summary in record.get("batches", {}).items():
                samples = summary["samples_seconds_per_point"]
                uncertainty = median_uncertainty(samples)
                if legs < 3:
                    verdict = {"status": "no gate (2->2)"}
                elif record["accuracy"] != "full":
                    # Providers time full colour: LC/NLC carry no ratio.
                    verdict = {"status": "no gate (colour approximation)"}
                else:
                    verdict = gate_verdict(
                        summary["median_seconds_per_point"],
                        times,
                        uncertainty=uncertainty,
                        reference_uncertainty=reference_uncertainty,
                        means=means,
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
                "structure": record.get("structure"),
                "accuracy_check": accuracy_check,
                "skipped_batches": record.get("skipped_batches", {}),
                "max_rss_gib": record.get("max_rss_gib"),
                "failed_points": 0,
                "rescue": "off (no stability check, no escalation)",
                "earlier_runs": record.get("earlier_runs", []),
                "batches": batches,
                "values_vs_providers": compare_values(key, mine, provider_values)
                if record["accuracy"] == "full"
                else None,
            }
        provider_summary = None
        if entry["providers"] is not None:
            provider_summary = {
                name: {k: v for k, v in result.items() if k != "rows"}
                for name, result in entry["providers"]["providers"].items()
            }
            madloop = provider_summary.get("madloop")
            if madloop and "export" in madloop:
                madloop["generation"] = _madloop_generation(Path(madloop["export"]))
                madloop["export"] = _relative_export(madloop["export"])
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
                "label": label(key, entry["text"]),
                "outgoing": legs,
                "gated": legs >= 3,
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
    from tools.loop_v2_costmodel import g1_recalibration

    document["recalibration"] = g1_recalibration(document)
    return document, values_document


def _relative_export(path: str) -> str:
    """A MadLoop export path relative to the reference root (``runs/...``)."""

    parts = Path(path).parts
    return str(Path(*parts[parts.index("runs") :])) if "runs" in parts else path


def main(options: Any) -> int:
    document, values = build(options.records)
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
                        f" ({gate['ratio_to_binding_limit']:.2f} x limit, band "
                        f"{gate['band_to_binding_limit'][0]:.2f}-"
                        f"{gate['band_to_binding_limit'][1]:.2f})"
                        if "ratio_to_binding_limit" in gate
                        else ""
                    )
                )
        print("; ".join(line))
    return 0
