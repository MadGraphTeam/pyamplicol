# SPDX-License-Identifier: 0BSD
"""Write data/mqcd.json, the per-row data of the M-QCD validation campaign.

Usage: python scripts/build_mqcd.py RESULTS_DIR... [--output data/mqcd.json]
       [--findings data/mqcd-findings.json] [--markdown TABLE.md]
       [--meta key=value ...]

Inputs:

- tests/fixtures/loop/mqcd/manifest.json   the 76 campaign rows (m-qcd/PLAN.md
                                           §4.2): request, reference, tier,
                                           status, extras, listings, variants
- RESULTS_DIR/<row>.<tier>.json            one record per row (or variant
                                           ``<id>@<name>``) and tier, written
                                           by tests/unit/test_loop_v2_mqcd_*.py
                                           (or ``python -m
                                           tools.loop_benchmark.mqcd run``) with
                                           PYAMPLICOL_MQCD_RESULTS=RESULTS_DIR;
                                           ``smoke:<restriction>`` and
                                           ``expansion:<row>`` records of the
                                           nightly smokes and the M01 expansion
- data/mqcd-findings.json (optional)       the triage of the failing checks:
                                           per finding the rows and checks it
                                           explains, its evidence and the
                                           package it is routed to (curated,
                                           not computed)

Per row the output holds the manifest facts, every tier's record summary
(points, checks, failures with their rule, point, sector, coefficient,
error, bound and note; the largest double-double deviation from the primary
provider, binary64 against double-double, the poles against Catani in both
carriers, binary64 against the provider (information), the ``ward`` extra's
worst ratios, the points without a provider reference (MQ-REF's per-point
record), the out-of-scope binary64 coefficients, timings), its variants'
records and a status: ``pass``
(every run tier and gating variant passed), ``fail`` (a check failed: a
finding), ``pending`` (the manifest's waiting package) or ``not-run``
(active, no record given). Later directories override earlier ones per
(row, tier). Nothing is estimated: a value without a record stays null. The
per-class matrix of the report (PLAN §5.2) is the ``classes`` section;
``--markdown`` writes the per-row table.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MANIFEST = ROOT / "tests" / "fixtures" / "loop" / "mqcd" / "manifest.json"
DATA = ROOT / "docs" / "performance_reports" / "loop" / "data"
DEFAULT_OUTPUT = DATA / "mqcd.json"
SUMMARY_KEYS = (
    "points",
    "passed",
    "checks",
    "failures",
    "max_dd_vs_reference",
    "max_binary64_vs_dd",
    "max_catani_dd",
    "max_catani_binary64",
    "catani_not_formed",
    "binary64_vs_reference",
    "ward",
    "no_reference",
    "binary64_out_of_scope",
    "timings",
)
CHECK_KEYS = (
    "rule",
    "point",
    "carrier",
    "sector",
    "coefficient",
    "error",
    "bound",
    "note",
)
STATUSES = ("pass", "fail", "pending", "not-run")


def _maximum(values):
    values = [v for v in values if v is not None]
    return max(values) if values else None


def _entry(record: dict) -> dict:
    entry = {key: record.get(key) for key in SUMMARY_KEYS}
    entry["failed_checks"] = [
        {key: check.get(key) for key in CHECK_KEYS}
        for check in record.get("check_records", ())
        if not check["passed"]
    ]
    return entry


def _tiers(records, name: str) -> dict:
    return {
        tier: _entry(records[name, tier])
        for tier in ("default", "nightly")
        if (name, tier) in records
    }


def _status(pending: bool, tiers: dict, gating: list[dict]) -> str:
    if pending:
        return "pending"
    if not tiers and not gating:
        return "not-run"
    if all(t["passed"] for t in tiers.values()) and all(
        v["status"] == "pass" for v in gating
    ):
        return "pass"
    if any(not t["passed"] for t in tiers.values()) or any(
        v["status"] == "fail" for v in gating
    ):
        return "fail"
    return "not-run"


def build(results: list[Path], meta: dict[str, str], findings=None) -> dict:
    manifest = json.loads(MANIFEST.read_text())
    records: dict[tuple[str, str], dict] = {}
    for directory in results:
        for path in sorted(Path(directory).glob("*.json")):
            record = json.loads(path.read_text())
            records[record["row"], record["tier"]] = record
    rows = []
    for row in manifest["rows"]:
        variants = []
        for variant in row.get("variants", ()):
            name = f"{row['id']}@{variant['name']}"
            tiers = _tiers(records, name)
            variants.append(
                {
                    "id": name,
                    "gating": variant.get("gating", True),
                    "notes": variant.get("notes"),
                    "reference": variant.get("reference"),
                    "status": _status(False, tiers, []),
                    "tiers": tiers,
                }
            )
        tiers = _tiers(records, row["id"])
        gating = [v for v in variants if v["gating"]]
        status = _status(row["status"] == "pending", tiers, gating)
        every = [*tiers.values(), *(t for v in gating for t in v["tiers"].values())]
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
                "pending_reason": (row.get("pending") or {}).get("reason"),
                "listed_outliers": row.get("reference_outliers", []),
                "listed_out_of_scope": row.get("binary64_out_of_scope", []),
                "status": status,
                "tiers": tiers,
                "variants": variants,
                "max_dd_vs_reference": _maximum(
                    t["max_dd_vs_reference"] for t in every
                ),
                "max_binary64_vs_dd": _maximum(t["max_binary64_vs_dd"] for t in every),
                "max_catani_dd": _maximum(t["max_catani_dd"] for t in every),
                # The ward extra's worst double-double virtual ratio
                # (|V_k| / scale_k; the bound is 1e-25).
                "max_ward_dd": _maximum(
                    (t.get("ward") or {}).get("virtual_double-double")
                    for t in tiers.values()
                ),
            }
        )
    classes = defaultdict(lambda: defaultdict(int))
    for row in rows:
        classes[row["class"]][row["status"]] += 1
        classes[row["class"]]["rows"] += 1
    checks = {}
    for (name, tier), record in sorted(records.items()):
        if name.startswith(("smoke:", "expansion:")):
            checks[name] = {
                "tier": tier,
                "passed": record["passed"],
                "checks": record["checks"],
                "failed_checks": _entry(record)["failed_checks"],
            }
    data = {
        "source": "tests/fixtures/loop/mqcd/manifest.json + campaign records "
        "(tests/unit/test_loop_v2_mqcd_*.py, PYAMPLICOL_MQCD_RESULTS)",
        "rules": "m-qcd/PLAN.md §1.4 (tools/loop_benchmark/mqcd.py)",
        **meta,
        "counts": {
            status: sum(r["status"] == status for r in rows) for status in STATUSES
        },
        "classes": {name: dict(counts) for name, counts in sorted(classes.items())},
        "smokes_and_expansions": checks,
        "rows": rows,
    }
    if findings is not None:
        data["findings"] = findings["findings"]
    return data


def _number(value) -> str:
    return "-" if value is None else f"{value:.1e}"


def markdown(data: dict) -> str:
    """The per-row table: status, the worst deviation per rule and the
    failing checks (rule, point, carrier, coefficient, error > bound),
    with the finding that explains them."""

    explained = {}
    for finding in data.get("findings", ()):
        label = finding["id"]
        if finding.get("status") == "resolved":
            label += " (resolved)"
        for name in finding["rows"]:
            explained.setdefault(name, []).append(label)
    columns = (
        "Row",
        "Process",
        "Tier",
        "Status",
        "DD vs ref",
        "b64 vs DD",
        "Catani DD",
        "Ward DD",
        "Failing checks",
        "Findings",
    )
    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "---|" * len(columns),
    ]
    for row in data["rows"]:
        fails = []
        units = [(row["id"], row["tiers"])] + [
            (v["id"], v["tiers"]) for v in row["variants"] if v["gating"]
        ]
        for name, tiers in units:
            for tier in tiers.values():
                for check in tier["failed_checks"]:
                    label = name.split("@", 1)[1] + ": " if "@" in name else ""
                    text = (
                        f"{label}r{check['rule']} p{check['point']} "
                        f"{check['carrier'][:2]} {check['coefficient'][:6]}"
                    )
                    if check["rule"] != "eval":
                        text += f" {check['error']:.2g}>{check['bound']:.2g}"
                    if text not in fails:
                        fails.append(text)
        note = "; ".join(fails[:3]) + (
            f" (+{len(fails) - 3})" if len(fails) > 3 else ""
        )
        if row["status"] == "pending":
            note = f"waits for {row['waits_for']}"
        variants = "".join(
            f" +{v['id'].split('@', 1)[1]}" for v in row["variants"] if v["gating"]
        )
        ids = []
        for name in [row["id"]] + [v["id"] for v in row["variants"]]:
            ids += [f for f in explained.get(name, []) if f not in ids]
        lines.append(
            f"| {row['id']}{variants} | {row['process']} | {row['tier'][0]} | "
            f"{row['status']} | {_number(row['max_dd_vs_reference'])} | "
            f"{_number(row['max_binary64_vs_dd'])} | {_number(row['max_catani_dd'])} | "
            f"{_number(row.get('max_ward_dd'))} | {note} | {', '.join(ids)} |"
        )
    lines.append("")
    lines.append("Counts: " + json.dumps(data["counts"]))
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--findings", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--meta", nargs="*", default=[])
    args = parser.parse_args(argv)
    meta = dict(item.split("=", 1) for item in args.meta)
    findings = json.loads(args.findings.read_text()) if args.findings else None
    data = build(args.results, meta, findings)
    args.output.write_text(json.dumps(data, indent=1, default=str) + "\n")
    if args.markdown:
        args.markdown.write_text(markdown(data))
    print(json.dumps(data["counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
