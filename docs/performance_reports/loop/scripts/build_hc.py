# SPDX-License-Identifier: 0BSD
# build_hc.py (campaign m1101-mfb, as hc_rows.py in workspace/reports/engine-v2/m-final/records/m1101-mfb-new): write hc.json, the HC_NLO_X0 rows of MF-GM-HC at the pinned commit.
# Usage (worktree root as cwd, env.sh sourced, SYMBOLICA_LICENSE in the environment, PYTHONPATH as for pytest):
#   python docs/performance_reports/loop/scripts/build_hc.py BASETEMP JUNIT OUT
# BASETEMP: the --basetemp of the whole-file job of tests/unit/test_loop_v2_hc.py (its artifacts are reloaded, no
# regeneration); JUNIT: that job's --junitxml. Per row the evaluation mirrors the test's _check_row (same points,
# parameters, scales, deviation measure _relative with the floor |Born| alpha_s/(2 pi)) and records the maxima.
# HC05 (g g > x0 g g, heft, veto t) is generated once to record its typed refusal key.
import json
import math
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from tests.unit import test_loop_v2_hc as hc  # noqa: E402

from pyamplicol import Runtime  # noqa: E402
from pyamplicol.api.virtual_results import VirtualStabilityChecks  # noqa: E402

basetemp, junit, out = (Path(a) for a in sys.argv[1:4])
card = hc._card()
outcomes = {}
for case in ET.parse(junit).getroot().iter("testcase"):
    kids = [c.tag for c in case]
    outcomes[case.get("name")] = (
        "failed" if "failure" in kids or "error" in kids else "skipped" if "skipped" in kids else "passed"
    )

rows = []
for row_id in ("HC01", "HC02", "HC03", "HC04", "HC06"):
    row = hc._row(card, row_id)
    (artifact,) = [p for p in sorted(basetemp.glob(f"test_hc_rows_equal_madloop_*/{row_id}")) if not p.parent.is_symlink()][:1]
    fixture = json.loads((hc.FIXTURES / f"{row_id.lower()}.json").read_text())
    runtime = Runtime.load(artifact, process="p")
    worst = {"born": 0.0, "finite": 0.0, "single_pole": 0.0, "double_pole": 0.0}
    catani = {"single_pole": 0.0, "double_pole": 0.0}
    rotation, dd_vs_ref, dd_vs_b64, values = 0.0, 0.0, 0.0, 0
    for entry in fixture["cards"]:
        runtime.set_model_parameters(
            {k: v for k, v in entry["parameters"].items() if k not in card["fixed_parameters"]}
        )
        alpha_s = float(entry["parameters"]["aS"])
        points = [[[float(x) for x in leg] for leg in fixture["points"][v["point"]]] for v in entry["values"]]
        scales = [float(v["mu_r"]) for v in entry["values"]]
        result = runtime.evaluate(points, mu_r2=[m * m for m in scales], stability_checks=VirtualStabilityChecks(1))
        extended = (
            runtime.evaluate(points, mu_r2=[m * m for m in scales], arithmetic="double-double")
            if row_id == "HC02"
            else None
        )
        for k, value in enumerate(entry["values"]):
            values += 1
            born = float(result.born_values[k][0])
            laurent = [float(x) for x in result.values[k][0]]
            floor = abs(value["born"]) * alpha_s / (2 * math.pi)
            worst["born"] = max(worst["born"], hc._relative(born, value["born"], 0.0))
            for ours, key in zip(laurent, ("finite", "single_pole", "double_pole")):
                worst[key] = max(worst[key], hc._relative(ours, value[key], floor))
            poles = hc._catani(row["process"], points[k], born, scales[k], alpha_s)
            for ours, theirs, key in zip(laurent[1:], poles, ("single_pole", "double_pole")):
                if theirs is not None:
                    catani[key] = max(catani[key], hc._relative(ours, theirs, floor))
                elif key == "single_pole":
                    catani[key] = None
            rotation = max(rotation, result.stability[k].relative)
            if extended is not None:
                for i, key in enumerate(("finite", "single_pole", "double_pole")):
                    ours = float(extended.values[k][0][i])
                    dd_vs_ref = max(dd_vs_ref, hc._relative(ours, value[key], floor))
                    dd_vs_b64 = max(dd_vs_b64, hc._relative(ours, laurent[i], floor))
    test = outcomes.get(f"test_hc_rows_equal_madloop[{row_id}]")
    within = max(worst.values()) <= hc.TOLERANCE
    rows.append(
        {
            "id": row_id,
            "process": row["process"],
            "particle_veto": row["particle_veto"],
            "madloop_process": row["madloop"]["process"],
            "model": "HC_NLO_X0_UFO (v1.3, tools/loop_reference/hc_nlo_x0.json)",
            "restriction": row["restriction"],
            "parameter_cards": [entry["parameters"].get("cosa") for entry in fixture["cards"]],
            "points": len(fixture["points"]),
            "values": values,
            "mu_r": card["mu_r"],
            "reference": f"tests/fixtures/loop/required/hc/{row_id.lower()}.json (MadLoop 3.7.0)",
            "max_relative_deviation": worst,
            "acceptance": hc.TOLERANCE,
            "catani_max_relative": catani,
            "catani_tolerance": hc.POLE_TOLERANCE,
            "rotation_estimate_max": rotation,
            "rotation_bound": hc.ROTATION_BOUND,
            "double_double": {"vs_madloop": dd_vs_ref, "vs_binary64": dd_vs_b64} if row_id == "HC02" else None,
            "test": test,
            "status": "pass" if within and test == "passed" else "fail",
        }
    )
    print(row_id, rows[-1]["status"], {k: f"{v:.1e}" for k, v in worst.items()}, flush=True)

# HC05: generation refused, typed
hc05 = {"id": "HC05", "process": "g g > x0 g g", "particle_veto": ["t"], "restriction": "heft"}
import os  # noqa: E402

source = Path(
    os.environ.get("PYAMPLICOL_HC_UFO_REFERENCE")
    or Path(os.environ["PYAMPLICOL_LOOP_WORKSPACE"]) / "reference/sources/hc-nlo-x0/extract/HC_NLO_X0_UFO"
)
refusal = {"key": None, "message": None}
start = time.time()
probe = out.parent / "hc05-probe"
probe.mkdir(exist_ok=True)
try:
    hc._generate(source, card, hc05, probe)
    refusal["key"] = "NOT REFUSED"
except Exception as error:  # the typed refusal carries its key
    refusal["key"] = getattr(error, "key", None) or str(error).split(":", 1)[0]
    refusal["type"] = type(error).__name__
    refusal["message"] = str(error)[:600]
refusal["seconds"] = round(time.time() - start, 1)
rows.append(
    {
        "id": "HC05",
        "process": "g g > x0 g g",
        "particle_veto": ["t"],
        "model": "HC_NLO_X0_UFO (v1.3)",
        "restriction": "heft",
        "status": "blocked",
        "reason": "five-point f*f*f*f R2 contact (G G G G X0) needs the multi-trace colour state (DESIGN §6.1); "
        "recorded limitation (optional row)",
        "refusal": refusal,
    }
)
print("HC05", refusal["key"], flush=True)

required = [r for r in rows if r["id"] in ("HC01", "HC02", "HC03", "HC04", "HC06")]
out.write_text(
    json.dumps(
        {
            "source": "tests/unit/test_loop_v2_hc.py whole-file job (every tier, JUnit) + hc_rows.py re-evaluation of its artifacts",
            "commit": "617b59cdb106e398b4a84b403e60920fbcd3a501",
            "native": "loop-native-v2-slice-b36af289 (digest 58b40383)",
            "date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
            "precision": "binary64 (HC02 also double-double); deviation |ours - MadLoop| / max(|ours|, |MadLoop|, |Born| alpha_s/(2 pi))",
            "junit": {k: v for k, v in outcomes.items()},
            "counts": {
                "pass": sum(r["status"] == "pass" for r in rows),
                "fail": sum(r["status"] == "fail" for r in rows),
                "blocked": sum(r["status"] == "blocked" for r in rows),
            },
            "all_required_pass": all(r["status"] == "pass" for r in required),
            "rows": rows,
        },
        indent=1,
    )
    + "\n"
)
