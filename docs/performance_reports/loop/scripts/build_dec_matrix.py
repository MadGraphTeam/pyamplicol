# SPDX-License-Identifier: 0BSD
"""Write data/dec-matrix.json, the decay capability matrix of the live loop report.

Usage: python scripts/build_dec_matrix.py [--output PATH]

Reads data/dec.json (scripts/build_mqcd.py on the decay manifest: the decay
campaign's rows XX01-XX08, their tiers, variants and delegated columns) and
the manifest tests/fixtures/loop/dec/manifest.json (model, restriction,
scheme, gauge, sectors, per-point inputs, Catani route, features), and writes
one entry per row: the largest deviations of double-double from MadLoop's
quadruple precision (rule 1), of binary64 from double-double (rule 2) and of
the poles from Catani (QCD) or Catani + QED (EW) in double-double (rule 4),
the Ward identity (XX07), the N_c scan (LC/NLC, QCD rows), the massless vector
form factor (XX04), the public route (Generator on the shipped loop_sm) and
the status, plus the further checks and the per-row appendix data. dec.json
may hold Infinity (an estimate out of scope); this file never does, so the
report reads dec.json only through it. Never edit the output by hand.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DATA = HERE / "data"
REPO = HERE.parents[2]
MANIFEST = "tests/fixtures/loop/dec/manifest.json"


def _sector(s: dict) -> str:
    return " ".join(f"{k}^{v}" for k, v in s.items())


def _max(xs: list[float | None]) -> float | None:
    vals = [x for x in xs if x is not None]
    return max(vals) if vals else None


def _tiers(entry: dict) -> list[dict]:
    return [
        {
            "tier": name,
            "points": len(t["points"]),
            "checks": t["checks"],
            "failures": t["failures"],
            "binary64_vs_reference": t["binary64_vs_reference"],
        }
        for name, t in entry["tiers"].items()
    ]


def _row(r: dict, m: dict) -> dict:
    tiers = list(r["tiers"].values())
    variants = r.get("variants", [])
    public = [v for v in variants if v["id"].endswith("@public")]
    ward = None
    for t in tiers:
        w = t.get("ward")
        if w:
            ward = {
                "checks": w["checks"],
                "virtual_dd": w["virtual_double-double"],
                "born_dd": w["born_double-double"],
                "virtual_binary64": w["virtual_double"],
                "born_binary64": w["born_double"],
            }
    out_of_scope = [
        {"tier": name, "point": x["point"], "sector": x["sector"], "coefficient": x["coefficient"]}
        for name, t in r["tiers"].items()
        for x in t["binary64_out_of_scope"]
    ]
    b64_ref = {}
    for t in tiers + [t for v in variants for t in v["tiers"].values()]:
        for k, v in t["binary64_vs_reference"].items():
            if v is not None:
                b64_ref[k] = max(b64_ref.get(k, 0.0), v)
    delegated = r.get("delegated", {})
    qed = "QED" in r["corrections"]
    return {
        "row": r["id"],
        "class": r["class"],
        "process": r["process"],
        "multiplicity": f"1->{len(r['process'].split('>')[1].split())}",
        "model": r["model"],
        "restriction": r["restriction"],
        "restriction_code": r["restriction_code"],
        "scheme": m.get("scheme"),
        "gauge": m.get("gauge"),
        "corrections": r["corrections"],
        "sectors": [_sector(s) for s in m.get("sectors", [])],
        "features": m.get("features", []),
        "inputs": m.get("inputs") or "tools",
        "catani_route": m.get("catani") or "python",
        "reference": r["reference_legend"],
        "tiers": _tiers(r),
        "points": sum(len(t["points"]) for t in tiers),
        "checks": sum(t["checks"] for t in tiers)
        + sum(t["checks"] for v in variants for t in v["tiers"].values()),
        "dd_vs_reference": r["max_dd_vs_reference"],
        "binary64_vs_dd": r["max_binary64_vs_dd"],
        "binary64_vs_reference": b64_ref,
        "binary64_out_of_scope": out_of_scope,
        "poles": "Catani + QED" if qed else "Catani",
        "catani_dd": r["max_catani_dd"],
        "ward": ward,
        "nc": None if "nc" not in delegated else {
            "status": delegated["nc"]["status"],
            "tests": len(delegated["nc"]["tests"]),
        },
        "ff": None if "ff" not in delegated else {
            "status": delegated["ff"]["status"],
            "tests": len(delegated["ff"]["tests"]),
        },
        "public": [
            {
                "id": v["id"],
                "status": v["status"],
                "points": sum(len(t["points"]) for t in v["tiers"].values()),
                "dd_vs_reference": _max([t["max_dd_vs_reference"] for t in v["tiers"].values()]),
            }
            for v in public
        ],
        "extras": r.get("extras", []),
        "status": r["status"],
        "source": f"data/dec.json rows[{r['id']}]; {MANIFEST} rows[{r['id']}]",
    }


def _largest(rows: list[dict], key: str) -> dict:
    best = max((r for r in rows if r[key] is not None), key=lambda r: r[key])
    return {"value": best[key], "row": best["row"]}


def build() -> dict:
    dec = json.loads((DATA / "dec.json").read_text())
    man = {r["id"]: r for r in json.loads((REPO / MANIFEST).read_text())["rows"]}
    rows = [_row(r, man[r["id"]]) for r in dec["rows"]]
    further = {
        "ff": [
            {"row": r["row"], "process": r["process"], **r["ff"],
             "check": "z > u u~ [QCD] = the massless vector form factor (analytic)"}
            for r in rows if r["ff"]
        ],
        "ward": [
            {"row": r["row"], "process": r["process"], **r["ward"],
             "check": "external gluon polarisation replaced by its momentum"}
            for r in rows if r["ward"]
        ],
        "nc": [
            {"row": r["row"], "process": r["process"], **r["nc"],
             "check": "LC and NLC = the kept powers of the N_c scan"}
            for r in rows if r["nc"]
        ],
    }
    return {
        "what": (
            "the decay capability matrix of docs/performance_reports/loop/benchmarks.typ,"
            " written by scripts/build_dec_matrix.py; do not edit by hand"
        ),
        "source": f"data/dec.json (scripts/build_mqcd.py on {MANIFEST}); {MANIFEST}",
        "campaign": {
            "slice": dec.get("slice"),
            "branch": dec.get("branch"),
            "native": dec.get("native"),
            "date": dec.get("date"),
            "counts": dec["counts"],
            "rules": dec.get("rules"),
        },
        "largest": {
            "dd_vs_reference": _largest(rows, "dd_vs_reference"),
            "binary64_vs_dd": _largest(rows, "binary64_vs_dd"),
            "catani_dd": _largest(rows, "catani_dd"),
        },
        "rows": rows,
        "further": further,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DATA / "dec-matrix.json")
    args = parser.parse_args(argv)
    args.output.write_text(json.dumps(build(), indent=1, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
