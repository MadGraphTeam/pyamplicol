# SPDX-License-Identifier: 0BSD
# build_corr.py (campaign m1101-mfb, as corr_rows.py in workspace/reports/engine-v2/m-final/records/m1101-mfb-new): write corr.json, the MF-CORR Recola correlation rows at the pinned commit.
# Usage (worktree root as cwd, env.sh sourced, SYMBOLICA_LICENSE in the environment, PYTHONPATH as for pytest):
#   python docs/performance_reports/loop/scripts/build_corr.py BASETEMP JUNIT OUT
# BASETEMP: the --basetemp of the whole-file job of tests/unit/test_loop_v2_corr_recola.py (its artifacts
# corr-<process>0/{virtual,tree} are reloaded, no regeneration); JUNIT: that job's --junitxml. The requests, conversions
# and deviation measures are the test's (_requests, _parameters; Born relative to |Recola LO|; Laurent coefficients
# relative to the row's largest |Recola coefficient|); this script records the maxima per process and kind.
import json
import math
import sys
import time
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from tests.unit import test_loop_v2_corr_recola as corr  # noqa: E402

from pyamplicol import Runtime  # noqa: E402

basetemp, junit, out = (Path(a) for a in sys.argv[1:4])
outcomes = {}
for case in ET.parse(junit).getroot().iter("testcase"):
    kids = [c.tag for c in case]
    outcomes[case.get("name")] = (
        "failed" if "failure" in kids or "error" in kids else "skipped" if "skipped" in kids else "passed"
    )


def reference(name):
    return json.loads((ROOT / "tests/fixtures/loop" / f"{name}.json").read_text())


KINDS = {"born": "plain Born", "cc": "colour", "sc": "spin", "scc": "spin-colour"}
rows = []
for name in corr.PROCESSES:
    data = corr._fixture(reference, name)
    root = basetemp / f"corr-{name}0"
    parameters, fixed = corr._parameters(name)
    virtual = Runtime.load(root / "virtual", model_parameters=parameters)
    tree = Runtime.load(root / "tree")
    mutable = {p.name for p in tree.physics.model_parameters if p.mutable}
    tree.set_model_parameters({k: float(v) for k, v in {**parameters, **fixed}.items() if k in mutable})
    requests, answers = corr._requests(data)
    scales = [str(Decimal(mu) ** 2) for mu in data["mu_r"]]
    loop = virtual.evaluate_correlated_many(data["points"], requests, mu_r2=scales)
    momenta = [tuple(tuple(Decimal(x) for x in leg) for leg in point) for point in data["points"]]
    born_tree = tree.evaluate_correlated_many(momenta, requests, precision=20)
    per_kind = {}
    for label, row, factor in answers:
        point, kind = row["point"], row["kind"]
        entry = per_kind.setdefault(
            kind,
            {"entries": 0, "tree_born": 0.0, "virtual_born": 0.0, "finite": 0.0, "single_pole": 0.0, "double_pole": 0.0},
        )
        entry["entries"] += 1
        lo = factor * row["lo"]
        value = born_tree[label][point]
        ours_tree = complex(float(value.real), float(value.imag))
        entry["tree_born"] = max(entry["tree_born"], abs(ours_tree - lo) / abs(lo))
        result = loop[label]
        born = complex(result.born_values[point][0])
        entry["virtual_born"] = max(entry["virtual_born"], abs(born - lo) / abs(lo))
        finite, ir1, ir2 = row["nlo"]
        expected = [factor * (finite + math.pi**2 / 6 * ir2), factor * ir1, factor * ir2]
        scale = max(map(abs, expected))
        for key, ours, theirs in zip(
            ("finite", "single_pole", "double_pole"), (complex(v) for v in result.values[point][0]), expected
        ):
            entry[key] = max(entry[key], abs(ours - theirs) / scale)
    tests = {
        test: outcomes.get(f"{test}[{name}]")
        for test in (
            "test_recola_references_conserve_colour",
            "test_correlated_virtual_matches_recola",
            "test_correlated_tree_born_matches_recola",
        )
    }
    for kind, entry in per_kind.items():
        born_ok = max(entry["tree_born"], entry["virtual_born"]) <= corr.BORN_RELATIVE
        loop_ok = max(entry["finite"], entry["single_pole"], entry["double_pole"]) <= corr.VIRTUAL_RELATIVE
        rows.append(
            {
                "process": name,
                "recola_process": data["recola_process"],
                "kind": KINDS[kind],
                "entries": entry["entries"],
                "points": len(data["points"]),
                "max_relative_deviation": {k: entry[k] for k in ("tree_born", "virtual_born", "finite", "single_pole", "double_pole")},
                "acceptance": {"born": corr.BORN_RELATIVE, "laurent_vs_row_scale": corr.VIRTUAL_RELATIVE},
                "tests": tests,
                "status": "pass" if born_ok and loop_ok and all(v == "passed" for v in tests.values()) else "fail",
            }
        )
        print(name, kind, rows[-1]["status"], {k: f"{v:.1e}" for k, v in rows[-1]["max_relative_deviation"].items()}, flush=True)

out.write_text(
    json.dumps(
        {
            "source": "tests/unit/test_loop_v2_corr_recola.py whole-file job (every tier, JUnit) + corr_rows.py re-evaluation of its artifacts",
            "reference": "tests/fixtures/loop/required/corr/<process>.json (Recola2 2.2.5, binary64)",
            "commit": "617b59cdb106e398b4a84b403e60920fbcd3a501",
            "native": "loop-native-v2-slice-b36af289 (digest 58b40383)",
            "date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
            "precision": "binary64 one-loop runtime; tree engine correlated Born at precision=20 (rounded to binary64); "
            "Laurent deviations relative to the row's largest |Recola coefficient| (the test's measure)",
            "junit": outcomes,
            "counts": {"pass": sum(r["status"] == "pass" for r in rows), "fail": sum(r["status"] == "fail" for r in rows)},
            "all_pass": all(r["status"] == "pass" for r in rows) and all(v == "passed" for v in outcomes.values()),
            "rows": rows,
        },
        indent=1,
    )
    + "\n"
)
