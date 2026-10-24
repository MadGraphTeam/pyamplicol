# SPDX-License-Identifier: 0BSD
"""Write data/measured.json for the live loop report.

Usage: python scripts/collect_milestone.py <workspace> [output]

<workspace> is the development workspace that holds the run records
(tmp/generation-scale/runs, tmp/ct-recursion/s4, the WP3.1 native validations
in tmp/generation-scale/gint, the provider reference runs in
reference/runs/required). Every value is read from those records (JSON and
/usr/bin/time -v logs); nothing is copied from text.
Each block carries its source, relative to the workspace. The hand-maintained
registry data/milestone.json is not written here.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RUNS = "tmp/generation-scale/runs"
CT = "tmp/ct-recursion/s4"
# Native validations of the WP3.1 branch (work/v2-generation-scale) on its
# merged head, recorded by DESIGN WP3.1 "eighth increment" (0ea83af2):
# tools/loop_v2_generate.py validate --inputs native, production counterterm
# route, binary64, one record per process.
GINT = "tmp/generation-scale/gint"
GINT_RECORDS = {
    "uux_emepddxg": "val1/uux_emepddxg.json",
    "uux_emepggg": "val1/uux_emepggg.json",
    "gg_ttxemepg_qcd": "val1/gg_ttxemepg_qcd.json",
    "gg_ttxgg": "val1/gg_ttxgg.json",
    "gg_gggg": "val2/gg_gggg.json",
    "gg_ggggg": "val1/gg_ggggg_njet.json",
}
# Provider reference runs of the required set (HANDOFF section 0.1): MadLoop
# export records (graph generation, source export, compilation) and the
# Recola/OpenLoops result records of the reference campaign.
REFS = "reference/runs/required"
REF_PROCESSES = (
    "uux_emepddxg",
    "uux_emepggg",
    "gg_ttxemepg_qcd",
    "gg_ttxemepg_ew",
    "uux_ggggg",
    "gg_ggggg",
)


def _load(root: Path, rel: str) -> dict:
    return json.loads((root / rel).read_text())


def _time_v(root: Path, rel: str) -> dict:
    """Wall, user and system time (s), max RSS (KiB) and CPU share (%) from a
    /usr/bin/time -v log."""
    text = (root / rel).read_text()
    wall = re.search(
        r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)", text
    ).group(1)
    parts = [float(x) for x in wall.split(":")]
    seconds = sum(v * 60**i for i, v in enumerate(reversed(parts)))
    rss = int(re.search(r"Maximum resident set size \(kbytes\): (\d+)", text).group(1))
    cpu = int(re.search(r"Percent of CPU this job got: (\d+)%", text).group(1))
    user = float(re.search(r"User time \(seconds\): (\S+)", text).group(1))
    system = float(re.search(r"System time \(seconds\): (\S+)", text).group(1))
    return {
        "wall_s": round(seconds, 2),
        "user_s": user,
        "system_s": system,
        "max_rss_kib": rss,
        "cpu_percent": cpu,
    }


def _events(record: dict) -> dict:
    return {e["stage"]: e for e in record.get("events", [])}


def _generation(root: Path, name: str) -> dict:
    rel = f"{RUNS}/{name}.json"
    rec = _load(root, rel)
    ev = _events(rec)
    out = {
        "source": f"workspace/{rel}, workspace/{RUNS}/{name}.log",
        "process": rec["process"],
        "generate_s": rec["generate_s"],
        "generate_peak_gib": ev["LoopSlice.generate"]["peak_gb"],
        "export_s": ev["export_plan"]["wall_s"],
        "plan_json_s": ev["plan_json"]["wall_s"],
        "plan_json_mb": rec["plan_json_mb"],
        "counts": rec["counts"],
    }
    out.update(_time_v(root, f"{RUNS}/{name}.log"))
    return out


def _native_validation(root: Path, key: str, rel: str) -> dict:
    """One WP3.1 native validation record: generation and export cost, and
    per reference the largest deviation of every coefficient over the points
    (the record's own metric, |a-b|/max(|a|,|b|,|Born| coupling/2pi))."""
    path = f"{GINT}/{rel}"
    rec = _load(root, path)
    worst: dict[str, dict[str, float]] = {}
    for point in rec["points"]:
        for ref, errors in point["errors"].items():
            for coefficient, value in errors.items():
                slot = worst.setdefault(ref, {})
                slot[coefficient] = max(slot.get(coefficient, 0.0), value)
    return {
        "source": f"workspace/{path}",
        "process": rec["process"],
        "counterterms": rec["counterterms"],
        "inputs": rec["inputs"],
        "generate_s": rec["generate_s"],
        "generate_peak_gib": rec["generate_peak_gb"],
        "export_s": rec["export_s"],
        "export_peak_gib": rec["export_peak_gb"],
        "plan_json_mb": rec["plan_json_mb"],
        "max_rss_gib": rec["max_rss_gb"],
        "tolerance": rec["tolerance"],
        "passed": rec["passed"],
        "points": [p["index"] for p in rec["points"]],
        "max_deviation": worst,
        "max_error_per_point": [p["max_error"] for p in rec["points"]],
        "stability_estimate_per_point": [
            p.get("stability_relative") for p in rec["points"]
        ],
        # Single-point development evaluations (one point per call, with the
        # rotation check where a stability estimate is recorded); not batched
        # timings.
        "seconds_per_point_unbatched": [p["seconds"] for p in rec["points"]],
    }


def _provider_generation(root: Path, key: str) -> dict:
    """MadLoop export and Recola generation records of one required process,
    and the OpenLoops library its reference run used."""
    base = root / REFS / key
    out: dict = {"source": f"workspace/{REFS}/{key}/"}
    ml = json.loads((base / "madloop-export.generation.json").read_text())
    stages = ("graph_generation_s", "source_export_s", "compile_s")
    madloop = {"status": ml["status"], "loops": ml.get("loops")}
    madloop.update({s: ml[s] for s in stages if s in ml})
    if ml["status"] == "compiled":
        madloop["total_s"] = sum(ml[s] for s in stages)
    out["madloop"] = madloop
    recola = base / "recola-result.json"
    if recola.exists():
        out["recola"] = {
            "status": "done",
            "generation_s": json.loads(recola.read_text())["generation_seconds"],
        }
    else:
        state = json.loads((base / "status-recola.json").read_text())
        out["recola"] = {"status": state["state"], "updated": state["updated"]}
    openloops = base / "openloops-result.json"
    out["openloops"] = (
        {"library": json.loads(openloops.read_text())["library"]["name"]}
        if openloops.exists()
        else None
    )
    return out


def collect(root: Path) -> dict:
    poles = _load(root, f"{RUNS}/poles2_gg_ggggg.json")
    ev0 = _load(root, f"{RUNS}/eval2_gg_ggggg.json")
    ev1 = _load(root, f"{RUNS}/eval2_gg_ggggg_rot.json")
    ct = _load(root, f"{CT}/gg_ggggg.json")
    uux = _load(root, f"{RUNS}/cmp_uux_ggggg.json")

    p0, p1 = ev0["points"][0], ev1["points"][0]
    rotation = {
        key: abs(a - b) / abs(a)
        for key, a, b in zip(
            ("finite", "single_pole", "double_pole"),
            p0["virtual"],
            p1["virtual"],
            strict=True,
        )
    }
    worst = {}
    for provider in ("madloop", "recola"):
        for key in ("born", "finite", "single_pole", "double_pole"):
            worst.setdefault(provider, {})[key] = max(
                p["errors"][provider][key] for p in uux["points"]
            )

    return {
        "date": "2026-10-23",
        "engine_revision": "e734b708",
        "native_build": (
            "loop-native-v2-slice-45875b87"
            " (digest 2be17627...; release, codegen-units 1, thin LTO)"
        ),
        "host": "AMD EPYC 9754 (shared, 384 logical CPUs)",
        "seven_gluon": {
            "generation_first": _generation(root, "gen_gg_ggggg_final"),
            "generation_latest": _generation(root, "gen_gg_ggggg_hash"),
            "ct_program": {
                "source": f"workspace/{CT}/gg_ggggg.json, workspace/{CT}/gg_ggggg.log",
                "total_s": ct["total_s"],
                "ct_program_s": ct["ct_program_s"],
                "plain_blocks_s": ct["plain_blocks_s"],
                "ct_currents": ct["ct_currents"],
                "ct_interactions": ct["ct_interactions"],
                "root_sites": ct["root_sites"],
                "residual": len(ct["residual"]),
                **_time_v(root, f"{CT}/gg_ggggg.log"),
            },
            "native_bare": {
                "source": (
                    f"workspace/{RUNS}/poles2_gg_ggggg.json,"
                    f" workspace/{RUNS}/poles2_gg_ggggg.log"
                ),
                "what": (
                    "bare loop + Born on the native trees, binary64,"
                    " point and one rotation (two evaluations)"
                ),
                "seconds": [p["seconds"] for p in poles["points"]],
                "double_pole_deviation": [p["deviation"] for p in poles["points"]],
                "stability_estimate": [
                    p["stability_relative"] for p in poles["points"]
                ],
                "expected_double_pole_over_born": poles[
                    "expected_double_pole_over_born"
                ],
                # Stage walls of the same job, for the CPU-time bound of the
                # evaluations (the report subtracts one core over each).
                "generate_s": poles["generate_s"],
                "export_with_trees_s": poles["export_with_trees_s"],
                # Whole job: generation, export with trees and the points.
                # The executor's thread count is not recorded (default: all
                # cores unless RAYON_NUM_THREADS is set).
                **_time_v(root, f"{RUNS}/poles2_gg_ggggg.log"),
            },
            "first_virtual": {
                "source": (
                    f"workspace/{RUNS}/eval2_gg_ggggg.json,"
                    f" workspace/{RUNS}/eval2_gg_ggggg_rot.json"
                ),
                "point": 0,
                "born": p0["born"],
                "virtual": p0["virtual"],
                "virtual_rotated": p1["virtual"],
                "rotation_relative": rotation,
                "double_pole_over_born": p0["double_pole_over_born"],
                "evaluate_s": [p0["evaluate_s"], p1["evaluate_s"]],
            },
            "uux_ggggg_vs_providers": {
                "source": f"workspace/{RUNS}/cmp_uux_ggggg.json",
                "points": len(uux["points"]),
                "max_relative_deviation": worst,
            },
        },
        "required_native": {
            "branch": "work/v2-generation-scale",
            "record": "DESIGN.md WP3.1 eighth increment (0ea83af2), "
            "'Native validations on the merged head'",
            "what": (
                "generation (LoopSlice.generate, one thread) and plan export,"
                " then binary64 virtuals with native per-point inputs and the"
                " production counterterm route at the fixture points, against"
                " the committed references (tests/fixtures/loop/required)"
            ),
            "processes": {
                key: _native_validation(root, key, rel)
                for key, rel in GINT_RECORDS.items()
            },
        },
        "provider_generation": {
            "what": (
                "MadLoop: graph generation, source export and compilation"
                " (madloop-export.generation.json); Recola: process generation"
                " (recola-result.json, or the run status if unfinished);"
                " OpenLoops: the prebuilt library of the reference run"
            ),
            "processes": {
                key: _provider_generation(root, key) for key in REF_PROCESSES
            },
        },
    }


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    out = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else Path(__file__).resolve().parents[1] / "data" / "measured.json"
    )
    out.write_text(json.dumps(collect(root), indent=1) + "\n")


if __name__ == "__main__":
    main()
