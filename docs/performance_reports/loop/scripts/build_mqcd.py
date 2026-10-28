# SPDX-License-Identifier: 0BSD
"""Write data/mqcd.json, the per-row data of the M-QCD validation campaign.

Usage: python scripts/build_mqcd.py RESULTS_DIR... [--output data/mqcd.json]
       [--meta key=value ...]

Inputs:

- tests/fixtures/loop/mqcd/manifest.json   the 76 campaign rows (m-qcd/PLAN.md
                                           §4.2): request, reference, tier,
                                           status, extras, listings
- RESULTS_DIR/<row>.<tier>.json            one record per row and tier, written
                                           by tests/unit/test_loop_v2_mqcd_*.py
                                           (or ``python -m
                                           tools.loop_benchmark.mqcd run``) with
                                           PYAMPLICOL_MQCD_RESULTS=RESULTS_DIR

Per row the output holds the manifest facts, every tier's record summary
(points, checks, failures with their rule, point, sector, coefficient,
error and bound; the largest double-double deviation from the primary
provider, binary64 against double-double, the poles against Catani in both
carriers, binary64 against the provider (information), the out-of-scope
binary64 coefficients, timings) and a status: ``pass`` (every run tier
passed), ``fail`` (a check failed: the finding), ``pending`` (the manifest's
waiting package) or ``not-run`` (active, no record given). Later directories
override earlier ones per (row, tier). Nothing is estimated: a value without
a record stays null. The per-class matrix of the report (PLAN §5.2) is the
``classes`` section.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MANIFEST = ROOT / "tests" / "fixtures" / "loop" / "mqcd" / "manifest.json"
DEFAULT_OUTPUT = ROOT / "docs" / "performance_reports" / "loop" / "data" / "mqcd.json"
SUMMARY_KEYS = (
    "points",
    "passed",
    "checks",
    "failures",
    "max_dd_vs_reference",
    "max_binary64_vs_dd",
    "max_catani_dd",
    "max_catani_binary64",
    "binary64_vs_reference",
    "binary64_out_of_scope",
    "timings",
)


def _maximum(values):
    values = [v for v in values if v is not None]
    return max(values) if values else None


def build(results: list[Path], meta: dict[str, str]) -> dict:
    manifest = json.loads(MANIFEST.read_text())
    records: dict[tuple[str, str], dict] = {}
    for directory in results:
        for path in sorted(Path(directory).glob("*.json")):
            record = json.loads(path.read_text())
            records[record["row"], record["tier"]] = record
    rows = []
    for row in manifest["rows"]:
        tiers = {}
        for tier in ("default", "nightly"):
            record = records.get((row["id"], tier))
            if record is None:
                continue
            entry = {key: record.get(key) for key in SUMMARY_KEYS}
            entry["failed_checks"] = [
                {
                    key: check[key]
                    for key in (
                        "rule",
                        "point",
                        "carrier",
                        "sector",
                        "coefficient",
                        "error",
                        "bound",
                        "note",
                    )
                }
                for check in record.get("check_records", ())
                if not check["passed"]
            ]
            tiers[tier] = entry
        if row["status"] == "pending":
            status = "pending"
        elif not tiers:
            status = "not-run"
        elif all(t["passed"] for t in tiers.values()):
            status = "pass"
        else:
            status = "fail"
        rows.append(
            {
                "id": row["id"],
                "class": row["class"],
                "process": row["process"],
                "restriction": row["restriction"],
                "restriction_code": row["restriction_code"],
                "tier": row["tier"],
                "reference": row["reference"],
                "reference_legend": row.get("reference_legend"),
                "extras": row["extras"],
                "extras_pending": row.get("extras_pending", {}),
                "waits_for": (row.get("pending") or {}).get("waits_for"),
                "listed_outliers": row.get("reference_outliers", []),
                "listed_out_of_scope": row.get("binary64_out_of_scope", []),
                "status": status,
                "tiers": tiers,
                "max_dd_vs_reference": _maximum(
                    t["max_dd_vs_reference"] for t in tiers.values()
                ),
                "max_binary64_vs_dd": _maximum(
                    t["max_binary64_vs_dd"] for t in tiers.values()
                ),
                "max_catani_dd": _maximum(t["max_catani_dd"] for t in tiers.values()),
            }
        )
    classes = defaultdict(lambda: defaultdict(int))
    for row in rows:
        classes[row["class"]][row["status"]] += 1
        classes[row["class"]]["rows"] += 1
    return {
        "source": "tests/fixtures/loop/mqcd/manifest.json + campaign records "
        "(tests/unit/test_loop_v2_mqcd_*.py, PYAMPLICOL_MQCD_RESULTS)",
        "rules": "m-qcd/PLAN.md §1.4 (tools/loop_benchmark/mqcd.py)",
        **meta,
        "counts": {
            status: sum(r["status"] == status for r in rows)
            for status in ("pass", "fail", "pending", "not-run")
        },
        "classes": {name: dict(counts) for name, counts in sorted(classes.items())},
        "rows": rows,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--meta", nargs="*", default=[])
    args = parser.parse_args(argv)
    meta = dict(item.split("=", 1) for item in args.meta)
    data = build(args.results, meta)
    args.output.write_text(json.dumps(data, indent=1, default=str) + "\n")
    print(json.dumps(data["counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
