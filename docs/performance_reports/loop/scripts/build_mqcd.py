# SPDX-License-Identifier: 0BSD
"""Write data/mqcd.json, the per-row data of the M-QCD validation campaign.

Usage: python scripts/build_mqcd.py RESULTS_DIR... [--output data/mqcd.json]
       [--findings data/mqcd-findings.json] [--markdown TABLE.md]
       [--junit JUNIT.xml ...] [--meta key=value ...]

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
- JUNIT.xml (optional)                     pytest --junitxml of the test
                                           files that hold a row's delegated
                                           column: rule 7 (``nc``) is MQ-NC's
                                           test ids (manifest ``nc_column``),
                                           the LC/NLC smoke on every shipped
                                           restriction its test (manifest
                                           ``smokes.lc_every_restriction``)
- data/mqcd-findings.json (optional)       the triage of the failing checks:
                                           per finding the rows and checks it
                                           explains, its evidence and the
                                           package it is routed to (curated,
                                           not computed)

Per row the output holds the manifest facts (rule 1's tolerance
``reference_tolerance`` among them: 1e-12 at 2->2 and 2->3, 1e-10 from 2->4
up, the user's ruling of 2026-10-29 ~01:12), every tier's record summary
(points, checks, failures with their rule, point, sector, coefficient,
error, bound and note; the largest double-double deviation from the primary
provider, binary64 against double-double, the poles against Catani in both
carriers, binary64 against the provider (information), the ``ward`` extra's
worst ratios, the points without a provider reference (MQ-REF's per-point
record), the out-of-scope binary64 coefficients, timings), its variants'
records, the ``nc`` column (per MQ-NC test id its outcome: passed,
failed, skipped or null when absent) and a status: ``pass``
(every run tier, gating variant and the nc column passed), ``fail`` (a check
or an nc test failed: a finding), ``pending`` (the manifest's waiting
package) or ``not-run`` (active, a record or an nc test missing). Later
directories override earlier ones per (row, tier). Nothing is estimated: a
value without a record stays null. The
per-class matrix of the report (PLAN §5.2) is the ``classes`` section;
``--markdown`` writes the per-row table.
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
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


def _status(pending: bool, tiers: dict, gating: list[dict], columns=()) -> str:
    if pending:
        return "pending"
    if not tiers and not gating:
        return "not-run"
    if (
        all(t["passed"] for t in tiers.values())
        and all(v["status"] == "pass" for v in gating)
        and all(c == "pass" for c in columns)
    ):
        return "pass"
    if (
        any(not t["passed"] for t in tiers.values())
        or any(v["status"] == "fail" for v in gating)
        or "fail" in columns
    ):
        return "fail"
    return "not-run"


def _node_id(classname: str, name: str) -> str:
    """The pytest node id of a JUnit test case (classname: the test file's
    dotted path, then its classes)."""

    parts = classname.split(".")
    for cut in range(len(parts), 0, -1):
        path = "/".join(parts[:cut]) + ".py"
        if (ROOT / path).is_file():
            return "::".join([path, *parts[cut:], name])
    return f"{classname.replace('.', '/')}.py::{name}"


def junit_outcomes(paths) -> dict[str, str]:
    """Node id -> passed | failed | skipped from pytest JUnit XML files
    (later files override)."""

    outcomes = {}
    for path in paths:
        for case in ET.parse(path).iter("testcase"):
            tags = {child.tag for child in case}
            outcome = (
                "failed"
                if tags & {"failure", "error"}
                else "skipped"
                if "skipped" in tags
                else "passed"
            )
            outcomes[_node_id(case.get("classname", ""), case.get("name", ""))] = (
                outcome
            )
    return outcomes


def column(ids, outcomes: dict[str, str]) -> dict:
    """A delegated column (another package's test ids): each id's outcome
    (an unparametrised id stands for all its parametrisations; null when
    absent) and the column's status: fail (one failed), pass (every id
    passed) or not-run."""

    tests = {}
    for node in ids:
        found = [
            o for n, o in outcomes.items() if n == node or n.startswith(node + "[")
        ]
        tests[node] = (
            None
            if not found
            else "failed"
            if "failed" in found
            else "skipped"
            if "skipped" in found
            else "passed"
        )
    values = list(tests.values())
    status = (
        "fail"
        if "failed" in values
        else "pass"
        if values and all(v == "passed" for v in values)
        else "not-run"
    )
    return {"status": status, "tests": tests}


def build(results: list[Path], meta: dict[str, str], findings=None, junit=()) -> dict:
    manifest = json.loads(MANIFEST.read_text())
    outcomes = junit_outcomes(junit)
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
            pending = variant.get("status") == "pending"
            variants.append(
                {
                    "id": name,
                    "gating": variant.get("gating", True),
                    "notes": variant.get("notes"),
                    "reference": variant.get("reference"),
                    "status": _status(pending, tiers, []),
                    "waits_for": (variant.get("pending") or {}).get("waits_for"),
                    "tiers": tiers,
                }
            )
        tiers = _tiers(records, row["id"])
        # A pending variant (waiting for its package) is reported, and does
        # not hold its row's status.
        gating = [v for v in variants if v["gating"] and v["status"] != "pending"]
        nc = column(row["nc_column"], outcomes) if row.get("nc_column") else None
        status = _status(
            row["status"] == "pending", tiers, gating, [nc["status"]] if nc else []
        )
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
                "reference_tolerance": row.get("reference_tolerance", 1e-12),
                "listed_outliers": row.get("reference_outliers", []),
                "listed_out_of_scope": row.get("binary64_out_of_scope", []),
                "status": status,
                "tiers": tiers,
                "variants": variants,
                "nc": nc,
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
    smoke = manifest.get("smokes", {}).get("lc_every_restriction")
    if isinstance(smoke, dict):
        checks["lc:every_restriction"] = column([smoke["test"]], outcomes)
    data = {
        "source": "tests/fixtures/loop/mqcd/manifest.json + campaign records "
        "(tests/unit/test_loop_v2_mqcd_*.py, PYAMPLICOL_MQCD_RESULTS)"
        + (" + JUnit XML of the delegated columns" if junit else ""),
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


def _nc_cell(row: dict) -> str:
    if row.get("nc"):
        return row["nc"]["status"]
    return "pending" if "nc" in row.get("extras_pending", {}) else ""


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
        "Rule 1 tol",
        "DD vs ref",
        "b64 vs DD",
        "Catani DD",
        "Ward DD",
        "nc",
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
        nc = row.get("nc")
        if nc:
            fails += [
                f"r7 {node.split('::')[-1]} {outcome or 'absent'}"
                for node, outcome in nc["tests"].items()
                if outcome == "failed"
            ]
        note = "; ".join(fails[:3]) + (
            f" (+{len(fails) - 3})" if len(fails) > 3 else ""
        )
        if row["status"] == "pending":
            note = f"waits for {row['waits_for']}"
        variants = "".join(
            f" +{v['id'].split('@', 1)[1]}"
            + (f" (waits for {v['waits_for']})" if v["status"] == "pending" else "")
            for v in row["variants"]
            if v["gating"]
        )
        ids = []
        for name in [row["id"]] + [v["id"] for v in row["variants"]]:
            ids += [f for f in explained.get(name, []) if f not in ids]
        lines.append(
            f"| {row['id']}{variants} | {row['process']} | {row['tier'][0]} | "
            f"{row['status']} | {row['reference_tolerance']:.0e} | "
            f"{_number(row['max_dd_vs_reference'])} | "
            f"{_number(row['max_binary64_vs_dd'])} | {_number(row['max_catani_dd'])} | "
            f"{_number(row.get('max_ward_dd'))} | {_nc_cell(row)} | {note} | "
            f"{', '.join(ids)} |"
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
    parser.add_argument("--junit", nargs="*", type=Path, default=[])
    parser.add_argument("--meta", nargs="*", default=[])
    args = parser.parse_args(argv)
    meta = dict(item.split("=", 1) for item in args.meta)
    findings = json.loads(args.findings.read_text()) if args.findings else None
    data = build(args.results, meta, findings, args.junit)
    args.output.write_text(json.dumps(data, indent=1, default=str) + "\n")
    if args.markdown:
        args.markdown.write_text(markdown(data))
    print(json.dumps(data["counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
