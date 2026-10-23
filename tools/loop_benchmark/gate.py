# SPDX-License-Identifier: 0BSD
"""Gate G1 from the benchmark records (DESIGN §14, REQUIREMENTS_ADDENDUM D).

Reads ``pyamplicol`` and ``providers`` records (``python -m
tools.loop_benchmark``) and writes one JSON document for the live report
(``docs/performance_reports/loop/data/g1.json``):

- per process its multiplicity class (the gate applies from 2->3 upward;
  2->2 is reported without a gate), the providers' production-mode times
  per point and their setup, every pyAmpliCol record (path, colour, B, stage
  split, generation, accuracy check), and the speed gate per pyAmpliCol
  configuration: t < t_MadLoop and t <= 1.30 t for each matched Recola and
  OpenLoops time; with no matched provider the gate is "no matched provider
  timing" (never extrapolated, addendum F);
- the value comparison of pyAmpliCol and the providers on the same stream
  points (Born and finite part, metric |a-b| / max(|a|, |b|, |Born|
  alpha_s/(2 pi)) for the finite part; Recola's finite part converted to
  MadLoop's convention with the universal double pole, since Recola returns
  no poles in production mode).

Usage:
    python -m tools.loop_benchmark gate RECORD.json ... --json g1.json
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from . import providers as provider_module
from . import streams

GATE_FACTOR = 1.30
LABELS = {
    "gg_gg": "g g > g g",
    "uux_ddxg": "u u~ > d d~ g",
    "uux_uuxg": "u u~ > u u~ g",
    "uux_ggg": "u u~ > g g g",
    "gg_ggg": "g g > g g g",
    "gg_gggg": "g g > g g g g",
    "gg_ttxgg": "g g > t t~ g g",
    "uux_gggg": "u u~ > g g g g",
}


def multiplicity(key: str) -> int:
    return len(streams.spec(key)["pdgs"]) - 2


def gate_verdict(seconds: float, times: dict[str, float]) -> dict[str, Any]:
    """The speed gate of one pyAmpliCol time against the matched providers."""

    if not times:
        return {"status": "no matched provider timing"}
    checks = {}
    for provider, reference in times.items():
        limit = reference if provider == "madloop" else GATE_FACTOR * reference
        strict = provider == "madloop"
        passed = seconds < limit if strict else seconds <= limit
        checks[provider] = {
            "reference": reference,
            "limit": limit,
            "ratio_to_limit": seconds / limit,
            "passed": passed,
        }
    fastest = min(times, key=times.get)
    return {
        "status": "pass" if all(c["passed"] for c in checks.values()) else "fail",
        "checks": checks,
        "fastest_provider": fastest,
        "ratio_to_fastest": seconds / times[fastest],
        "binding_limit": min(c["limit"] for c in checks.values()),
        "ratio_to_binding_limit": seconds / min(c["limit"] for c in checks.values()),
    }


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
        for index in common:
            b0, f0 = mine[index]
            b1, f1 = values[index]
            floor = abs(b0) * alpha / (2 * math.pi)
            db = abs(b0 - b1) / max(abs(b0), abs(b1)) if (b0 or b1) else 0.0
            df = abs(f0 - f1) / max(abs(f0), abs(f1), floor) if (f0 or f1) else 0.0
            born_dev = max(born_dev, db)
            if df >= finite_dev:
                finite_dev, worst = df, index
        result[provider] = {
            "points": len(common),
            "max_born_deviation": born_dev,
            "max_finite_deviation": finite_dev,
            "worst_point": worst,
        }
    return result


def _times(record: dict[str, Any] | None) -> dict[str, float]:
    if record is None:
        return {}
    return {
        name: result["mean_seconds_per_point"]
        for name, result in record["providers"].items()
        if "mean_seconds_per_point" in result
    }


def _configuration(record: dict[str, Any]) -> str:
    parts = [record["inputs"], record["accuracy"]]
    if record.get("schedule", "B") != "B":
        parts.append("M")
    if record.get("lanes", 16) != 16:
        parts.append(f"L{record['lanes']}")
    return "/".join(parts)


def build(paths: list[Path]) -> dict[str, Any]:
    records = [json.loads(path.read_text()) for path in paths]
    processes: dict[str, dict[str, Any]] = {}
    for record in records:
        entry = processes.setdefault(
            record["process"],
            {"key": record["process"], "pyamplicol": {}, "providers": None},
        )
        if record["kind"] == "providers":
            if entry["providers"] is None:
                entry["providers"] = record
            else:
                entry["providers"]["providers"].update(record["providers"])
        else:
            entry["pyamplicol"][_configuration(record)] = record
    out = []
    for key in LABELS:
        entry = processes.get(key)
        if entry is None:
            continue
        legs = multiplicity(key)
        times = _times(entry["providers"])
        provider_values = (
            _provider_values(key, entry["providers"]) if entry["providers"] else {}
        )
        configurations = {}
        for name, record in entry["pyamplicol"].items():
            batches = {}
            mine: dict[int, tuple] = {}
            for size, summary in record.get("batches", {}).items():
                verdict = (
                    gate_verdict(summary["median_seconds_per_point"], times)
                    if legs >= 3
                    else {"status": "no gate (2->2)"}
                )
                batches[size] = {**summary, "gate": verdict}
                for index, value in summary.get("values", {}).items():
                    mine.setdefault(int(index), tuple(value))
            configurations[name] = {
                "revision": record["revision"],
                "branch": record["branch"],
                "dirty": record["dirty"],
                "native": record.get("native"),
                "inputs": record["inputs"],
                "accuracy": record["accuracy"],
                "schedule": record.get("schedule", "B"),
                "lanes": record.get("lanes", 16),
                "generation": record.get("generation"),
                "structure": record.get("structure"),
                "accuracy_check": record.get("accuracy_check"),
                "skipped_batches": record.get("skipped_batches", {}),
                "max_rss_gib": record.get("max_rss_gib"),
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
        out.append(
            {
                "key": key,
                "label": LABELS[key],
                "outgoing": legs,
                "gated": legs >= 3,
                "providers": provider_summary,
                "provider_cpu": entry["providers"]["cpu"]
                if entry["providers"]
                else None,
                "pyamplicol": configurations,
            }
        )
    return {"gate_factor": GATE_FACTOR, "processes": out}


def main(options: Any) -> int:
    document = build(options.records)
    options.json.parent.mkdir(parents=True, exist_ok=True)
    options.json.write_text(json.dumps(document, indent=1) + "\n")
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
                        f" ({gate['ratio_to_binding_limit']:.2f} x limit)"
                        if "ratio_to_binding_limit" in gate
                        else ""
                    )
                )
        print("; ".join(line))
    return 0
