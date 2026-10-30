# SPDX-License-Identifier: 0BSD
"""Write data/mqcd.json, the per-row data of the M-QCD validation campaign.

Usage: python scripts/build_mqcd.py RESULTS_DIR... [--output data/mqcd.json]
       [--findings data/mqcd-findings.json] [--markdown TABLE.md]
       [--junit JUNIT.xml ...] [--meta key=value ...] [--manifest MANIFEST]

The M-SM campaign (m-sm/PLAN.md §3.2 MS-VALIDATE item 9) is the same build
on its manifest: ``--manifest tests/fixtures/loop/msm/manifest.json --output
data/msm.json`` (records of tests/unit/test_loop_v2_msm_*.py and of the
campaign CLI's ``--tier campaign`` rows).

The campaign: PYAMPLICOL_MQCD_RESULTS=RESULTS_DIR pytest on
tests/unit/test_loop_v2_mqcd_default.py (-m "not loop_nightly") and on each
nightly file job tests/unit/test_loop_v2_mqcd_nightly*.py (-m loop_nightly),
one process per file; the delegated columns by
pytest --junitxml JUNIT.xml $(python -m tools.loop_benchmark.mqcd
delegated-ids).

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
                                           columns (manifest ``delegated``:
                                           rule 7's ``nc``, MQ-NC's ids;
                                           M01's ``bitwise``, MQ-MODEL's) and
                                           the LC/NLC smoke on every shipped
                                           restriction (manifest
                                           ``smokes.lc_every_restriction``)
- data/mqcd-findings.json (optional)       the triage of the failing checks:
                                           per finding the rows and checks it
                                           explains, its evidence and the
                                           package it is routed to (curated,
                                           not computed)

Per row the output holds the manifest facts (rule 1's tolerance
``reference_tolerance`` among them: 1e-12, relaxed to 1e-10 only on the
2->4+ rows whose providers need it, the user's ruling of 2026-10-29 ~01:12;
and ``relaxed``, the rule -> tolerance of checks the user's ruling of
2026-10-29 ~10:20 relaxes on the row, at most 1e-5),
every tier's expected record summary at the manifest's points
(points, checks, failures with their rule, point, sector, coefficient,
error, bound and note; the largest double-double deviation from the primary
provider, binary64 against double-double, the poles against Catani in both
carriers, binary64 against the provider (information), the ``ward`` extra's
worst ratios, the points without a provider reference (MQ-REF's per-point
record), the out-of-scope binary64 coefficients, timings), its variants'
records, the delegated columns (``delegated``, rule 7's as ``nc``: per
test id its outcome, passed, failed, skipped or null when absent) and a
status: ``pass`` (every run tier, gating variant and delegated column
passed, and a composite row's expansion check), ``partial`` (likewise, but
a record forms no rule 4, ``catani_not_formed``: a native-input row without
the tree engine's committed correlations), ``fail`` (a check or a
delegated test failed: a finding), ``pending`` (the manifest's waiting
package) or ``not-run`` (active, a delegated test or an expected record
missing: a default-tier row's default and nightly records, a nightly row's
nightly record, each at the manifest's points, ``missing_records``). A
composite row (M01) has no tier of its own: its gating variants, its
``expansion:<id>`` record and its delegated columns make it up. Later
directories override earlier ones per (row, tier) among the records at the
manifest's points (a partial ``--points`` rerun is no tier record). Nothing
is estimated: a
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
STATUSES = ("pass", "partial", "fail", "pending", "not-run")
# Short carrier names of the per-row table.
CARRIERS = {"double": "b64", "double-double": "DD"}


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


def expected_tiers(entry: dict, base: dict | None = None) -> dict[str, list[int]]:
    """tier -> the manifest's points of a row (or of a variant, ``base`` its
    row) that the campaign's tier modules run: a default-tier row's default
    points (tests/unit/test_loop_v2_mqcd_default.py) and every row's nightly
    points (the nightly file jobs, extras included). A composite row runs no
    tier of its own."""

    if base is None and entry.get("status") == "composite":
        return {}
    points = entry.get("points") or (base or {}).get("points") or {}
    tier = entry.get("tier") or (base or {}).get("tier")
    # A campaign-tier row (m-sm/PLAN.md §4.3: the 2->5 target, CM07) runs
    # its own tier, by the campaign CLI.
    tiers = ("default", "nightly") if tier == "default" else (tier or "nightly",)
    return {t: list(points[t]) for t in tiers if points.get(t)}


def _tiers(records, name: str, expected: dict[str, list[int]]) -> tuple[dict, list]:
    """The summaries of the expected tiers' records and the expected tiers
    without one: a record counts only at the manifest's points (a partial
    ``--points`` rerun is not a tier record; the latest matching directory
    wins)."""

    tiers, missing = {}, []
    for tier, points in expected.items():
        found = [r for r in records.get((name, tier), ()) if r["points"] == points]
        if found:
            tiers[tier] = _entry(found[-1])
        else:
            missing.append(tier)
    return tiers, missing


def _status(
    pending: bool, tiers: dict, gating: list[dict], columns=(), missing=()
) -> str:
    """pending, else fail (a failed check, gating variant or delegated test),
    else pass (every expected record, gating variant and delegated test
    present and passed), else not-run."""

    if pending:
        return "pending"
    if (
        any(not t["passed"] for t in tiers.values())
        or any(v["status"] == "fail" for v in gating)
        or "fail" in columns
    ):
        return "fail"
    if (
        (tiers or gating)
        and not missing
        and all(v["status"] == "pass" for v in gating)
        and all(c == "pass" for c in columns)
    ):
        return "pass"
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


def build(
    results: list[Path],
    meta: dict[str, str],
    findings=None,
    junit=(),
    manifest_path: Path | None = None,
) -> dict:
    manifest_path = manifest_path or MANIFEST
    manifest = json.loads(Path(manifest_path).read_text())
    outcomes = junit_outcomes(junit)
    records: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for directory in results:
        for path in sorted(Path(directory).glob("*.json")):
            record = json.loads(path.read_text())
            records[record["row"], record["tier"]].append(record)
    rows = []
    for row in manifest["rows"]:
        variants = []
        for variant in row.get("variants", ()):
            name = f"{row['id']}@{variant['name']}"
            tiers, missing = _tiers(records, name, expected_tiers(variant, row))
            pending = variant.get("status") == "pending"
            variants.append(
                {
                    "id": name,
                    "gating": variant.get("gating", True),
                    "notes": variant.get("notes"),
                    "reference": variant.get("reference"),
                    "relaxed": variant.get("relaxed", row.get("relaxed", {})),
                    "status": _status(pending, tiers, [], missing=missing),
                    "waits_for": (variant.get("pending") or {}).get("waits_for"),
                    "tiers": tiers,
                    "missing_records": missing,
                }
            )
        tiers, missing = _tiers(records, row["id"], expected_tiers(row))
        # A pending variant (waiting for its package) is reported, and does
        # not hold its row's status.
        gating = [v for v in variants if v["gating"] and v["status"] != "pending"]
        delegated = {
            name: column(ids, outcomes)
            for name, ids in (row.get("delegated") or {}).items()
        }
        if row["status"] == "composite":
            # Its expansion check is one of its parts.
            found = records.get((f"expansion:{row['id']}", "nightly"))
            expansion = found[-1] if found else None
            gating.append(
                {
                    "tiers": {},
                    "status": "not-run"
                    if expansion is None
                    else "pass"
                    if expansion["passed"]
                    else "fail",
                }
            )
        status = _status(
            row["status"] == "pending",
            tiers,
            gating,
            [c["status"] for c in delegated.values()],
            missing,
        )
        if (
            status == "pass"
            and row.get("route", "tools") != "public"
            and any(t["catani_not_formed"] for t in tiers.values())
        ):
            # Every asserted check passed, but rule 4 was not formed (a
            # native-input row without the tree engine's correlations).
            status = "partial"
        every = [*tiers.values(), *(t for v in gating for t in v["tiers"].values())]
        rows.append(
            {
                "id": row["id"],
                "class": row["class"],
                "process": row["process"],
                "restriction": row["restriction"],
                "restriction_code": row["restriction_code"],
                # The model and corrections (M-SM rows; M-QCD's are loop_sm
                # and QCD).
                "model": row.get("model", "loop_sm"),
                "corrections": row.get("corrections", ["QCD"]),
                "tier": row["tier"],
                "reference": row["reference"],
                "reference_legend": row.get("reference_legend"),
                "extras": row["extras"],
                "extras_pending": row.get("extras_pending", {}),
                "waits_for": (row.get("pending") or {}).get("waits_for"),
                "pending_reason": (row.get("pending") or {}).get("reason"),
                "reference_tolerance": row.get("reference_tolerance", 1e-12),
                # Rule 4's prediction ("python", "tree", "none") and the
                # ward extra's legs (null: every massless vector leg).
                "catani": row.get("catani", "python"),
                "ward_legs": row.get("ward_legs"),
                "listed_outliers": row.get("reference_outliers", []),
                "relaxed": row.get("relaxed", {}),
                "status": status,
                "tiers": tiers,
                # Expected tier records absent at the manifest's points.
                "missing_records": missing if row["status"] == "active" else [],
                "variants": variants,
                "nc": delegated.get("nc"),
                "delegated": delegated,
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
    for (name, tier), found in sorted(records.items()):
        record = found[-1]
        if name.startswith(("smoke:", "expansion:", "oracle:")):
            checks[name] = {
                "tier": tier,
                "passed": record["passed"],
                "checks": record["checks"],
                "failed_checks": _entry(record)["failed_checks"],
            }
    # The nightly smokes, composite expansions and the "tree" Catani oracle
    # check (tests/unit/test_loop_v2_mqcd_nightly.py): absent records not-run.
    smokes = manifest.get("smokes", {})
    declared = [f"smoke:{r}" for r in smokes.get("same_request", {})]
    # The M-SM restriction smokes (tests/unit/test_loop_v2_msm_smokes*.py).
    declared += [f"smoke:{e['id']}" for e in smokes.get("restrictions", ())]
    if any(r.get("catani") == "tree" for r in manifest["rows"]):
        declared.append("oracle:tree-catani")
    declared += [
        f"expansion:{r['id']}" for r in manifest["rows"] if r["status"] == "composite"
    ]
    for name in declared:
        checks.setdefault(
            name, {"tier": "nightly", "passed": None, "status": "not-run"}
        )
    for entry in checks.values():
        entry.setdefault("status", "pass" if entry["passed"] else "fail")
    smoke = manifest.get("smokes", {}).get("lc_every_restriction")
    if isinstance(smoke, dict):
        checks["lc:every_restriction"] = column([smoke["test"]], outcomes)
    name = Path(manifest_path).resolve().parent.name
    # The manifest's own plan ("workspace/reports/engine-v2/m-sm/PLAN.md
    # §1.4, ..."): its directory names the campaign's PLAN.
    plan = Path(manifest["plan"].split()[0]).parent.name
    data = {
        "source": f"tests/fixtures/loop/{name}/manifest.json + campaign records "
        f"(tests/unit/test_loop_v2_{name}_*.py, PYAMPLICOL_MQCD_RESULTS)"
        + (" + JUnit XML of the delegated columns" if junit else ""),
        "rules": f"{plan}/PLAN.md §1.4 (tools/loop_benchmark/mqcd.py)",
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
        # What the campaign covers short of the plan, stated (curated).
        data["coverage_notes"] = findings.get("coverage_notes", [])
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
        "Tolerances",
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
                    carrier = CARRIERS.get(check["carrier"], check["carrier"])
                    if check["rule"] == "eval" and check["point"] is None:
                        # The row's generation or evaluation raised.
                        error = (check["note"] or "").split(":", 1)[0]
                        text = f"{label}raised {error}".rstrip()
                    elif check["rule"] == "eval":
                        text = f"{label}p{check['point']} {carrier} evaluation failed"
                    else:
                        text = (
                            f"{label}r{check['rule']} p{check['point']} {carrier} "
                            f"{check['sector'] or ''} {check['coefficient']} "
                            f"{check['error']:.2g}>{check['bound']:.2g}"
                        ).replace("  ", " ")
                    if text not in fails:
                        fails.append(text)
        for name, found in row.get("delegated", {}).items():
            label = "r7" if name == "nc" else name
            fails += [
                f"{label} {node.split('::')[-1]} failed"
                for node, outcome in found["tests"].items()
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
            f"{row['status']} | {_tolerances(row)} | "
            f"{_number(row['max_dd_vs_reference'])} | "
            f"{_number(row['max_binary64_vs_dd'])} | {_number(row['max_catani_dd'])} | "
            f"{_number(row.get('max_ward_dd'))} | {_nc_cell(row)} | {note} | "
            f"{', '.join(ids)} |"
        )
    lines.append("")
    lines.append("Counts: " + json.dumps(data["counts"]))
    return "\n".join(lines) + "\n"


def _tolerances(row: dict) -> str:
    """Rule 1's tolerance, then each relaxed rule's (the row's and its
    gating variants')."""

    cells = [f"{row['reference_tolerance']:.0e}"]
    for name, relaxed in [("", row.get("relaxed") or {})] + [
        (v["id"].split("@", 1)[1] + ": ", v.get("relaxed") or {})
        for v in row["variants"]
        if v["gating"] and v.get("relaxed") != row.get("relaxed")
    ]:
        cells += [f"{name}r{rule} {value:.0e}" for rule, value in relaxed.items()]
    return "; ".join(cells)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--findings", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--junit", nargs="*", type=Path, default=[])
    parser.add_argument("--meta", nargs="*", default=[])
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="the campaign manifest (default M-QCD's; M-SM: tests/fixtures/loop/"
        "msm/manifest.json with --output data/msm.json)",
    )
    args = parser.parse_args(argv)
    meta = dict(item.split("=", 1) for item in args.meta)
    findings = json.loads(args.findings.read_text()) if args.findings else None
    data = build(args.results, meta, findings, args.junit, args.manifest)
    args.output.write_text(json.dumps(data, indent=1, default=str) + "\n")
    if args.markdown:
        args.markdown.write_text(markdown(data))
    print(json.dumps(data["counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
