# SPDX-License-Identifier: 0BSD
"""Write data/msm-matrix.json, the report's M-SM capability matrix and CMS
table (m-sm/PLAN.md §5.2), from the campaign data in data/.

Usage: python scripts/build_msm_matrix.py [--output data/msm-matrix.json]
       python scripts/build_msm_matrix.py --import-public PUBLIC.xml
       python scripts/build_msm_matrix.py --import-selftest PYPI.json COMMUNITY.json

Inputs:

- data/msm.json            per-row results of the M-SM campaign (build_mqcd.py
                           --manifest tests/fixtures/loop/msm/manifest.json)
- data/msm-findings.json   the campaign's findings (status text: "open ...",
                           "accepted ...", "fixed ...", "resolved ...")
- data/msm-public.json     the campaign's public-route tests on the shipped EW
                           UFOs: the JUnit outcomes of
                           tests/unit/test_loop_v2_ew_public_models.py and its
                           PUBLIC_ROUTE cases (written by --import-public)
- data/msm-selftest.json   the wheel self-test in two fresh venvs (written by
                           --import-selftest from ``pyamplicol self-test
                           --json``)
- tests/fixtures/loop/msm/manifest.json  the manifest facts msm.json does not
                           carry: per-point inputs (native rows), mass scheme,
                           widths, unpredicted sectors and their reasons

Per class (m-sm/PLAN.md §1.1, in its order): rows and their statuses, the
largest final-state multiplicity, the models, the public route (the
PUBLIC_ROUTE cases and the self-test's EW virtual whose process is a row of
the class or of the rows the plan lists with it), the largest deviation of
double-double from the row's reference (rule 1; MadLoop unless named), of
binary64 from double-double (rule 2) and of binary64 from the reference
(information), the poles against Catani in double-double (rule 4; rows where
it is not formed, rows without a predicted sector, rows with a relaxed rule
4), the rows run on native per-point inputs, the complex-mass rows of the
class's processes, the open and accepted findings and a status. The CMS
table: every row of class W-CMS with its widths, variants and largest
deviations. Nothing is estimated: a value without a record stays null.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
REPO = Path(__file__).resolve().parents[4]
MANIFEST = REPO / "tests/fixtures/loop/msm/manifest.json"
PUBLIC_TESTS = REPO / "tests/unit/test_loop_v2_ew_public_models.py"
# The classes of m-sm/PLAN.md §1.1, in its order, with their content and
# the rows the plan lists with a class beyond its own prefix ("Rows").
CLASSES = {
    "W-lep": (
        "lepton-only [virt=QED], lines through the loop, Bhabha, W pairs, tops",
        (),
    ),
    "W-DY": (
        "neutral and charged Drell-Yan, lepton-hadron, + jets, alpha(MZ) twin",
        (),
    ),
    "W-V": ("V/photon + jet, VV, VVV, VH, VBF H", ()),
    "W-top": ("t t~ (joint QCD+QED), + jet, four tops, massive b, t t~ V/H/ll(+g)", ()),
    "W-singletop": ("s- and t-channel, tW; massless and massive b", ()),
    "W-jets": ("QCD processes with EW orders, every split order", ()),
    "W-photon": (
        "final and initial photons, tagged per leg",
        ("VJ03", "VV05", "VV06", "LL08", "CM09"),
    ),
    "W-CMS": ("internal widths > 0, coloured too; tagged photons; loop_sm", ()),
    "W-multi": ("multiparticle labels, no-Born members skipped (Q2)", ()),
    "W-scheme": (
        "alpha(MZ), massive mu, CKM, massive b, massive initial states, eps sign",
        ("TT04",),
    ),
}
PUBLIC_TEST = "test_public_route_on_the_shipped_qcd_qed_models_equals_the_tools_view"


def outgoing(process: str) -> int:
    return len(process.split(">")[1].split())


def _largest(items):
    items = [x for x in items if x[0] is not None]
    return max(items, key=lambda x: x[0]) if items else (None, None)


def _tiers(row: dict):
    """The row's tier records and those of its gating variants."""
    for tier in row["tiers"].values():
        yield row["id"], tier
    for variant in row["variants"]:
        if variant.get("gating"):
            for tier in variant["tiers"].values():
                yield variant["id"], tier


def binary64_vs_reference(row: dict):
    best = None
    out_of_scope = False
    for _, tier in _tiers(row):
        values = [
            v
            for v in (tier.get("binary64_vs_reference") or {}).values()
            if v is not None
        ]
        if values and (best is None or max(values) > best):
            best = max(values)
        out_of_scope |= bool(tier.get("binary64_out_of_scope"))
    return best, out_of_scope


def reference_name(row: dict) -> str:
    """The row's reference (a composite row: its variants'): MadLoop's
    quadruple precision (MS-REF) or its double-precision control exports
    (formats ew-control, cms-control), with the other providers named."""
    refs = [row.get("reference")] + [
        v.get("reference") for v in row["variants"] if v.get("gating")
    ]
    refs = [r for r in refs if r]
    if any(r.get("format") in ("ew-control", "cms-control") for r in refs):
        return "MadLoop (double)"
    providers = next((r.get("providers") for r in refs if r.get("providers")), [])
    if "madloop" in providers:
        others = [p.capitalize() for p in providers if p != "madloop"]
        return "MadLoop" + (f" + {', '.join(others)}" if others else "")
    return "/".join(p.capitalize() for p in providers) or "fixture"


def _status_kind(finding: dict) -> str:
    return str(finding.get("status", "")).split(" ", 1)[0]


def _sector(sector: dict) -> str:
    return " ".join(f"{k}^{v}" for k, v in sector.items() if v)


def build() -> dict:
    msm = json.loads((DATA / "msm.json").read_text())
    findings = json.loads((DATA / "msm-findings.json").read_text())["findings"]
    public = json.loads((DATA / "msm-public.json").read_text())
    selftest = json.loads((DATA / "msm-selftest.json").read_text())
    manifest = {r["id"]: r for r in json.loads(MANIFEST.read_text())["rows"]}
    rows = msm["rows"]
    by_id = {r["id"]: r for r in rows}

    # Public-route evidence: each case at the row of its process (same model
    # and restriction first, the real-mass row before the CMS twin), and the
    # wheel self-test's prepared EW virtual.
    def row_of(process: str, model: str, restriction: str | None) -> str | None:
        same = [r for r in rows if r["process"] == process]
        same.sort(
            key=lambda r: (
                r["model"] != model,
                r["restriction"] != (restriction or "default"),
                manifest[r["id"]].get("mass_scheme") == "complex-mass",
            )
        )
        return same[0]["id"] if same else None

    cases = []
    for name, case in public["cases"].items():
        cases.append(
            {
                "case": name,
                "row": row_of(case["process"], case["model"], case["restriction"]),
                "process": case["process"],
                "model": case["model"],
                "restriction": case["restriction"],
                "passed": case["outcome"] == "passed",
                "madloop_fixture": case["madloop_fixture"],
            }
        )
    prepared = [
        c
        for venv in ("pypi", "community")
        for c in selftest[venv]["checks"]
        if c["name"] == "physics-virtual-prepared"
    ]
    if prepared:
        m = re.match(
            r"(?P<process>.+?) \[virt=\w+\] on the shipped (?P<model>\S+) .*"
            r"= MadLoop to (?P<dev>\S+) at",
            prepared[0]["detail"],
        )
        if m is None:
            raise ValueError(
                f"msm-selftest.json: unread detail {prepared[0]['detail']}"
            )
        cases.append(
            {
                "case": "self-test",
                "row": row_of(m["process"], m["model"], None),
                "process": m["process"],
                "model": m["model"],
                "restriction": None,
                "passed": all(c["status"] == "pass" for c in prepared),
                "madloop_fixture": True,
                "dd_vs_madloop": None,
                "binary64_vs_madloop": float(m["dev"]),
            }
        )

    classes = []
    for cls, (content, also) in CLASSES.items():
        rs = [r for r in rows if r["class"] == cls]
        ids = {r["id"] for r in rs}
        related = ids | set(also)
        counts: dict[str, int] = {}
        for r in rs:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        dd, dd_row = _largest([(r["max_dd_vs_reference"], r["id"]) for r in rs])
        b64dd, b64dd_row = _largest([(r["max_binary64_vs_dd"], r["id"]) for r in rs])
        b64 = [(binary64_vs_reference(r), r["id"]) for r in rs]
        b64_value, b64_row = _largest([(v[0], rid) for v, rid in b64])
        catani, catani_row = _largest([(r["max_catani_dd"], r["id"]) for r in rs])
        not_formed = [
            r["id"]
            for r in rs
            if r.get("catani") == "none"
            or any(t.get("catani_not_formed") for t in r["tiers"].values())
        ]
        no_sector = [
            {
                "row": r["id"],
                "reasons": sorted(
                    set(manifest[r["id"]]["unpredicted_reasons"].values())
                ),
            }
            for r in rs
            if r["max_catani_dd"] is None
            and r["id"] not in not_formed
            and manifest[r["id"]].get("unpredicted_sectors")
        ]
        relaxed4 = [
            {"row": r["id"], "rule": k, "tolerance": v}
            for r in rs
            for k, v in sorted(r.get("relaxed", {}).items())
            if k in ("4", "4dd")
        ]
        native = [
            {"row": r["id"], "status": r["status"]}
            for r in rs
            if manifest[r["id"]].get("inputs") == "native"
        ]
        cms_procs = {by_id[x]["process"] for x in related if x in by_id}
        cms = [
            {"row": r["id"], "status": r["status"]}
            for r in rows
            if manifest[r["id"]].get("mass_scheme") == "complex-mass"
            and (r["class"] == cls or r["process"] in cms_procs or r["id"] in related)
        ]
        variant_ids = {v["id"] for r in rs for v in r["variants"]}
        open_findings = [
            {
                "id": f["id"],
                "rows": f["rows"],
                "kind": _status_kind(f),
                "status": f["status"],
            }
            for f in findings
            if _status_kind(f) in ("open", "accepted")
            and any(x in ids or x in variant_ids for x in f["rows"])
        ]
        covered = {
            x.split("@")[0]
            for f in open_findings
            if f["kind"] == "accepted"
            for x in f["rows"]
        }
        others = [r["id"] for r in rs if r["status"] != "pass"]
        if not others:
            status = "pass"
        elif all(rid in covered for rid in others):
            status = "accepted"
        else:
            status = "fail" if counts.get("fail") else "partial"
        classes.append(
            {
                "class": cls,
                "content": content,
                "rows": len(rs),
                "counts": counts,
                "max_outgoing": max(
                    (outgoing(r["process"]) for r in rs if ">" in r["process"]),
                    default=None,
                ),
                "models": sorted({r["model"] for r in rs}),
                "public": [c for c in cases if c["row"] in related],
                "dd_vs_reference": {
                    "value": dd,
                    "row": dd_row,
                    "reference": reference_name(by_id[dd_row]) if dd_row else None,
                },
                "binary64_vs_dd": {"value": b64dd, "row": b64dd_row},
                "binary64_vs_reference": {
                    "value": b64_value,
                    "row": b64_row,
                    "rows_out_of_scope": [rid for v, rid in b64 if v[1]],
                },
                "catani_dd": {
                    "value": catani,
                    "row": catani_row,
                    "not_formed": not_formed,
                    "no_predicted_sector": no_sector,
                    "relaxed": relaxed4,
                },
                "native_inputs": native,
                "cms": cms,
                "findings": open_findings,
                "status": status,
            }
        )
    unclassified = {r["class"] for r in rows} - set(CLASSES)
    if unclassified:
        raise ValueError(f"msm.json classes outside m-sm/PLAN.md §1.1: {unclassified}")

    cms_rows = []
    for r in rows:
        man = manifest[r["id"]]
        if man.get("mass_scheme") != "complex-mass":
            continue
        tier = next(iter(r["tiers"].values()))
        widths = {k: v for k, v in man["fixed_parameters"].items() if k.startswith("W")}
        cms_rows.append(
            {
                "row": r["id"],
                "process": r["process"],
                "model": r["model"],
                "restriction": r["restriction"],
                "corrections": r["corrections"],
                "tier": r["tier"],
                "inputs": man.get("inputs", "python"),
                "widths": widths or None,
                "points": len(tier["points"]),
                "checks": sum(t["checks"] for _, t in _tiers(r)),
                "variants": [
                    {
                        "id": v["id"],
                        "status": v["status"],
                        "notes": v.get("notes"),
                        "dd_vs_reference": max(
                            t["max_dd_vs_reference"] for t in v["tiers"].values()
                        ),
                    }
                    for v in r["variants"]
                    if v.get("gating")
                ],
                "reference": reference_name(r),
                "dd_vs_reference": r["max_dd_vs_reference"],
                "binary64_vs_dd": r["max_binary64_vs_dd"],
                "catani_dd": r["max_catani_dd"],
                "catani_binary64": max(
                    (
                        t["max_catani_binary64"]
                        for _, t in _tiers(r)
                        if t["max_catani_binary64"] is not None
                    ),
                    default=None,
                ),
                "unpredicted": [
                    {
                        "sector": _sector(s),
                        "reason": man["unpredicted_reasons"].get(_sector(s)),
                    }
                    for s in man.get("unpredicted_sectors", [])
                ],
                "ward_dd": None
                if tier["ward"] is None
                else {
                    "virtual": tier["ward"].get("virtual_double-double"),
                    "born": tier["ward"].get("born_double-double"),
                    "role": "diagnostic under CMS (m-sm/PLAN.md §1.4, §1.5)",
                },
                "features": man["features"],
                "status": r["status"],
            }
        )

    # Rule 4 in double-double (the Catani column) at its standard tolerance,
    # and the rows where the user's ruling of 2026-10-29 ~10:20 relaxes it
    # (manifest "relaxed" rule "4dd"), named apart with their tolerance.
    relaxed_rows = [
        {"row": r["id"], "value": r["max_catani_dd"], "tolerance": r["relaxed"]["4dd"]}
        for r in rows
        if r["max_catani_dd"] is not None and "4dd" in r.get("relaxed", {})
    ]
    standard = _largest(
        [
            (r["max_catani_dd"], r["id"])
            for r in rows
            if r["id"] not in {x["row"] for x in relaxed_rows}
        ]
    )
    named = {}
    for f in findings:
        for x in f["rows"]:
            named.setdefault(x.split("@")[0], []).append(f["id"])
    appendix = [
        {
            "row": r["id"],
            "class": r["class"],
            "process": r["process"],
            "model": r["model"],
            "restriction": r["restriction"],
            "corrections": r["corrections"],
            "points": {t: len(x["points"]) for t, x in r["tiers"].items()},
            "inputs": manifest[r["id"]].get("inputs", "python"),
            "reference": reference_name(r),
            "dd_vs_reference": r["max_dd_vs_reference"],
            "binary64_vs_dd": r["max_binary64_vs_dd"],
            "catani_dd": r["max_catani_dd"],
            "catani": r.get("catani"),
            "relaxed": r.get("relaxed", {}),
            "extras": r["extras"],
            "variants": [
                {"id": v["id"], "status": v["status"]}
                for v in r["variants"]
                if v.get("gating")
            ],
            "findings": sorted(set(named.get(r["id"], [])), key=lambda x: int(x[1:])),
            "status": r["status"],
        }
        for r in rows
    ]
    return {
        "source": "scripts/build_msm_matrix.py from data/msm.json, msm-findings.json,"
        " msm-public.json, msm-selftest.json and tests/fixtures/loop/msm/manifest.json",
        "campaign": {
            k: msm[k] for k in ("branch", "records", "natives", "counts", "rules")
        },
        "smokes_and_expansions": msm["smokes_and_expansions"],
        "coverage_notes": msm["coverage_notes"],
        "public_route": {
            "source": public["source"],
            "tests": {
                "total": len(public["tests"]),
                "passed": sum(t["outcome"] == "passed" for t in public["tests"]),
            },
            "dry_runs": [t["name"] for t in public["tests"] if "dry_run" in t["name"]],
        },
        "selftest": {
            "source": selftest["source"],
            "passed": all(
                c["status"] == "pass"
                for venv in ("pypi", "community")
                for c in selftest[venv]["checks"]
            ),
            "checks": len(selftest["pypi"]["checks"]),
            "virtuals": [
                {"name": c["name"], "detail": c["detail"]}
                for c in selftest["pypi"]["checks"]
                if c["name"].startswith("physics-virtual")
            ],
        },
        "classes": classes,
        "catani": {
            "standard": {"value": standard[0], "row": standard[1]},
            "relaxed": relaxed_rows,
        },
        "cms": cms_rows,
        "rows": appendix,
    }


def _public_cases() -> dict:
    """PUBLIC_ROUTE of the public-route test module: per case its model,
    restriction, process and MadLoop fixture (read with ast, not imported)."""
    tree = ast.parse(PUBLIC_TESTS.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "PUBLIC_ROUTE" for t in node.targets
        ):
            out = {}
            for key, value in zip(node.value.keys, node.value.values, strict=True):
                items = value.elts

                def const(n):
                    return n.value if isinstance(n, ast.Constant) else None

                out[key.value] = {
                    "model": const(items[0]),
                    "restriction": const(items[1]),
                    "process": const(items[2]),
                    "madloop_fixture": const(items[5]),
                }
            return out
    raise ValueError(f"{PUBLIC_TESTS}: no PUBLIC_ROUTE")


def import_public(junit: Path) -> dict:
    tests = []
    for case in ET.parse(junit).iter("testcase"):
        outcome = "passed"
        for child in case:
            if child.tag in ("failure", "error", "skipped"):
                outcome = {"failure": "failed"}.get(child.tag, child.tag)
        tests.append(
            {
                "name": case.get("name"),
                "outcome": outcome,
                "seconds": float(case.get("time")),
            }
        )
    by_name = {t["name"]: t for t in tests}
    cases = _public_cases()
    for name, case in cases.items():
        test = by_name.get(f"{PUBLIC_TEST}[{name}]")
        if test is None:
            raise ValueError(f"{junit}: no outcome for the public-route case {name}")
        case.update(outcome=test["outcome"], seconds=test["seconds"])
    return {
        "source": f"JUnit of tests/unit/test_loop_v2_ew_public_models.py (every tier,"
        f" one whole-file job) in the M-SM campaign ({junit.name}); cases: its"
        " PUBLIC_ROUTE (public route = tools view bitwise; = MadLoop QP where a"
        " fixture is named)",
        "cases": cases,
        "tests": tests,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DATA / "msm-matrix.json")
    parser.add_argument("--import-public", type=Path, metavar="JUNIT")
    parser.add_argument(
        "--import-selftest", type=Path, nargs=2, metavar=("PYPI", "COMMUNITY")
    )
    parser.add_argument("--source", default="", help="provenance line of an import")
    args = parser.parse_args(argv)
    if args.import_public:
        out = import_public(args.import_public)
        if args.source:
            out["source"] += f"; {args.source}"
        (DATA / "msm-public.json").write_text(json.dumps(out, indent=1) + "\n")
        return 0
    if args.import_selftest:
        pypi, community = (json.loads(p.read_text()) for p in args.import_selftest)
        out = {"source": args.source, "pypi": pypi, "community": community}
        (DATA / "msm-selftest.json").write_text(json.dumps(out, indent=1) + "\n")
        return 0
    # allow_nan=False: the report's JSON reader takes no Infinity (msm.json's
    # out-of-scope estimates may be infinite; none is copied here).
    args.output.write_text(json.dumps(build(), indent=1, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
