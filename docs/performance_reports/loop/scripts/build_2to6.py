# SPDX-License-Identifier: 0BSD
"""Build 2to6.json: the PRELIMINARY 2->6 rows (g g > 6g LC/FC, u u~ > 6g LC,
u u~ > u u~ 4g LC) harvested from the existing bench-2to6 records.

Deterministic, standard library only, no network, no clock: the output depends
only on the files named on the command line (identified by their trailing path
components, so their location and order do not matter). Every number comes
from those raw records (harness JSON, watchdog status/log files, guard logs,
stored-artifact generation.json); the few numbers that exist only in prose
(STATE.md lines) are written as strings under a "prose_only" key with their
source. 8-leg artifacts are never opened (their size is the store record's).

Usage (one line):
  python3 build_2to6.py --out 2to6.json \\
    B/runs/{time,stability-time}-{gg_gggggg,uux_gggggg,uux_uuxgggg}-lc.json \\
    B/runs/time-rot-gg_gggggg-full.json \\
    B/runs/catani-{gg_gggggg-lc,uux_gggggg-lc,uux_gggggg-lc.killed-2245,uux_uuxgggg-lc}.json \\
    B/runs/{dd,ward}-uux_uuxgggg-lc.json \\
    B/logs/<status/log files listed in REQUIRED> B/dryrun/*.json B/estimates.json \\
    B/smoke/catani-gg_ggg-2.json A/{gg_gggggg-lc,gg_gggggg-full,uux_gggggg-lc,uux_uuxgggg-lc}/generation.json \\
    W/tmp/STOP-8LEG W/reports/engine-v2/m-final/8g0-report.md \\
    <work/v2-bench-2to6 worktree>/tools/loop_benchmark/processes.json
with W = workspace, B = W/tmp/bench-2to6, A = W/artifacts/2to6. The exact list of the
58 inputs is in args.txt next to this script: python3 -I build_2to6.py --out 2to6.json $(cat args.txt)
(Python >= 3.11; output checked byte-identical under 3.11 and 3.14 and for any argument order).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROWS = ("gg_gggggg-lc", "gg_gggggg-full", "uux_gggggg-lc", "uux_uuxgggg-lc")
GIB_PER_GB = 1e9 / 2**30
LAX = 1e-5  # USER 2026-10-29: a discrepancy below ~1e-5 relative is not a finding

REQUIRED = (
    # timing / stability / checks (harness records)
    "runs/time-gg_gggggg-lc.json", "runs/stability-time-gg_gggggg-lc.json",
    "runs/time-uux_gggggg-lc.json", "runs/stability-time-uux_gggggg-lc.json",
    "runs/time-uux_uuxgggg-lc.json", "runs/stability-time-uux_uuxgggg-lc.json",
    "runs/time-rot-gg_gggggg-full.json",
    "runs/catani-gg_gggggg-lc.json", "runs/catani-uux_gggggg-lc.json",
    "runs/catani-uux_gggggg-lc.killed-2245.json", "runs/catani-uux_uuxgggg-lc.json",
    "runs/dd-uux_uuxgggg-lc.json", "runs/ward-uux_uuxgggg-lc.json",
    # watchdog status / logs
    "logs/store-gg_gggggg-lc.status.json", "logs/store-gg_gggggg-full.status.json",
    "logs/store-uux_gggggg-lc.status.json", "logs/store-uux_uuxgggg-lc.status.json",
    "logs/guard-store-gg-lc.log",
    "logs/time-gg_gggggg-lc.status.json", "logs/time-uux_gggggg-lc.status.json",
    "logs/time-uux_gggggg-lc.killed-1600.status.json", "logs/time-uux_gggggg-lc.killed-1600.log",
    "logs/time-uux_uuxgggg-lc.status.json",
    "logs/time-gg_gggggg-full.status.json", "logs/time-gg_gggggg-full.log",
    "logs/time-rot-gg_gggggg-full.status.json",
    "logs/phys-gg_gggggg-full.status.json", "logs/phys-gg_gggggg-full.log",
    "logs/phys-gg_gggggg-full.killed-1606.status.json", "logs/phys-gg_gggggg-full.killed-1606.log",
    "logs/catani-gg_gggggg-lc.status.json", "logs/guard-catani-gg-lc.log",
    "logs/catani-uux_uuxgggg-lc.status.json",
    "logs/catani-uux_gggggg-lc.killed-2245.status.json", "logs/catani-uux_gggggg-lc.status.json",
    "logs/dd-gg_gggggg-lc.skip", "logs/dd-uux_uuxgggg-lc.status.json", "logs/dd-uux_gggggg-lc.status.json",
    "logs/ward-gg_gggggg-lc.status.json", "logs/ward-uux_uuxgggg-lc.status.json",
    "logs/ward-uux_gggggg-lc.killed-1602.status.json",
    "logs/store-uux_uuxgggg-full.killed-1602.status.json",
    # dry runs (Generator.plan), pre-run estimates, smoke check of the Catani route
    "dryrun/gg_gggggg-lc.json", "dryrun/gg_gggggg-full.json", "dryrun/gg_gggggg_top-full.json",
    "dryrun/uux_gggggg-lc.json", "dryrun/uux_gggggg-full.json",
    "dryrun/uux_uuxgggg-lc.json", "dryrun/uux_uuxgggg-full.json",
    "estimates.json", "smoke/catani-gg_ggg-2.json",
    # stored artifacts (generation.json only), stop flag, mf-8g-0 report, harness rows
    "artifacts/gg_gggggg-lc/generation.json", "artifacts/gg_gggggg-full/generation.json",
    "artifacts/uux_gggggg-lc/generation.json", "artifacts/uux_uuxgggg-lc/generation.json",
    "STOP-8LEG", "8g0-report.md", "processes.json",
)

LOCATION = {
    "runs": "workspace/tmp/bench-2to6/runs/",
    "logs": "workspace/tmp/bench-2to6/logs/",
    "dryrun": "workspace/tmp/bench-2to6/dryrun/",
    "smoke": "workspace/tmp/bench-2to6/smoke/",
    "artifacts": "workspace/artifacts/2to6/",
    "estimates.json": "workspace/tmp/bench-2to6/estimates.json",
    "STOP-8LEG": "workspace/tmp/STOP-8LEG",
    "8g0-report.md": "workspace/reports/engine-v2/m-final/8g0-report.md",
    "processes.json": "tools/loop_benchmark/processes.json (work/v2-bench-2to6)",
}


def key_of(path: str) -> str:
    parts = os.path.normpath(path).split(os.sep)
    base = parts[-1]
    if base in ("STOP-8LEG", "8g0-report.md", "processes.json", "estimates.json"):
        return base
    if base == "generation.json":
        return f"artifacts/{parts[-2]}/generation.json"
    return f"{parts[-2]}/{base}"


def where(key: str) -> str:
    head, _, tail = key.partition("/")
    if not tail:
        return LOCATION[key]
    return LOCATION[head] + tail


def sig(x: float, n: int = 3) -> float:
    return float(f"{x:.{n}g}")


def gib(gb: float) -> float:
    return round(gb * GIB_PER_GB, 2)


class Records:
    def __init__(self, paths: list[str]) -> None:
        self.text: dict[str, str] = {}
        for path in paths:
            key = key_of(path)
            if key not in REQUIRED:
                raise SystemExit(f"unexpected input {path} (key {key})")
            if key in self.text:
                raise SystemExit(f"duplicate input {key}")
            with open(path, encoding="utf-8") as handle:
                self.text[key] = handle.read()
        missing = [k for k in REQUIRED if k not in self.text]
        if missing:
            raise SystemExit(f"missing inputs: {missing}")
        self.used: set[str] = set()

    def json(self, key: str):
        self.used.add(key)
        return json.loads(self.text[key])

    def raw(self, key: str) -> str:
        self.used.add(key)
        return self.text[key]


def status(rec: Records, key: str) -> dict:
    s = rec.json(key)
    out = {k: s[k] for k in ("start", "end", "elapsed_s", "peak_rss_gb", "rc", "reason", "core") if k in s}
    if "peak_rss_gb" in s:
        out["peak_rss_gib"] = gib(s["peak_rss_gb"])
    for k in ("attempt", "previous_attempts", "running", "waiting_for_memory", "gate_wait_s"):
        if k in s:
            out[k] = s[k]
    out["source"] = where(key)
    return out


def loaded_lines(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = re.match(r"\S+ loaded (\{.*\})$", line)
        if m:
            d = json.loads(m.group(1))
            out.append({"s": d["seconds"], "peak_gib": d["peak_gib"]})
    return out


def warm_up_line(text: str):
    for line in text.splitlines():
        m = re.match(r"\S+ warm-up B=(\d+) \((\d+) points\): ([0-9.]+) s$", line)
        if m:
            return {"B": int(m.group(1)), "points": int(m.group(2)), "s": float(m.group(3))}
    return None


def generation(rec: Records, row: str) -> dict:
    g = rec.json(f"artifacts/{row}/generation.json")
    st = status(rec, f"logs/store-{row}.status.json")
    stages = {}
    for name in ("model", "generate", "export"):
        s = g["generation"][name]
        stages[name] = {"s": s["seconds"], "peak_gib": s["peak_gib"]}
        if "plan_mb" in s:
            stages[name]["plan_mb"] = s["plan_mb"]
    stages["store"] = {"s": g["store"]["seconds"], "peak_gib": g["store"]["peak_gib"]}
    peak = max(v["peak_gib"] for v in stages.values())
    out = {
        "stages": stages,
        "stage_sum_s": round(sum(v["s"] for v in stages.values()), 1),
        "step_wall_s": st["elapsed_s"],
        "step_wall_h": round(st["elapsed_s"] / 3600, 2),
        "peak_gib": peak,
        "peak_note": "max of the per-stage VmHWM peaks (harness resets the high-water mark per stage)",
        "step": st,
        "revision": g["revision"],
        "dirty": g["dirty"],
        "lanes": g["lanes"],
        "structure": g["structure"],
    }
    return out, g


def artifact(g: dict, row: str) -> dict:
    return {
        "path": f"workspace/artifacts/2to6/{row}/loop-runtime.pacbin",
        "bytes": g["store"]["bytes"],
        "gb": round(g["store"]["bytes"] / 1e9, 3),
        "plan_sha256": g["plan_sha256"],
        "point_inputs": g["point_inputs"],
        "source": f"workspace/artifacts/2to6/{row}/generation.json (store.bytes; artifact not opened)",
    }


def batches(t: dict) -> dict:
    (b, v), = t["batches"].items()
    return int(b), v


def physical_check(t: dict) -> dict:
    points = []
    for p in t["physical"]:
        virt = p["components"]["virtual"]
        points.append({
            "index": p["index"],
            "born": p["born"],
            "finite": p["finite"],
            "single_pole_over_born_abs": virt[1] / abs(p["born"]),
            "double_pole_over_born": p["double_pole_over_born"],
            "universal_double_pole": p["universal_double_pole"],
            "double_pole_deviation": p["double_pole_deviation"],
            "seconds_per_point_all_poles": p["seconds"],
        })
    worst = max(q["double_pole_deviation"] for q in points)
    return {
        "status": "done",
        "what": "double pole / Born of the renormalised virtual against the universal value (every pole, binary64)",
        "points": points,
        "max_deviation": worst,
        "verdict": "pass" if worst < LAX else "FAIL",
    }


def stability_check(rec: Records, row: str) -> dict:
    s = rec.json(f"runs/stability-time-{row}.json")
    pts = []
    for r in s["rows"]:
        pts.append({
            "index": r["index"],
            "arithmetic": r["arithmetic"],
            "finite": r["finite"],
            "estimate_finite_relative": r["estimate_finite"],
            "rotation-0_budget_relative": r["checks"]["rotation-0"],
            "reduction-rescaled_budget_relative": r["checks"]["reduction-rescaled"],
            "seconds_per_point_with_checks": r["seconds_with_checks"],
            "above_1e-5": r["estimate_finite"] > LAX,
        })
    return {
        "status": "done",
        "what": ("recommended stability estimate (loops.v2.stability.RECOMMENDED_CHECKS: one generic exact rotation "
                 "default_rotation(0) + the rescaled reduction check), binary64, stream points 0-2; estimate = "
                 "2 x (rotation budget + reduction budget) + 16 u S, relative to the finite part; the check budgets "
                 "are each check's own relative budget (sum over reduction lanes of |Omega - Omega'| plus local parts), "
                 "not a spread of two totals"),
        "points": pts,
        "max_estimate": max(p["estimate_finite_relative"] for p in pts),
        "points_above_1e-5": [p["index"] for p in pts if p["above_1e-5"]],
        "source": where(f"runs/stability-time-{row}.json"),
    }


def not_obtained(why: str, **extra) -> dict:
    out = {"status": "not obtained", "why": why}
    out.update(extra)
    return out


def evaluation_normal(rec: Records, row: str, t: dict) -> dict:
    b, v = batches(t)
    st = status(rec, f"logs/time-{row}.status.json")
    (wb, ws), = t["warm_up_seconds"].items()
    wp = t["warm_up_points"][wb]
    return {
        "mode": "normal timing: warm-up, then paired timed blocks of B stream points (finite part, poles off, checks off)",
        "B": b,
        "lanes": t["lanes"],
        "threads": 1,
        "threads_source": "record protocol: " + t["protocol"],
        "host_core": t["host_cpus"],
        "warm_up": {"points": wp, "B": int(wb), "s": ws, "s_per_point": round(ws / wp, 1),
                    "note": "includes lazy compilation"},
        "timed": {"blocks": v["blocks"], "points_per_block": v["points_per_block"],
                  "points": v["blocks"] * v["points_per_block"],
                  "samples_s_per_point": v["samples_seconds_per_point"]},
        "s_per_point": v["median_seconds_per_point"],
        "stages_s_per_point": v["stages_per_point"],
        "peak_gib_harness": t["max_rss_gib"],
        "peak_note": "harness ru_maxrss of the timing process; step = watchdog process-group VmRSS samples (GB = 1e9 B)",
        "step": st,
        "revision": t["revision"],
        "colour_contraction": t.get("colour_contraction_policy"),
    }


def load(t: dict) -> dict:
    l = t["stored"]["load"]
    return {"s": l["seconds"], "peak_gib": l["peak_gib"]}


def row_gg_lc(rec: Records, common: dict) -> dict:
    row = "gg_gggggg-lc"
    gen, g = generation(rec, row)
    guard = rec.raw("logs/guard-store-gg-lc.log")
    m = re.search(r"job ended; true peak (\d+)GiB", guard)
    stop = re.search(r"^(\S+) STOP watchdog", guard, re.M)
    end = re.search(r"^(\S+) job ended", guard, re.M)
    gen["step_peak_caveat"] = (
        f"the watchdog's step peak ({gen['step']['peak_rss_gb']} GB) under-reports: the watchdog was SIGSTOPped from "
        f"{stop.group(1)} to {end.group(1)} (logs/guard-store-gg-lc.log); the guard's 5-min samples peak at "
        f"{m.group(1)} GiB and the harness store-stage VmHWM is {g['store']['peak_gib']} GiB")
    gen["guard_true_peak_gib"] = int(m.group(1))
    t = rec.json("runs/time-gg_gggggg-lc.json")
    ev = evaluation_normal(rec, row, t)
    cat = rec.json("runs/catani-gg_gggggg-lc.json")
    cst = status(rec, "logs/catani-gg_gggggg-lc.status.json")
    gc = rec.raw("logs/guard-catani-gg-lc.log")
    kill = re.search(r"^(\S+) KILL pgid \d+ \(host MemAvailable (\d+) GB < (\d+) GB; peak (\d+)GiB\)", gc, re.M)
    dd_skip = rec.raw("logs/dd-gg_gggggg-lc.skip").strip()
    ward = rec.json("logs/ward-gg_gggggg-lc.status.json")
    est = rec.json("estimates.json")
    return {
        "key": row,
        "evaluation_B_reason": est["rows"][row]["B_reason"],
        "generation": gen,
        "artifact": artifact(g, row),
        "load": load(t),
        "evaluation": ev,
        "checks": {
            "double_pole": physical_check(t),
            "catani_single_pole": not_obtained(
                f"tree-engine Catani route (8-leg LC tree + 28 dipole correlators) produced 0 points: still in the "
                f"tree generation after {cst['elapsed_s']} s, killed at {kill.group(1)} by the host-memory floor "
                f"(MemAvailable {kill.group(2)} GB < {kill.group(3)} GB; job peak {kill.group(4)} GiB) per "
                f"logs/guard-catani-gg-lc.log; the status label '{cst['reason']}' (rc {cst['rc']}) is wrong (its "
                f"stopped watchdog held the old 7200 s bound); a re-run alone was planned, then the USER stop",
                points=len(cat["points"]), step=cst),
            "ward": not_obtained("deferred (logs/ward-gg_gggggg-lc.status.json): " + ward["note"].split("; re-run")[0]
                                 + "; it never ran before the USER stop"),
            "double_double": not_obtained("skipped by the chain rule (logs/dd-gg_gggggg-lc.skip): " + dd_skip),
            "stability": stability_check(rec, row),
        },
    }


def row_gg_full(rec: Records, common: dict) -> dict:
    row = "gg_gggggg-full"
    gen, g = generation(rec, row)
    t = rec.json("runs/time-rot-gg_gggggg-full.json")
    rt = t["rotation_timing"]
    st = status(rec, "logs/time-rot-gg_gggggg-full.status.json")
    first_log = rec.raw("logs/time-gg_gggggg-full.log")
    first = status(rec, "logs/time-gg_gggggg-full.status.json")
    first_load = loaded_lines(first_log)
    first_wu = warm_up_line(first_log)
    phys_attempts = []
    k = rec.json("logs/phys-gg_gggggg-full.killed-1606.status.json")
    kl = loaded_lines(rec.raw("logs/phys-gg_gggggg-full.killed-1606.log"))
    phys_attempts.append({"start": k["start"], "elapsed_s": k["elapsed_s"], "peak_rss_gb": k["peak_rss_gb"],
                          "reason": k["reason"], "load": kl[0] if kl else None})
    ps = rec.json("logs/phys-gg_gggggg-full.status.json")
    pl = loaded_lines(rec.raw("logs/phys-gg_gggggg-full.log"))
    for i, a in enumerate(ps["previous_attempts"]):
        phys_attempts.append({"start": a["start"], "elapsed_s": a["elapsed_s"], "peak_rss_gb": a["peak_rss_gb"],
                              "reason": a["reason"], "load": pl[i] if i < len(pl) else None})
    loads = [load(t)] + first_load + [a["load"] for a in phys_attempts if a["load"]]
    rows = []
    for r in rt["rows"]:
        rows.append({"stream_index": r["index"], "finite": r["finite"],
                     "relative_spread": r["relative_spread"], "born_relative_spread": r["born_relative_spread"],
                     "above_1e-5": r["relative_spread"] > LAX})
    unstable = [r["stream_index"] for r in rows if r["relative_spread"] >= 1.0]
    unstable_spreads = ", ".join("%.3g" % r["relative_spread"] for r in rows if r["stream_index"] in unstable)
    stable = [r["stream_index"] for r in rows if not r["above_1e-5"]]
    lc = rec.json("runs/time-gg_gggggg-lc.json")
    (_, lv), = lc["batches"].items()
    ev = {
        "mode": ("rotation block (USER 2026-11-01 ~09:50): warm-up 16 stream points, then ONE timed batch of 16 = "
                 f"{rt['samples']} stream points x {rt['rotations']} copies (identity + default_rotation(0..2)), "
                 "finite part, poles off, checks off; not the paired 2-block protocol"),
        "B": int(next(iter(t["batches"]))),
        "lanes": rt["lanes"],
        "threads": rt["threads"],
        "host_core": t["host_cpus"],
        "warm_up": {"points": t["warm_up_points"]["16"], "B": 16, "s": t["warm_up_seconds"]["16"],
                    "s_per_point": round(t["warm_up_seconds"]["16"] / t["warm_up_points"]["16"], 1),
                    "note": "includes lazy compilation"},
        "timed": {"blocks": 1, "points_per_block": rt["points"], "points": rt["points"],
                  "stream_indices": rt["stream_indices"], "copies": rt["copies"], "wall_s": rt["wall"],
                  "samples_s_per_point": [rt["seconds_per_point"]]},
        "s_per_point": rt["seconds_per_point"],
        "stages_s_per_point": rt["stages_per_point"],
        "colour_contraction": rt["colour_contraction"],
        "peak_gib_harness": rt["peak_gib"],
        "peak_note": ("harness VmHWM of the timed block (reset before it); the step peak (watchdog, GB = 1e9 B) "
                      "includes the warm-up"),
        "step": st,
        "revision": t["revision"],
        "fc_over_lc_s_per_point": round(rt["seconds_per_point"] / lv["median_seconds_per_point"], 2),
        "earlier_normal_timing_stopped_after_warm_up": {
            "load": first_load[0] if first_load else None,
            "warm_up": first_wu,
            "step": first,
            "prose_only": {"why_stopped": "stopped by the coordinator at 09:56 to switch to the rotation layout "
                                          "(STATE.md COORDINATOR 2026-11-01 ~10:00); the status only says rc -15"},
        },
    }
    return {
        "key": row,
        "generation": gen,
        "artifact": artifact(g, row),
        "load": {**load(t), "all_loads_of_this_artifact": loads,
                 "range_s": [min(x["s"] for x in loads), max(x["s"] for x in loads)]},
        "evaluation": ev,
        "checks": {
            "rotation_spread": {
                "status": "done",
                "what": ("finite-part relative spread max_r |f_r - f_0| / |f_0| over the 4 copies of each sample "
                         "(binary64, from the timed block itself)"),
                "points": rows,
                "max_relative_spread": rt["max_relative_spread"],
                "unstable_points": unstable,
                "verdict": (f"stream point(s) {unstable} binary64-unstable (spread {unstable_spreads}: no correct "
                            f"digit): a rescue case; points {stable} below 1e-5"),
            },
            "double_pole": not_obtained(
                "the FC physical-points job (phys-gg_gggggg-full: load, 1-point warm-up, points 0-2 with every "
                f"pole) was killed by the host-memory floor on all {len(phys_attempts)} attempts before its warm-up "
                f"finished (no warm-up line in its logs), then held at its {ps['gate_need_gb']:.0f} GB start gate "
                "until the USER stop",
                attempts=phys_attempts),
            "catani_single_pole": not_obtained("catani-gg_gggggg-full needs the FC physical rows: never started"),
            "ward": not_obtained("no FC Ward run was started",
                                 prose_only={"plan": "planned only if >= 500 GiB were free (STATE.md 2026-11-01 16:15)"}),
            "double_double": not_obtained("no double-double run at 2->6 g g > 6g (the chain skips DD when "
                                          "100 x s/pt > 1 h)"),
        },
    }


def row_uux6g(rec: Records, common: dict) -> dict:
    row = "uux_gggggg-lc"
    gen, g = generation(rec, row)
    t = rec.json("runs/time-uux_gggggg-lc.json")
    ev = evaluation_normal(rec, row, t)
    k = rec.json("logs/time-uux_gggggg-lc.killed-1600.status.json")
    kl = rec.raw("logs/time-uux_gggggg-lc.killed-1600.log")
    ev["earlier_attempt_killed"] = {"start": k["start"], "elapsed_s": k["elapsed_s"], "peak_rss_gb": k["peak_rss_gb"],
                                    "reason": k["reason"], "load": loaded_lines(kl)[0], "warm_up": warm_up_line(kl)}
    cat = rec.json("runs/catani-uux_gggggg-lc.json")
    cat_k = rec.json("runs/catani-uux_gggggg-lc.killed-2245.json")
    ck = rec.json("logs/catani-uux_gggggg-lc.killed-2245.status.json")
    attempts = ck["previous_attempts"] + [{"attempt": ck["attempt"], "start": ck["start"], "elapsed_s": ck["elapsed_s"],
                                           "peak_rss_gb": ck["peak_rss_gb"], "reason": ck["reason"]}]
    rerun = rec.json("logs/catani-uux_gggggg-lc.status.json")
    dd = rec.json("logs/dd-uux_gggggg-lc.status.json")
    wk = rec.json("logs/ward-uux_gggggg-lc.killed-1602.status.json")
    return {
        "key": row,
        "generation": gen,
        "artifact": artifact(g, row),
        "load": load(t),
        "evaluation": ev,
        "checks": {
            "double_pole": physical_check(t),
            "catani_single_pole": not_obtained(
                f"tree-engine Catani route: {len(attempts)} chain attempts all killed by the 120 GB host-memory floor "
                f"while in the tree generation (longest {max(a['elapsed_s'] for a in attempts)} s), "
                f"{len(cat_k['points'])} points; the own-track re-run started {rerun['start']} (record: "
                f"{len(cat['points'])} points; its status still says running, last update at {rerun['elapsed_s']} s) "
                "was ended by the USER stop",
                attempts=attempts),
            "ward": not_obtained(f"ward-uux_gggggg-lc killed by the host-memory floor {wk['elapsed_s']} s after its "
                                 f"start ({wk['start']}); not re-run before the USER stop"),
            "double_double": not_obtained(
                "dd-uux_gggggg-lc (point 0) killed by the host-memory floor on attempt 1 "
                f"({dd['previous_attempts'][0]['elapsed_s']} s), then "
                + ("waiting at its start gate" if dd.get("waiting_for_memory") else "re-running")
                + " when the USER stop ended it"),
            "stability": stability_check(rec, row),
        },
    }


def row_uux4g(rec: Records, common: dict) -> dict:
    row = "uux_uuxgggg-lc"
    gen, g = generation(rec, row)
    t = rec.json("runs/time-uux_uuxgggg-lc.json")
    ev = evaluation_normal(rec, row, t)
    cat = rec.json("runs/catani-uux_uuxgggg-lc.json")
    cst = status(rec, "logs/catani-uux_uuxgggg-lc.status.json")
    smoke = rec.json("smoke/catani-gg_ggg-2.json")
    pts = []
    for p in cat["points"]:
        pts.append({k: p[k] for k in ("index", "mu_r", "tree_born", "loop_born", "born_ratio",
                                      "catani_single_over_born", "loop_single_over_born_abs", "single_deviation",
                                      "catani_double_over_born", "loop_double_over_born", "double_deviation",
                                      "passed_1e-5", "seconds")})
    dd = rec.json("runs/dd-uux_uuxgggg-lc.json")
    d64 = next(r for r in dd["rows"] if r["arithmetic"] == "double")
    ddd = next(r for r in dd["rows"] if r["arithmetic"] == "double-double")
    err = abs(d64["finite"] - ddd["finite"]) / abs(ddd["finite"])
    dst = status(rec, "logs/dd-uux_uuxgggg-lc.status.json")
    w = rec.json("runs/ward-uux_uuxgggg-lc.json")
    wst = status(rec, "logs/ward-uux_uuxgggg-lc.status.json")
    wrows = []
    for p in w["points"]:
        for carrier, c in p["carriers"].items():
            for r in c["rows"]:
                wrows.append({"point": p["index"], "carrier": carrier, "leg": r["leg"], "factor": r["factor"],
                              "born": r["born"], "virtual_finite_single_double": r["parts"]["virtual"],
                              "in_scope": r["in_scope"], "passed": r["passed"]})
    c0 = w["points"][0]["carriers"]["double"]
    uq = rec.json("logs/store-uux_uuxgggg-full.killed-1602.status.json")
    return {
        "key": row,
        "generation": gen,
        "artifact": artifact(g, row),
        "load": load(t),
        "evaluation": ev,
        "checks": {
            "double_pole": physical_check(t),
            "catani_single_pole": {
                "status": "done (LC); decisive FC check pending",
                "what": ("tree engine's colour-correlated Born + massless Catani (mqcd 'tree' route, n_f = 5) at "
                         f"tree accuracy '{cat['tree_accuracy']}' against the loop's poles; single pole compared in "
                         "magnitude, both normalised to their own Born; single_deviation = loop/Catani - 1; "
                         "born_ratio = loop LC Born / tree LC Born"),
                "points": pts,
                "max_single_deviation": max(p["single_deviation"] for p in pts),
                "max_double_deviation": max(p["double_deviation"] for p in pts),
                "tree_generation_s": cat["tree_generation_s"],
                "tree_peak_gib": cat["tree_peak_gib"],
                "step": cst,
                "verdict": (f"double pole passes (<= {max(p['double_deviation'] for p in pts):.2g}); single pole off "
                            f"by {' / '.join('%.1f' % (100 * p['single_deviation']) for p in pts)} % (not passed at "
                            "1e-5) while the two engines' LC Borns differ too (born_ratio "
                            f"{' / '.join('%.3f' % p['born_ratio'] for p in pts)}): the tree engine's LC (colour-flow "
                            "truncation and its LC colour correlations) is not the loop engine's formal-N_c LC for quark "
                            "lines, so this LC comparison is not like for like; to be decided by the FC check (exact "
                            "colour on both sides), which is pending"),
                "route_validation": {
                    "process": smoke["process"], "tree_accuracy": smoke["tree_accuracy"],
                    "max_single_deviation": max(p["single_deviation"] for p in smoke["points"]),
                    "max_double_deviation": max(p["double_deviation"] for p in smoke["points"]),
                    "source": where("smoke/catani-gg_ggg-2.json"),
                    "note": "the route agrees at full colour on g g > g g g; it was never run at LC on a gluon row",
                },
                "fc_check_pending": {
                    "why": (f"store-uux_uuxgggg-full (the FC phase's first step) was killed by the host-memory floor "
                            f"{uq['elapsed_s']} s after its start ({uq['start']}); the FC phase never re-ran before the "
                            "USER stop"),
                },
                "prose_only": {"explanation_source": "STATE.md COORDINATOR 2026-11-01 ~13:50 (LC-definition reading; "
                                                     "not investigated further by ruling)"},
            },
            "ward": {
                "status": "done",
                "what": ("tools/loop_v2_ward.py on a regenerated LC process: point 0, leg 8 polarisation replaced by "
                         "c p_j / p_j^0 with factors 1 and i, binary64, every pole; ratios to the scale of each "
                         "Laurent coefficient"),
                "passed": w["passed"],
                "max_born_ratio": c0["max_born"],
                "max_virtual_ratio_finite_single_double": c0["max_virtual"],
                "rows": wrows,
                "criterion": w["criterion"],
                "regeneration": w["stages"],
                "max_rss_gib": w["max_rss_gib"],
                "step": wst,
                "verdict": "pass" if w["passed"] else "FAIL",
            },
            "double_double": {
                "status": "done",
                "what": "stream point 0 in binary64 and double-double, recommended checks on both",
                "binary64": {"born": d64["born"], "finite": d64["finite"],
                             "estimate_finite_relative": d64["estimate_finite"],
                             "seconds_per_point_with_checks": d64["seconds_with_checks"]},
                "double_double": {"born": ddd["born"], "finite": ddd["finite"],
                                  "estimate_finite_relative": ddd["estimate_finite"],
                                  "seconds_per_point_with_checks": ddd["seconds_with_checks"]},
                "binary64_true_error_finite_relative": sig(err, 4),
                "binary64_born_difference_relative": sig(abs(d64["born"] - ddd["born"]) / abs(ddd["born"]), 3),
                "estimate_over_true_error": round(d64["estimate_finite"] / err, 1),
                "step": dst,
                "verdict": (f"{'pass' if err < LAX else 'FAIL'}: binary64 agrees with double-double to {err:.2g} "
                            f"relative; the binary64 estimate ({d64['estimate_finite']:.2g}) "
                            f"{'covers' if d64['estimate_finite'] >= err else 'UNDERSTATES'} it"),
            },
            "stability": stability_check(rec, row),
        },
    }


def parse_8g0(text: str) -> dict:
    sections = re.split(r"^## ", text, flags=re.M)
    sec5 = next(s for s in sections if s.startswith("5."))
    sec4 = next(s for s in sections if s.startswith("4."))

    def table(sec: str) -> list[list[str]]:
        rows = []
        for line in sec.splitlines():
            if line.startswith("|") and not re.match(r"^\|[-| ]+\|$", line):
                rows.append([c.strip().replace("**", "") for c in line.strip().strip("|").split("|")])
        return rows

    t5 = table(sec5)
    head5 = t5[0]
    est = [dict(zip(["stage"] + [h.lower().replace(" ", "_") for h in head5[1:]], r)) for r in t5[1:]]
    t4 = table(sec4)
    head4 = t4[0][1:]
    keep = {}
    for r in t4[1:]:
        if r[0].startswith("tree + CT state") or r[0].startswith("JSON GB"):
            keep[r[0]] = dict(zip(head4, r[1:]))
    return {
        "estimates_after_mf_8g_1_2": {
            "label": "ESTIMATES [inf] +-50 %, not measured (8g0-report §5 'now -> after MF-8G-1/-2')",
            "heading": sec5.splitlines()[0],
            "rows": est,
        },
        "stored_program_scans": {
            "label": "mf-8g-0 scans of the stored plans/tree programs (8g0-report §4; not re-derived here)",
            "rows": keep,
        },
    }


def dry_runs(rec: Records) -> dict:
    out = {}
    for name in ("gg_gggggg-lc", "gg_gggggg-full", "gg_gggggg_top-full", "uux_gggggg-lc", "uux_gggggg-full",
                 "uux_uuxgggg-lc", "uux_uuxgggg-full"):
        d = rec.json(f"dryrun/{name}.json")
        out[name] = {"expression": d["expression"], "accuracy": d["accuracy"], "particle_veto": d["particle_veto"],
                     "passed": d["passed"], "blockers": d["blockers"], "plan_s": d["plan_s"], "peak_gib": d["peak_gib"]}
    return {"what": "Generator.plan dry runs (no structure counts); all configurations, including top-included "
                    "g g > 6g FC (Q-A)", "rows": out}


def row_caveats(rows: list[dict]) -> dict:
    lc, fc, u6, u4 = rows
    st = lc["checks"]["stability"]
    above = st["points_above_1e-5"]
    est = ", ".join("%.1e" % p["estimate_finite_relative"] for p in st["points"] if p["index"] in above)
    rs = fc["checks"]["rotation_spread"]
    spreads = ", ".join("%.3g" % p["relative_spread"] for p in rs["points"] if p["stream_index"] in rs["unstable_points"])
    cat = u4["checks"]["catani_single_pole"]["points"]
    dev = [100 * p["single_deviation"] for p in cat]
    return {
        "gg_gggggg-lc": [
            lc["generation"]["step_peak_caveat"],
            "Catani step status says 'time bound' but the cause was the host-memory floor (guard log)",
            f"points {above} have binary64 stability estimates above 1e-5 ({est}): rescue candidates; no "
            "double-double cross-check at 2->6 g g > 6g",
        ],
        "gg_gggggg-full": [
            "the rotated FC run ran partly in zram swap, so its 'native trees' time "
            f"({fc['evaluation']['stages_s_per_point']['native trees']:.1f} s/pt vs "
            f"{lc['evaluation']['stages_s_per_point']['native trees']:.1f} s/pt at LC) is likely inflated "
            "[inf, 8g0-report §0 item 4]",
            f"s/pt is ONE block of {fc['evaluation']['timed']['points']} = stream points "
            f"{fc['evaluation']['timed']['stream_indices']} x {len(fc['evaluation']['timed']['copies'])} copies "
            "(identity + 3 exact rotations) with FFT colour contraction, not the paired 2-block protocol of the LC rows",
            f"stream point(s) {rs['unstable_points']} binary64-unstable (rotation spread {spreads}): a rescue case "
            "(the Python-API rescue stack, mf-rescue 2234ee33, is the remedy; not applied in this run)",
            f"the block VmHWM ({fc['evaluation']['peak_gib_harness']:.1f} GiB) understates the footprint under swap; "
            f"the step peak {fc['evaluation']['step']['peak_rss_gb']:.1f} GB came from the warm-up",
            "no FC poles, Catani, Ward or double-double: the physical-points job never got past its warm-up",
        ],
        "uux_gggggg-lc": [
            "Catani, Ward and double-double not obtained (host-memory kills, then the USER stop)",
            "first timing attempt killed by the host-memory floor; the recorded timing is attempt 1 of the "
            "relaunched chain",
        ],
        "uux_uuxgggg-lc": [
            f"LC Catani single pole {min(dev):.1f}-{max(dev):.1f} % off: differing LC definitions (tree vs loop "
            "engine) for quark lines; the decisive FC check is pending",
        ],
    }


META = {
    "gg_gggggg-lc": ("gg_gggggg", "lc", "g g > 6g", "LC"),
    "gg_gggggg-full": ("gg_gggggg", "full", "g g > 6g", "FC"),
    "uux_gggggg-lc": ("uux_gggggg", "lc", "u u~ > 6g", "LC"),
    "uux_uuxgggg-lc": ("uux_uuxgggg", "lc", "u u~ > u u~ 4g", "LC"),
}


def head(rec: Records, row: str, body: dict, procs: dict) -> dict:
    name, acc, label, acc_label = META[row]
    dr = rec.json(f"dryrun/{row}.json")
    p = procs[name]
    out = {
        "key": row,
        "process": dr["expression"],
        "label": f"{label} ({acc_label}, N_f = 5, no top)",
        "accuracy": acc,
        "particle_veto": p["particle_veto"],
        "particle_veto_note": f"PDG {p['particle_veto']} (processes.json); dry run veto '{dr['particle_veto']}': "
                              "top-free massless five-flavour QCD (USER Q-A 2026-10-31)",
        "born_orders": p["born_orders"],
        "correction": p["correction"],
        "revisions": {"generation": body["generation"]["revision"], "timing": body["evaluation"]["revision"]},
        "lanes": body["generation"]["lanes"],
        "structure": body["generation"]["structure"],
    }
    out.update({k: v for k, v in body.items() if k != "key"})
    ev = body["evaluation"]
    gen = body["generation"]
    out["table1"] = {
        "label": out["label"],
        "generation_h": gen["step_wall_h"],
        "generation_peak_gib": gen["peak_gib"],
        "artifact_gb": body["artifact"]["gb"],
        "load_s": body["load"]["s"],
        "load_peak_gib": body["load"]["peak_gib"],
        "s_per_point": ev["s_per_point"],
        "B": ev["B"],
        "eval_peak_gib": ev["peak_gib_harness"],
        "eval_step_peak_gib": ev["step"]["peak_rss_gib"],
        "fastest_olp_s_per_point": None,
        "gate": "none: no external reference at 2->6 (no provider entry); speed reported without a gate, cell uncoloured",
        "preliminary": True,
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("records", nargs="+")
    args = ap.parse_args()
    rec = Records(args.records)
    procs = {r["name"]: r for r in rec.json("processes.json")["processes"]}
    common: dict = {}
    builders = {"gg_gggggg-lc": row_gg_lc, "gg_gggggg-full": row_gg_full,
                "uux_gggggg-lc": row_uux6g, "uux_uuxgggg-lc": row_uux4g}
    rows = [head(rec, r, builders[r](rec, common), procs) for r in ROWS]
    # one native build and one protocol across every timing record
    natives = set()
    protocols = set()
    revisions = set()
    for key in ("runs/time-gg_gggggg-lc.json", "runs/time-rot-gg_gggggg-full.json", "runs/time-uux_gggggg-lc.json",
                "runs/time-uux_uuxgggg-lc.json") + tuple(f"artifacts/{r}/generation.json" for r in ROWS):
        d = rec.json(key)
        natives.add(json.dumps(d["native"], sort_keys=True))
        revisions.add(d["revision"])
        if "protocol" in d:
            protocols.add(d["protocol"])
    if len(natives) != 1 or len(protocols) != 1:
        raise SystemExit(f"records disagree: natives {natives} protocols {protocols}")
    native = json.loads(natives.pop())
    stop = rec.raw("STOP-8LEG").strip()
    g8 = parse_8g0(rec.raw("8g0-report.md"))
    gg_fc = rows[1]
    out = {
        "schema": "pyamplicol-2to6-harvest/1",
        "status": ("PRELIMINARY: harvested from existing records only (no new 8-leg run: STOP-8LEG); pre-optimisation "
                   "engine; checks incomplete; runs stopped by the USER"),
        "engine": {
            "branch": "work/v2-bench-2to6",
            "base": "15d4ef5a (milestone M-SM report head; engine pin 71e2041e)",
            "harness_commits": {
                "d5ed94c2": "processes.json rows gg_gggggg / uux_gggggg / uux_uuxgggg (particle_veto [6]) + frozen "
                            "streams; at 2->6 the stream is RAMBO from its first point (no campaign point passes the "
                            "1/1000 cut)",
                "8a062a52": "--rotation-samples/--rotations rotation timing block and --colour-contraction",
            },
            "engine_source_change_vs_base": "none (15d4ef5a..8a062a52 touches tools/loop_benchmark and its unit test only)",
            "revisions_in_records": sorted(revisions),
            "native": native,
            "native_digest_short": native["digest"][:8],
            "protocol": protocols.pop(),
        },
        "stop": {"text": stop, "source": where("STOP-8LEG")},
        "units": {"s": "seconds wall", "gib": "2^30 bytes (harness VmHWM / ru_maxrss)",
                  "gb": "1e9 bytes (watchdog process-group VmRSS samples)", "s_per_point": "seconds per phase-space point, one thread"},
        "lax_precision_threshold": LAX,
        "rows": rows,
        "dry_runs": dry_runs(rec),
        **g8,
        "global_caveats": [
            "PRE-OPTIMISATION engine (15d4ef5a, native 71e2041e): the M-FINAL optimisation rounds (mf-8g-1, mf-8g-1b, "
            "mf-8g-2) target exactly these generation, load and evaluation peaks; the numbers are a baseline, not the "
            "M-FINAL result",
            "runs stopped by the USER on 2026-11-01 ~23:00 UTC for optimisation rounds (" + where("STOP-8LEG") + "); "
            "checks are incomplete (see each row's 'not obtained' entries)",
            "one pinned thread on a shared, loaded host; several steps were killed by host-memory floors set below "
            "other projects' usage (a 'host memory' end is not a defect); timings indicative",
            "no external reference exists at 2->6 (no provider entry): acceptance is internal (double pole, Catani, "
            "Ward, double-double, rotations); speed is reported without a gate",
            "stability estimates and check budgets are relative to the finite part (loops.v2.stability)",
            "the stored artifacts are kept in workspace/artifacts/2to6/<row>/ (loop-runtime.pacbin + generation.json)",
        ],
        "row_caveats": row_caveats(rows),
        "prose_only": {
            "gg_gggggg-full_swap": "VmSwap ~143 GB at the end of the rotated run, host zram swap ~246 GB used, "
                                   "process system time 2674 s of 19100 s CPU (STATE.md waiter 2, 2026-11-01 15:25)",
            "host_memory_other_projects": "other projects held ~600-950 GB of host memory during the runs "
                                          "(STATE.md 16:03-22:12 lines; slice-status DECISIONS ~23:20)",
            "stop_ruling": "USER 2026-11-01 ~23:00: 'stop your 8-point runs now and do a couple round of optimizations "
                           "first' (STATE.md COORDINATOR ~23:05; slice-status DECISIONS ~23:15)",
        },
        "sources": sorted(where(k) for k in rec.used),
    }
    if sorted(rec.used) != sorted(REQUIRED):
        unused = sorted(set(REQUIRED) - rec.used)
        raise SystemExit(f"inputs not used: {unused}")
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(out, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
