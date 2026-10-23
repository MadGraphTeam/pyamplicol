# SPDX-License-Identifier: 0BSD
"""Write data/measured.json for the live loop report.

Usage: python scripts/collect_milestone.py <workspace> [output]

<workspace> is the development workspace that holds the run records
(tmp/generation-scale/runs, tmp/ct-recursion/s4). Every value is read from
those records (JSON and /usr/bin/time -v logs); nothing is copied from text.
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
