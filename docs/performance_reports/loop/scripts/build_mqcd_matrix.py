# SPDX-License-Identifier: 0BSD
"""Write data/mqcd-matrix.json, the report's QCD capability matrix and FFT
cost table (m-qcd/PLAN.md §5.2), from the campaign data in data/.

Usage: python scripts/build_mqcd_matrix.py [--output data/mqcd-matrix.json]

Inputs (all in data/):

- mqcd.json            per-row results of the M-QCD campaign (build_mqcd.py)
- mqcd-findings.json   the campaign's findings (status open / resolved)
- mqcd-public.json     public-route representatives (Generator on the shipped
                       loop_sm, Runtime.load, rules 1-3), one row per class
- mqcd-fft-cost.json   FFT against direct seed contraction at B = 128
- mqcd-fft-worst.json  FFT against direct at the cost runs' worst points

Per class: rows and their statuses, the largest final-state multiplicity, the
public route (its representative and the campaign's own public variants), the
largest deviation from the row's binding reference in double-double (rule
1), of binary64 from double-double where binary64 is asserted (rule 2, the O1
scope E <= 1e-9) and of binary64 from the reference at every point
(information; rows with binary64 points outside the O1 scope are named),
the poles against Catani in double-double (rule 4; rows without a predicted
sector or without the tree engine's correlations named), LC/NLC (rule 7's
delegated column), the FFT cost rows of the class and the open findings.
Nothing is estimated: a value without a record stays null.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
# The classes of m-qcd/PLAN.md §1.1, in its order, with their content.
CLASSES = {
    "Q-massless": "gluons and massless quark lines, every initial state",
    "Q-top": "t t~ + jets, t t~ with quark lines, four tops",
    "Q-heavy": "massive b (4FS) and c, b-Yukawa Higgs",
    "Q-EWBorn": "QCD corrections to Borns with QED >= 1",
    "Q-ttX": "t t~ + H/Z, t t~ + leptons, e+ e- > t t~ (h)",
    "Q-singletop": "s- and t-channel, tW, 4FS t-channel",
    "Q-mixed": "several Born orders, every squared split order",
    "Q-CKM": "non-diagonal CKM on W lines",
    "Q-multi": "multiparticle labels (p p > t t~)",
}
# Public-route evidence outside the representatives' file: the campaign's
# own public variants of the multiparticle row (their subprocesses
# u u~ > t t~ and g g > t t~ are Q-top processes).
PUBLIC_VARIANTS = {
    "Q-top": ("M01@public-P0", "M01@public-P2"),
    "Q-multi": ("M01@public-P0", "M01@public-P2"),
}
LIGHT = {"g", "u", "u~", "d", "d~", "s", "s~", "c", "c~", "b", "b~"}


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
    best = (None, None)
    out_of_scope = False
    for rid, tier in _tiers(row):
        values = [
            v
            for v in (tier.get("binary64_vs_reference") or {}).values()
            if v is not None
        ]
        if values and (best[0] is None or max(values) > best[0]):
            best = (max(values), rid)
        out_of_scope |= bool(tier.get("binary64_out_of_scope"))
    return best[0], out_of_scope


def reference_name(row: dict) -> str:
    """The row's binding reference (a composite row: its variants')."""
    refs = [row.get("reference")] + [
        v.get("reference") for v in row["variants"] if v.get("gating")
    ]
    providers = next((r.get("providers") for r in refs if r), None) or []
    if "madloop" in providers:
        return "MadLoop"
    if any(p.startswith("njet") for p in providers):
        return "NJet DD"
    return "/".join(p.capitalize() for p in providers) or "—"


def build() -> dict:
    mqcd = json.loads((DATA / "mqcd.json").read_text())
    findings = json.loads((DATA / "mqcd-findings.json").read_text())["findings"]
    public = json.loads((DATA / "mqcd-public.json").read_text())
    cost = json.loads((DATA / "mqcd-fft-cost.json").read_text())
    worst = json.loads((DATA / "mqcd-fft-worst.json").read_text())
    rows = mqcd["rows"]
    by_id = {r["id"]: r for r in rows}
    variants = {v["id"]: v for r in rows for v in r["variants"]}
    by_process: dict[str, str] = {}
    for r in rows:  # the first row of a process names its class
        by_process.setdefault(r["process"], r["class"])
    smoke = mqcd["smokes_and_expansions"].get("lc:every_restriction", {}).get("status")

    fft_rows = []
    for c in cost["rows"]:
        cls = by_process.get(c["process"])
        if cls is None and set(c["process"].replace(">", " ").split()) <= LIGHT:
            cls = "Q-massless"
        total, seed = c["seconds"], c["seed_contraction_seconds"]
        fft_rows.append(
            {
                "name": c["name"],
                "process": c["process"],
                "class": cls,
                "group_order": c.get("group_order"),
                "pairs": c.get("pairs"),
                "algorithm": c["algorithm"],
                "total_fft_s": total["fft"],
                "total_direct_s": total["direct"],
                "total_ratio": total["fft"] / total["direct"],
                "seed_fft_s": seed["fft"],
                "seed_direct_s": seed["direct"],
                "seed_ratio": seed["fft"] / seed["direct"],
            }
        )

    classes = []
    for cls, content in CLASSES.items():
        rs = [r for r in rows if r["class"] == cls]
        counts: dict[str, int] = {}
        for r in rs:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        dd, dd_row = _largest([(r["max_dd_vs_reference"], r["id"]) for r in rs])
        b64 = [(binary64_vs_reference(r), r["id"]) for r in rs]
        b64_value, b64_row = _largest([(v[0], rid) for v, rid in b64])
        catani, catani_row = _largest([(r["max_catani_dd"], r["id"]) for r in rs])
        # Rule 4 not formed on the row's own tiers (the public variants
        # check rules 1-3 only), and rows whose sectors are all unpredicted
        # (checked against the reference per split order only).
        not_formed = [
            r["id"]
            for r in rs
            if any(t.get("catani_not_formed") for t in r["tiers"].values())
        ]
        no_catani = [
            r["id"]
            for r in rs
            if r["max_catani_dd"] is None and r["tiers"] and r["id"] not in not_formed
        ]
        b64dd, b64dd_row = _largest([(r["max_binary64_vs_dd"], r["id"]) for r in rs])
        nc_rows = [r["id"] for r in rs if r.get("nc")]
        nc_status = sorted({r["nc"]["status"] for r in rs if r.get("nc")})
        pub = [
            p for p in public["rows"] if by_id[p["row"].split("@")[0]]["class"] == cls
        ]
        pub_entries = [
            {
                "row": p["row"],
                "process": by_id[p["row"].split("@")[0]]["process"],
                "passed": p["passed"],
                "points": len(p["points"]),
                "dd_vs_reference": p["max_dd_vs_reference"],
                "binary64_vs_dd": p["max_binary64_vs_dd"],
            }
            for p in pub
        ]
        for vid in PUBLIC_VARIANTS.get(cls, ()):
            v = variants[vid]
            tier = next(iter(v["tiers"].values()))
            pub_entries.append(
                {
                    "row": vid,
                    "process": None,
                    "passed": v["status"] == "pass",
                    "points": len(tier["points"]),
                    "dd_vs_reference": tier["max_dd_vs_reference"],
                    "binary64_vs_dd": tier["max_binary64_vs_dd"],
                }
            )
        ids = {r["id"] for r in rs} | {v["id"] for r in rs for v in r["variants"]}
        open_findings = [
            {
                "id": f["id"],
                "rows": f["rows"],
                "accepted": "accepted" in f.get("status_note", ""),
                "note": f.get("status_note"),
            }
            for f in findings
            if f.get("status") == "open" and any(x in ids for x in f["rows"])
        ]
        # pass: every row passes; accepted: every other row is explained by
        # an open finding the coordinator accepted (status_note).
        covered = {
            x.split("@")[0] for f in open_findings if f["accepted"] for x in f["rows"]
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
                "max_outgoing": max(outgoing(r["process"]) for r in rs),
                "public": pub_entries,
                "dd_vs_reference": {
                    "value": dd,
                    "row": dd_row,
                    "reference": reference_name(by_id[dd_row]) if dd_row else None,
                },
                "binary64_vs_dd": {"value": b64dd, "row": b64dd_row},
                "binary64_vs_reference": {
                    "value": b64_value,
                    "row": b64_row,
                    "reference": reference_name(by_id[b64_row]) if b64_row else None,
                    "rows_out_of_scope": [rid for v, rid in b64 if v[1]],
                },
                "catani_dd": {
                    "value": catani,
                    "row": catani_row,
                    "no_predicted_sector": no_catani,
                    "not_formed": not_formed,
                },
                "nc": {
                    "rows": nc_rows,
                    "status": nc_status,
                    "smoke_every_restriction": smoke,
                },
                "fft": [f["name"] for f in fft_rows if f["class"] == cls],
                "findings": open_findings,
                "status": status,
            }
        )
    worst_by: dict[str, dict[str, float]] = {}
    for w in worst["rows"]:
        k = worst_by.setdefault(
            w["carrier"], {"ratio_to_envelope": 0.0, "relative": 0.0}
        )
        k["ratio_to_envelope"] = max(k["ratio_to_envelope"], w["ratio_to_envelope"])
        k["relative"] = max(k["relative"], w["fft_vs_direct_rel"])
    return {
        "source": "scripts/build_mqcd_matrix.py from data/mqcd.json,"
        " mqcd-findings.json, mqcd-public.json, mqcd-fft-cost.json and"
        " mqcd-fft-worst.json",
        "campaign": {k: mqcd[k] for k in ("campaign_head", "native", "date", "counts")},
        "public_route": public["route"],
        "classes": classes,
        "fft": {
            "protocol": cost["protocol"],
            "rows": fft_rows,
            "worst": {
                "what": worst["what"],
                "max_by_carrier": worst_by,
                "points": len(worst["rows"]),
            },
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DATA / "mqcd-matrix.json")
    args = parser.parse_args(argv)
    args.output.write_text(json.dumps(build(), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
