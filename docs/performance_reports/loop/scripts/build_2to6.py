# SPDX-License-Identifier: 0BSD
"""Build data/2to6.json (and the tables of m-final/2to6-report.md) from the
mf-2to6 run records: the 2->6 rows g g > 6g, u u~ > 6g and u u~ > u u~ 4g at
leading and full colour (M-FINAL item 1; MF-8G-3's 8-leg checks, MF-8Q, the
2->6 timing rows).

Inputs (read only): RUNS/<key>-<lc|fc>/ of tmp/mf-2to6 (the keeper's G1-harness
store records, stored_checks.py records, NGluon compares, the timing records
and the watchdog status files) and the stores' generation.json under ART.
Standard library only, no network, no clock: the output depends only on those
files. Stores are never opened beyond generation.json.

Usage:
  python3 -I build_2to6.py json RUNS ART PROCESSES_JSON --out data/2to6.json
  python3 -I build_2to6.py md RUNS ART PROCESSES_JSON [--notes FINDINGS.md] --out REPORT.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

KEYS = ("gg_gggggg", "uux_gggggg", "uux_uuxgggg")
TAGS = (("lc", "lc"), ("fc", "full"))
LAX = 1e-5  # USER 2026-10-29: a discrepancy below ~1e-5 relative is not a finding
BATCHES = ("16", "128")
NAMES = {21: "g", 2: "u", -2: "u~", 1: "d", -1: "d~"}


# Steps stopped on purpose (--not-run RUN/STEP=REASON): (run directory name, step) -> reason. A stopped step's
# partial record (no verdict) is ignored and the item is reported as not run with its reason.
NOT_RUN: dict[tuple[str, str], str] = {}


def _not_run(run: Path, step: str) -> str | None:
    return NOT_RUN.get((run.name, step))


def _read(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def _status(run: Path, step: str) -> dict | None:
    st = _read(run / f"{step}.status.json")
    if st is None:
        return None
    attempts = 1 + sum(1 for p in run.glob(f"killed-{step}-*") if p.is_dir())
    keep = (
        "start",
        "end",
        "elapsed_s",
        "peak_rss_gb",
        "gate_wait_s",
        "min_available_gb",
        "reason",
    )
    return {**{k: st.get(k) for k in keep}, "attempts": attempts}


def _max(xs):
    xs = [x for x in xs if x is not None]
    return max(xs) if xs else None


def _rel(a, b):
    return abs(a - b) / abs(b) if b else abs(a - b)


def _generation(
    run: Path, art: Path, t: str
) -> tuple[dict | None, dict | None, dict | None]:
    rec = _read(run / f"store-{t}.json")
    if rec is None:
        return None, None, None
    store_dir = art / f"{rec['process']}-{t}-{rec['revision'][:8]}"
    meta = _read(store_dir / "generation.json")
    stages = {
        k: {
            "s": v["seconds"],
            "peak_gib": v["peak_gib"],
            **({"plan_mb": v["plan_mb"]} if "plan_mb" in v else {}),
        }
        for k, v in rec["generation"].items()
    }
    artifact = None
    if meta is not None:
        st = meta["store"]
        stages["store"] = {"s": st["seconds"], "peak_gib": st["peak_gib"]}
        artifact = {
            "path": f"workspace/artifacts/2to6/{store_dir.name}/loop-runtime.pacbin",
            "bytes": st["bytes"],
            "gb": round(st["bytes"] / 1e9, 3),
            "plan_sha256": meta["plan_sha256"],
            "point_inputs": meta["point_inputs"],
        }
    gen = {
        "stages": stages,
        "stage_sum_s": round(sum(v["s"] for v in stages.values()), 1),
        "peak_gib": _max(v["peak_gib"] for v in stages.values()),
        "peak_note": "max of the per-stage VmHWM peaks (the harness resets the high-water mark per stage)",
        "step": _status(run, f"store-{t}"),
        "threads": None,
        "revision": rec["revision"],
        "dirty": rec["dirty"],
        "native": rec["native"],
    }
    return gen, artifact, rec


def _timing(run: Path, t: str, b: str) -> dict | None:
    rec = _read(run / f"time-{t}-b{b}.json")
    if rec is None or b not in rec.get("batches", {}):
        st = _status(run, f"time-{t}-b{b}")
        if (why := _not_run(run, f"time-{t}-b{b}")) is not None:
            return {"status": "not run", "why": why, "step": st}
        return None if st is None else {"status": "not measured", "step": st}
    s = rec["batches"][b]
    log = run / f"time-{t}-b{b}.log"
    core = None
    if log.exists():
        first = log.read_text().splitlines()[:1]
        if first and first[0].startswith("pinned to core"):
            core = int(first[0].split()[3])
    return {
        "status": "measured",
        "B": int(b),
        "lanes": rec["lanes"],
        "threads": 1,
        "host_core": core,
        "warm_up": {
            "points": rec["warm_up_points"][b],
            "s": rec["warm_up_seconds"][b],
            "note": "includes lazy compilation",
        },
        "timed": {
            "blocks": s["blocks"],
            "points_per_block": s["points_per_block"],
            "points": s["blocks"] * s["points_per_block"],
        },
        "s_per_point": s["median_seconds_per_point"],
        "stages_s_per_point": s["stages_per_point"],
        "load": rec["stored"]["load"],
        "peak_gib": rec["max_rss_gib"],
        "peak_note": "the timing process's ru_maxrss (load, warm-up and the block)",
        "step": _status(run, f"time-{t}-b{b}"),
        "revision": rec["revision"],
        "native": rec["native"],
        "loaded_from": "hard-linked copy of the store, every generation entry point raising (forbid_run.py)",
    }


def _checks(run: Path, t: str, acc: str, gluon_row: bool) -> dict:
    out: dict = {}
    c = _read(run / f"checks-{t}.json")
    if c is None:
        st = _status(run, f"checks-{t}")
        out["stored_checks"] = {
            "status": "not obtained",
            "why": "checks not run" if st is None else st["reason"],
            "step": st,
        }
    else:
        rows = c.get("checked", [])
        dp = [r["double_pole"] for r in rows if r.get("double_pole")]
        out["double_pole"] = {
            "status": "done",
            "verdict": "pass" if dp and all(x["passed"] for x in dp) else "fail",
            "max_deviation": _max(x["deviation"] / abs(x["universal"]) for x in dp),
            "points": [r["index"] for r in rows],
        }
        est = {r["index"]: r["relative_estimate"] for r in rows}
        out["stability"] = {
            "status": "done",
            "max_estimate": _max(est.values()),
            "estimates": est,
            "points": list(est),
            "points_above_1e-5": [
                k for k, v in est.items() if v is not None and v > LAX
            ],
        }
        if acc == "full":
            single, double, formed = [], [], []
            for r in rows:
                formed.append(r.get("catani_formed"))
                for s in r["sectors"].values():
                    if s.get("catani_deviation") is not None:
                        single.append(s["catani_deviation"][0] / abs(s["catani"][0]))
                        double.append(s["catani_deviation"][1] / abs(s["catani"][1]))
            dd_cat = [
                x
                for r in c.get("dd", [])
                for s in r.get("sectors", {}).values()
                for x in s.get("catani_relative", [])
            ]
            out["catani"] = {
                "status": "done",
                "passed": bool(formed)
                and all(formed)
                and all(
                    s.get("catani_passed") for r in rows for s in r["sectors"].values()
                ),
                "formed_at_every_point": bool(formed) and all(formed),
                "max_single_deviation": _max(single),
                "max_double_deviation": _max(double),
                "max_double_double_deviation": _max(dd_cat),
                "points": [r["index"] for r in rows],
                "rule": "native Catani prediction from the stored dipole orbits; each deviation <= 10 E + 1e-12",
            }
        dd = c.get("dd", [])
        if dd:
            d = dd[0]
            (s,) = d["sectors"].values()
            b64 = (
                next(r for r in rows if r["index"] == d["index"])
                if any(r["index"] == d["index"] for r in rows)
                else None
            )
            out["double_double"] = {
                "status": "done",
                "passed": all(x["passed"] for x in dd),
                "point": d["index"],
                "binary64_true_error_relative": [
                    x / abs(v) if v else x
                    for x, v in zip(s["deviation"], s["double_double"], strict=True)
                ],
                "binary64_true_error_finite_relative": s["deviation"][0]
                / abs(s["double_double"][0]),
                "binary64": {
                    "estimate_finite_relative": None
                    if b64 is None
                    else b64["relative_estimate"]
                },
                "within_10E": s.get("within_10E"),
            }
        rs = c.get("rescue")
        if rs:
            out["rescue"] = {
                "status": "done",
                "policy": "VirtualRescuePolicy() level 0 (binary64, rotation euler:0.1,0.2,0.3 + rescaled check), target 1e-5",
                "sent_up": rs["sent_up"],
                "count": rs["count"],
                "of": rs["of"],
                "max_level0_estimate": _max(rs["level0_estimates"].values()),
                "double_double": rs.get("double_double", {}),
                "double_double_seconds": c["stages"]
                .get("rescue double-double", {})
                .get("seconds"),
            }
        out["stored_checks"] = {
            # stored_checks.py rewrites its record after every stage: no verdict yet = still running
            "status": "done" if "passed" in c else "in progress",
            "why": None if "passed" in c else f"stages so far: {list(c['stages'])}",
            "passed": c.get("passed"),
            "stages": {
                k: {kk: v.get(kk) for kk in ("seconds", "peak_gib")}
                for k, v in c["stages"].items()
            },
            "max_rss_gib": c.get("max_rss_gib"),
            "step": _status(run, f"checks-{t}"),
        }
    wards = []
    running = []
    stopped = {
        name: why
        for name in (f"store-ward-{t}", f"ward-{t}", f"ward-{t}-dd")
        if (why := _not_run(run, name)) is not None
    }
    for name in (f"ward-{t}", f"ward-{t}-dd"):
        w = _read(run / f"{name}.json")
        if w is not None and "passed" in w:
            wards.append((name, w))
        elif w is not None and name not in stopped:
            # rewritten after every stage: no verdict yet = still running
            running.append(name)
    if running:
        out["ward"] = {
            "status": "in progress",
            "why": f"{', '.join(running)} running",
            "step": _status(run, running[0]),
        }
    elif wards:
        rows, legs = [], set()
        for _name, w in wards:
            for x in w.get("ward", []):
                legs.update(x["legs"])
                parts = [r for r in x["rows"] if r.get("leg") is not None]
                rows.append(
                    {
                        "point": x["index"],
                        "carrier": x["carrier"],
                        "asserted": x["asserted"],
                        "passed": x["passed"],
                        "legs": x["legs"],
                        "virtual_over_scale": [
                            max(abs(r["parts"]["virtual"][k]) for r in parts)
                            for k in range(3)
                        ],
                        "born_over_scale": max(abs(r["born"]) for r in parts),
                        "estimate_over_scale": [
                            max(r["estimate"][k] for r in parts) for k in range(3)
                        ]
                        if all(r.get("estimate") for r in parts)
                        else None,
                    }
                )
        asserted = [r for r in rows if r["asserted"]]
        b64 = [r for r in rows if r["carrier"] == "double"]
        dd = [r for r in rows if r["carrier"] != "double"]
        out["ward"] = {
            "status": "done" if asserted else "not asserted",
            "why": None
            if asserted
            else "every row beyond the binary64 scope (E > 1e-9): recorded, not asserted",
            "passed": bool(asserted) and all(r["passed"] for r in asserted),
            "asserted": [[r["point"], r["carrier"]] for r in asserted],
            "legs": sorted(legs),
            # binary64 rows, asserted or only recorded (an out-of-scope row stays below its estimate E)
            "max_virtual_ratio_finite_single_double": [
                _max(r["virtual_over_scale"][k] for r in b64) for k in range(3)
            ]
            if b64
            else None,
            "max_born_ratio": _max(r["born_over_scale"] for r in b64),
            "double_double_virtual_ratio": [
                _max(r["virtual_over_scale"][k] for r in dd) for k in range(3)
            ]
            if dd
            else None,
            "binary64_within_estimate": all(
                r["virtual_over_scale"][k] <= r["estimate_over_scale"][k]
                for r in b64
                if r["estimate_over_scale"]
                for k in range(3)
            )
            if b64
            else None,
            "rows": rows,
            "recorded_not_asserted": [r["point"] for r in rows if not r["asserted"]],
            "rule": "epsilon_j -> p_j / p_j^0 on the first, middle and last external gluon (stored gauge_legs); "
            "a binary64 point with E beyond the binary64 scope (1e-9) is recorded, not asserted; at 8 legs the "
            "double-double Ward (bound 1e-25 of the scale) runs at the Ward point of smallest level-0 E",
            "steps": {name: _status(run, name) for name, _ in wards},
            "not_run": stopped,
        }
    elif stopped:
        out["ward"] = {
            "status": "not run",
            "why": "; ".join(
                f"{', '.join(k for k, v in stopped.items() if v == why)}: {why}"
                for why in dict.fromkeys(stopped.values())
            ),
            "not_run": stopped,
        }
    elif (run / f"store-ward-{t}.status.json").exists() or (
        run / f"ward-{t}.status.json"
    ).exists():
        out["ward"] = {
            "status": "not obtained",
            "why": "Ward step not finished",
            "step": _status(run, f"ward-{t}") or _status(run, f"store-ward-{t}"),
        }
    if acc == "lc" and gluon_row:
        ng = {}
        for name in ("ngluon", "ngluon-dd"):
            cmp = _read(run / f"{name}-compare.json")
            if cmp is not None:
                ng[name] = {
                    "passed": cmp["passed"],
                    "worst": cmp["worst"],
                    "tolerance": cmp["tolerance"],
                    "estimates": cmp["estimates"],
                    "points": [r["index"] for r in cmp["rows"]],
                    "unmatched": cmp["unmatched"],
                    "rotation": cmp["rotation"],
                    "max_relative": [
                        _max(r["relative"][k] for r in cmp["rows"]) for k in range(3)
                    ],
                    "step": _status(run, name),
                }
        if ng:
            out["ngluon"] = {
                "status": "done",
                "passed": all(v["passed"] for v in ng.values()),
                **ng,
                "rule": "NJet 3.1.2 ngluon2 LC primitives on exactly rotated points; binary64 within "
                "1e-9 of the value + 10 E, double-double within 1e-12 of pyAmpliCol's DD point",
            }
    return out


def _row_engine(run: Path) -> dict | None:
    """The engine commit and native build of every record of a row (store, checks, Ward, timing)."""
    revisions, natives, records = set(), set(), []
    for f in sorted(run.glob("*.json")):
        if f.name.endswith(".status.json") or f.name.endswith("-compare.json"):
            continue
        rec = _read(f)
        nat = rec.get("native") if isinstance(rec, dict) else None
        if not isinstance(nat, dict) or "digest" not in nat:
            continue
        records.append(f.stem)
        natives.add((nat.get("directory"), nat["digest"]))
        revisions.add(rec.get("revision") or nat.get("source_revision"))
    if not records:
        return None
    return {
        "revision": sorted(revisions)[0] if len(revisions) == 1 else sorted(revisions),
        "native_directory": sorted(natives)[0][0] if len(natives) == 1 else None,
        "native_digest": sorted(natives)[0][1]
        if len(natives) == 1
        else sorted(natives),
        "one_engine": len(revisions) == 1 and len(natives) == 1,
        "records": records,
    }


EXPECTED = ("double_pole", "stability", "double_double", "rescue", "ward")


def not_obtained(d: dict) -> list[str]:
    """Every expected item of every row that failed, is missing or was not run (with the reason recorded)."""
    out = []
    for r in d["rows"]:
        label = r["label"]
        if r["generation"] is None:
            out.append(f"{label}: not generated (no store record)")
            continue
        eng = r.get("engine") or {}
        if eng and not eng.get("one_engine"):
            out.append(
                f"{label}: records on more than one engine: {eng['revision']} / {eng['native_digest']}"
            )
        for b in BATCHES:
            e = r["evaluations"].get(b)
            if e is None:
                out.append(f"{label}: timing B = {b} not run")
            elif e.get("status") == "not run":
                out.append(f"{label}: timing B = {b} not run ({e['why']})")
            elif e.get("status") != "measured":
                out.append(
                    f"{label}: timing B = {b} not measured ({(e.get('step') or {}).get('reason')})"
                )
        c = r["checks"]
        sc = c.get("stored_checks", {})
        if sc.get("status") != "done":
            out.append(f"{label}: stored checks not obtained ({sc.get('why')})")
        expected = list(EXPECTED)
        if r["accuracy"] == "full":
            expected.insert(1, "catani")
        if r["accuracy"] == "lc" and r["all_gluon"]:
            expected.append("ngluon")
        for k in expected:
            x = c.get(k)
            if x is None:
                if sc.get("status") == "done" or k in ("ward", "ngluon"):
                    out.append(f"{label}: {k} not run")
                continue
            if x.get("status") != "done":
                out.append(f"{label}: {k} {x.get('status')} ({x.get('why')})")
                continue
            ok = (
                x.get("verdict") == "pass"
                if k == "double_pole"
                else x.get("passed", True)
            )
            if not ok:
                out.append(f"{label}: {k} FAILED (see its table)")
        st = c.get("stability", {})
        if st.get("points_above_1e-5"):
            out.append(
                f"{label}: binary64 E above 1e-5 at points {st['points_above_1e-5']} (a rescue case, not a failure)"
            )
        w = c.get("ward", {})
        if w.get("status") in ("done", "not asserted"):
            for step, why in (w.get("not_run") or {}).items():
                out.append(f"{label}: {step} not run ({why})")
        if w.get("status") == "done" and w.get("recorded_not_asserted"):
            out.append(
                f"{label}: Ward recorded but not asserted at points {w['recorded_not_asserted']} (E beyond 1e-9)"
            )
        if r["accuracy"] == "lc" and not r["all_gluon"]:
            out.append(
                f"{label}: LC single pole unchecked (the native Catani operator is full colour only and NGluon "
                "serves only all-gluon rows); the LC double pole is checked"
            )
    return out


def build(runs: Path, art: Path, processes: Path, keys=KEYS) -> dict:
    spec = {p["name"]: p for p in json.loads(processes.read_text())["processes"]}
    rows, engine = [], None
    for key in keys:
        p = spec[key]
        gluon_row = all(int(x) == 21 for x in p["pdgs"])
        for t, acc in TAGS:
            run = runs / f"{key}-{t}"
            gen, artifact, rec = _generation(run, art, t)
            if rec is not None and engine is None:
                engine = {"revision": rec["revision"], "native": rec["native"]}
            evals = {b: e for b in BATCHES if (e := _timing(run, t, b)) is not None}
            measured = [e for e in evals.values() if e.get("status") == "measured"]
            main = max(measured, key=lambda e: e["B"]) if measured else None
            load = None
            if measured:
                load = {
                    "s": measured[0]["load"]["seconds"],
                    "peak_gib": measured[0]["load"]["peak_gib"],
                    "source": f"timing record B = {measured[0]['B']} (hard-linked copy, generation forbidden)",
                }
            rows.append(
                {
                    "key": f"{key}-{acc}",
                    "process": rec["process_text"] if rec else None,
                    "label": f"{' '.join(NAMES[int(x)] for x in p['pdgs'][:2])} > "
                    f"{' '.join(NAMES[int(x)] for x in p['pdgs'][2:])} ({t.upper()}, N_f = 5, no top)",
                    "accuracy": acc,
                    "all_gluon": gluon_row,
                    "particle_veto": p.get("particle_veto", []),
                    "particle_veto_note": "PDG [6] (processes.json): top-free massless five-flavour QCD (USER Q-A 2026-10-31)",
                    "born_orders": p["born_orders"],
                    "correction": p["correction"],
                    "lanes": (rec or {}).get("lanes"),
                    "structure": (rec or {}).get("structure"),
                    "generation": gen,
                    "artifact": artifact,
                    "load": load,
                    "evaluation": main,
                    "evaluations": evals,
                    "table1": {
                        "eval_peak_gib": None if main is None else main["peak_gib"],
                        "gate": "none: no provider at 2->6 (speed reported without a gate)",
                    },
                    "checks": _checks(run, t, acc, gluon_row),
                    "engine": _row_engine(run),
                }
            )
    return {
        "schema": "pyamplicol-2to6/2",
        "status": "M-FINAL 2->6 rows (mf-2to6): fresh generation, store, load and checks on one engine",
        "engine": {
            "branch": "work/v2-mf-8g-3",
            "base": "d24a01ae (slice: mf-8g-2b integrated) + mf-8g-3",
            "revision": None if engine is None else engine["revision"],
            "native": None if engine is None else engine["native"],
            "native_digest_short": None
            if engine is None
            else engine["native"]["digest"][:8],
            "harness_commits": {},
            "engine_source_change_vs_base": "mf-8g-3 (native Catani prediction from stored dipole orbits, stored_checks.py, NGluon driver)",
            "protocol": "timing: binary64, finite part only (poles off), no stability check, one thread on one pinned "
            "core, warm-up 16 points excluded, one block of B points, setup heap frozen out of the cyclic "
            "collector; indicative (shared host)",
        },
        "stop": {
            "text": "lifted by the coordinator for mf-2to6 (slice-status DECISIONS 2026-11-04 ~08:35 UTC)",
            "source": "workspace/tmp/STOP-8LEG",
        },
        "units": {
            "s": "seconds wall",
            "gib": "2^30 bytes (VmHWM / ru_maxrss)",
            "gb": "1e9 bytes (watchdog process-group VmRSS samples)",
            "s_per_point": "seconds per phase-space point, one thread",
        },
        "lax_precision_threshold": LAX,
        "global_caveats": [
            "no external reference exists at 2->6: acceptance is internal (Ward, rotations, Catani poles, double pole, double-double, NGluon at LC)",
            "timings are indicative: shared host (load 100-250 of 384 cores), one pinned thread, one block per B",
        ],
        "row_caveats": {},
        "rows": rows,
    }


HEADER = """\
# M-FINAL 2->6 rows (mf-2to6): g g > 6g, u u~ > 6g, u u~ > u u~ 4g at LC and FC

Package mf-2to6 (M-FINAL item 1, closing: MF-8G-3's 8-leg runs, MF-8Q, the 2->6
timing rows). Data: `docs/performance_reports/loop/data/2to6.json` on
`work/v2-mf-2to6`; this file's tables are printed by
`docs/performance_reports/loop/scripts/build_2to6.py md`. Records:
`workspace/tmp/mf-2to6/runs/<key>-<lc|fc>/`; artifacts (kept):
`workspace/artifacts/2to6/<key>-<lc|fc>[-ward]-<sha8>/`.

**Engine (every row):** {engine_line}

**Method.** (1) generate + export + store with the G1 harness (`--inputs native
--kernels production --store`, 24 threads, 16 for the quark rows): stage times
and VmHWM peaks from the harness record, the step's process-group peak from the
watchdog. (2) `tools/loop_benchmark/stored_checks.py` on the store (loaded as the
runtime loads it, nothing regenerated): binary64 at stream points 0 1 2 with every
pole and the recommended checks (E: rotation + rescaled reduction estimate), the
universal double pole, Catani's poles at FC (native, from the stored dipole
orbits; each deviation <= 10 E + 1e-12), double-double at point 0 against
binary64, and the default rescue policy's level 0 on points 0-15 (its DD level on
at most 2 points incl. the DD point; never the arbitrary level). (3) Ward on a
second store generated on the full tree kernels: epsilon_j -> p_j / p_j^0 on the
first, middle and last external gluon at the three stream points of smallest
level-0 E (binary64; at FC also double-double at the first). (4) At LC on the
all-gluon row: NGluon (NJet 3.1.2 `ngluon2` LC primitives) on exactly rotated
points (quaternion (5, 3, -2, 7)), binary64 at points 0-2 within 1e-9 + 10 E,
double-double at point 0 within 1e-12 of pyAmpliCol's DD point (the LC single
pole: the native Catani operator is full colour only). (5) Timing: the store
loaded from a hard-linked copy with every generation entry point raising,
binary64, finite part only, checks off, one thread pinned to an idle core,
warm-up 16 points, then one block of B = 16 and (separate job) B = 128 points;
indicative (shared host). Jobs ran as systemd user units under a watchdog (start:
MemAvailable minus our other live jobs' remaining expected peak >= peak + ~110 GB
held 10 min; kill only below 100 GB host free, youngest first; retried).
Precision is lax: a deviation below ~1e-5 relative is not a finding.
"""


def _e(x) -> str:
    return "-" if x is None else f"{x:.1e}"


def _t(s) -> str:
    if s is None:
        return "-"
    return (
        f"{s:.0f} s"
        if s < 600
        else (f"{s / 60:.1f} min" if s < 10800 else f"{s / 3600:.2f} h")
    )


def _verdict(c: dict) -> str:
    keys = ("double_pole", "catani", "double_double", "ward", "ngluon")
    out = []
    for k in keys:
        x = c.get(k)
        if not x:
            continue
        if x.get("status") != "done":
            out.append(f"{k} {x.get('status')}")
            continue
        ok = x.get("verdict") == "pass" if k == "double_pole" else x.get("passed")
        out.append(f"{k} {'pass' if ok else 'FAIL'}")
    if "rescue" in c:
        out.append(f"rescue {c['rescue']['count']}/{c['rescue']['of']}")
    return "; ".join(out) or "-"


def _engine(e: dict | None) -> str:
    if not e:
        return "-"
    if not e["one_engine"]:
        return f"MIXED {e['revision']} / {e['native_digest']}"
    return f"`{e['revision'][:8]}` / `{e['native_digest'][:8]}`"


def summary(d: dict) -> list[str]:
    out = [
        "| Row | generation (gen + export + store) / peak | artifact | load / resident peak "
        "| s/pt B = 16 / peak | s/pt B = 128 / peak | checks | engine / native |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in d["rows"]:
        g = r["generation"]
        if g is None:
            out.append(f"| {r['label']} | not generated | | | | | | |")
            continue
        st = g["stages"]
        gen = sum(st[k]["s"] for k in ("generate", "export", "store") if k in st)
        ev = []
        for b in BATCHES:
            e = r["evaluations"].get(b)
            if e and e.get("status") == "measured":
                ev.append(f"{e['s_per_point']:.2f} / {e['peak_gib']:.1f} GiB")
            else:
                ev.append("-" if not e else e.get("status", "-"))
        load = r["load"]
        out.append(
            f"| {r['label']} | {_t(gen)} / {g['peak_gib']:.1f} GiB | {(r['artifact'] or {}).get('gb')} GB "
            f"| {'-' if not load else _t(load['s']) + ' / ' + format(load['peak_gib'], '.1f') + ' GiB'} "
            f"| {ev[0]} | {ev[1]} | {_verdict(r['checks'])} | {_engine(r.get('engine'))} |"
        )
    return out


def markdown(d: dict, notes: str = "") -> str:
    e = d["engine"]
    nat = e["native"] or {}
    prof = nat.get("profile", {})
    engine_line = (
        f"`{e['branch']}` at `{(e['revision'] or '')[:8]}` ({e['base']}); native "
        f"`{nat.get('directory')}` (digest `{(nat.get('digest') or '')[:8]}...`, release CGU "
        f"{prof.get('CARGO_PROFILE_RELEASE_CODEGEN_UNITS')}, LTO {prof.get('CARGO_PROFILE_RELEASE_LTO')})."
    )
    out = [
        HEADER.format(engine_line=engine_line),
        "## Summary\n",
        *summary(d),
        "",
        *([notes.rstrip() + "\n"] if notes else []),
        "## Tables per process\n",
    ]
    for r in d["rows"]:
        out.append(f"### {r['label']}\n")
        g = r["generation"]
        if g is None:
            out.append("not generated\n")
            continue
        st = g["stages"]
        step = g["step"] or {}
        out.append("| Stage | time | peak |\n|---|---|---|")
        for k in ("model", "generate", "export", "store"):
            if k in st:
                extra = (
                    f" (plan {st[k]['plan_mb']:.0f} MB)" if "plan_mb" in st[k] else ""
                )
                out.append(
                    f"| {k}{extra} | {_t(st[k]['s'])} | {st[k]['peak_gib']:.1f} GiB |"
                )
        out.append(
            f"| step (watchdog; {step.get('attempts')} attempt(s), gate wait {_t(step.get('gate_wait_s'))}) | "
            f"{_t(step.get('elapsed_s'))} | {step.get('peak_rss_gb')} GB group |"
        )
        a = r["artifact"] or {}
        out.append(f"| artifact | {a.get('gb')} GB | |")
        if r["load"]:
            out.append(
                f"| load (hard-linked copy, generation forbidden) | {_t(r['load']['s'])} | {r['load']['peak_gib']:.2f} GiB |"
            )
        for b, e in r["evaluations"].items():
            if e.get("status") == "measured":
                out.append(
                    f"| eval B = {b} (warm-up {e['warm_up']['points']} pts {_t(e['warm_up']['s'])}) | "
                    f"**{e['s_per_point']:.2f} s/pt** | {e['peak_gib']:.1f} GiB |"
                )
            else:
                out.append(
                    f"| eval B = {b} | {e.get('status')} ({e.get('why') or (e.get('step') or {}).get('reason')}) | |"
                )
        out.append("")
        c = r["checks"]
        out.append("| Check | value | pass |\n|---|---|---|")
        if "double_pole" in c:
            out.append(
                f"| double pole vs universal (pts {c['double_pole']['points']}) | {_e(c['double_pole']['max_deviation'])} | {c['double_pole']['verdict']} |"
            )
        if "stability" in c:
            s = c["stability"]
            out.append(
                f"| E (rotation + rescaled), pts {s['points']} | {', '.join(_e(v) for v in s['estimates'].values())} | "
                f"{'pass' if not s['points_above_1e-5'] else 'rescue case ' + str(s['points_above_1e-5'])} |"
            )
        if "catani" in c:
            k = c["catani"]
            out.append(
                f"| Catani poles (1/eps, 1/eps^2; DD) | {_e(k['max_single_deviation'])}, {_e(k['max_double_deviation'])}; "
                f"{_e(k['max_double_double_deviation'])} | {'pass' if k['passed'] else 'FAIL'} |"
            )
        if "double_double" in c:
            k = c["double_double"]
            out.append(
                f"| DD - binary64, pt {k['point']} (finite, 1/eps, 1/eps^2) vs E {_e(k['binary64']['estimate_finite_relative'])} | "
                f"{', '.join(_e(x) for x in k['binary64_true_error_relative'])} | {'pass' if k['passed'] else 'FAIL'} |"
            )
        if "rescue" in c:
            k = c["rescue"]
            dd = "; ".join(
                f"pt {p}: E {v['estimate']:.1e} met {v['met']}"
                for p, v in k["double_double"].items()
            )
            out.append(
                f"| rescue level 0: sent up | {k['count']} of {k['of']} {k['sent_up']} (max E {_e(k['max_level0_estimate'])}){'; DD ' + dd if dd else ''} | - |"
            )
        if "ward" in c:
            w = c["ward"]
            if w["status"] in ("done", "not asserted"):
                for x in w["rows"]:
                    verdict = (
                        ("pass" if x["passed"] else "FAIL")
                        if x["asserted"]
                        else "recorded, not asserted (E > 1e-9)"
                    )
                    est = (
                        f" (E {', '.join(_e(v) for v in x['estimate_over_scale'])})"
                        if x.get("estimate_over_scale")
                        else ""
                    )
                    out.append(
                        f"| Ward {'DD' if x['carrier'] != 'double' else 'binary64'} pt {x['point']}, legs {x['legs']} "
                        f"(virtual/scale finite, 1/eps, 1/eps^2; Born/scale) | "
                        f"{', '.join(_e(v) for v in x['virtual_over_scale'])}; {_e(x['born_over_scale'])}{est} | {verdict} |"
                    )
                for step, why in (w.get("not_run") or {}).items():
                    out.append(f"| Ward {step} | not run ({why}) | - |")
                if w["status"] == "not asserted":
                    out.append(f"| Ward verdict | {w['why']} | - |")
            else:
                out.append(f"| Ward | {w['status']} ({w.get('why')}) | - |")
        if "ngluon" in c:
            for name in ("ngluon", "ngluon-dd"):
                if name in c["ngluon"]:
                    k = c["ngluon"][name]
                    out.append(
                        f"| NGluon LC {'DD' if name.endswith('dd') else 'binary64'} pts {k['points']} (finite, 1/eps, 1/eps^2) | "
                        f"{', '.join(_e(x) for x in k['max_relative'])} (tol {k['tolerance']:.0e}{' + 10 E' if k['estimates'] else ''}) | "
                        f"{'pass' if k['passed'] else 'FAIL'} |"
                    )
        out.append("")
    out.append("## What failed or could not run\n")
    items = d.get("not_obtained")
    if items is None:
        items = not_obtained(d)
    out.extend(f"- {x}" for x in items) if items else out.append("- nothing")
    out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("mode", choices=("json", "md"))
    parser.add_argument("runs", type=Path)
    parser.add_argument("art", type=Path)
    parser.add_argument("processes", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--not-run",
        action="append",
        default=[],
        metavar="RUN/STEP=REASON",
        help="a step stopped on purpose (e.g. gg_gggggg-fc/time-fc-b128=...), repeatable",
    )
    parser.add_argument(
        "--notes",
        type=Path,
        help="md mode: a markdown file inserted after the summary (findings)",
    )
    parser.add_argument(
        "--keys",
        nargs="+",
        default=list(KEYS),
        help="rows (default: the three 2->6 rows)",
    )
    o = parser.parse_args(argv)
    for item in o.not_run:
        where, why = item.split("=", 1)
        run, step = where.split("/", 1)
        NOT_RUN[(run, step)] = why
    d = build(o.runs, o.art, o.processes, tuple(o.keys))
    d["not_run_on_purpose"] = {f"{r}/{st}": why for (r, st), why in NOT_RUN.items()}
    d["not_obtained"] = not_obtained(d)
    text = (
        json.dumps(d, indent=1, sort_keys=False) + "\n"
        if o.mode == "json"
        else markdown(d, o.notes.read_text() if o.notes else "")
    )
    if o.out:
        o.out.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
