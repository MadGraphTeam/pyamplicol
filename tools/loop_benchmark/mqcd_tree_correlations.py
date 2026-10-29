# SPDX-License-Identifier: 0BSD
"""Write the tree engine's colour-correlated Born of M-QCD rows (rule 4's
"tree" prediction, m-qcd/PLAN.md §1.4 rule 4).

Usage: python -m tools.loop_benchmark.mqcd_tree_correlations ROW...
           --ufo LOOP_SM_UFO --work DIR

For each row: the tree engine's artifact of its process with every dipole
<T_j.T_k> of the coloured legs (``mqcd.tree_runtime``: full colour, the
row's restriction and Born orders; an artifact already in DIR/tree-<row> is
reused), evaluated at every manifest point of the row in ``mqcd.TREE_DIGITS``
digits, written to tests/fixtures/loop/mqcd/references/tree-correlations-
<row>.json. The campaign's rule 4 reads it on rows whose native-input
executor forms no Catani prediction (WP3.1 I5c; manifest
``tree_correlations``) instead of generating the tree artifact in the
nightly tier (g g > g g g g: 968 s and 11 GB), and checks the fixture's
momenta against the reference point and its Born against ours (1e-24).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from tools.loop_benchmark import mqcd

OUTPUT = mqcd.FIXTURES / "mqcd" / "references"


def fixture_path(name: str) -> Path:
    return OUTPUT / f"tree-correlations-{name}.json"


def write(name: str, ufo: Path, work: Path) -> Path:
    row = mqcd.rows()[name]
    reference = mqcd.load_reference(row)
    start = time.perf_counter()
    reused = (work / f"tree-{name}" / "artifact.json").is_file()
    runtime = mqcd.tree_runtime(row, ufo, work / f"tree-{name}")
    generated = None if reused else round(time.perf_counter() - start, 1)
    points = sorted({i for indices in row.points.values() for i in indices})
    entries = []
    for index in points:
        start = time.perf_counter()
        entry = mqcd.tree_point(runtime, row, reference.points[index])
        entries.append({"index": index, **entry})
        print(f"{name} point {index}: {time.perf_counter() - start:.1f} s", flush=True)
    data = {
        "row": name,
        "process": row.process,
        "restriction": row.restriction,
        "born_orders": dict(row.born_orders),
        "reference": row.reference["path"],
        "colour_accuracy": "full",
        "digits": mqcd.TREE_DIGITS,
        "source": "pyamplicol tree engine: Generator.generate(..., correlators="
        "CorrelatorConfig(color_correlations=every dipole T_j.T_k)), "
        "Runtime.evaluate_correlated_many (tools/loop_benchmark/"
        "mqcd_tree_correlations.py)",
        # None: an artifact generated earlier was reused.
        "generation_seconds": generated,
        "points": entries,
    }
    path = fixture_path(name)
    path.write_text(json.dumps(data, indent=1) + "\n")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("rows", nargs="+")
    parser.add_argument("--ufo", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    args = parser.parse_args(argv)
    for name in args.rows:
        print(write(name, args.ufo, args.work), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
