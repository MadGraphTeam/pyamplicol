#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""MG5_aMC standalone tree references of 1 -> n decays (M-FINAL MF-DEC-1).

For each row (``ROWS``) the decay's tree matrix element is generated with
MG5_aMC's ``output standalone`` on the row scheme's MG5 model, its param_card
set to the scheme's exact parameter values (every listed parameter; a
parameter the restriction removed must be zero), and evaluated at three
exact rest-frame points (``decay_points.py``, printed to 32 digits) by the
custom Fortran driver of ``tools/developer/madgraph_correctness.py``
(``SMATRIX``: summed over final helicities and colours, averaged over the
decaying particle's, divided by the identical-particle factor). The result is
committed as ``tests/fixtures/loop/required/dec/tree_<row>.json``.

Run with the Python that runs MG5_aMC, ``make`` and ``gfortran`` on PATH
(``workspace/reference/env.sh``):

    decay_tree_mg5.py --mg5 <MG5 tree> --work <scratch dir> [rows ...]
"""

import argparse
import json
import os
import re
import sys
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parent.parent
FIXTURES = REPOSITORY / "tests/fixtures/loop/required/dec"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPOSITORY))
import decay_points  # noqa: E402
import required_spec  # noqa: E402

# row -> MG5 process, PDG codes (decaying particle first), parameter scheme
# (required_processes.json) and pyAmpliCol's restriction of the shipped
# loop_sm (the scheme's MG5 model is loop_sm at that restriction).
ROWS = {
    "t_bwp": {"process": "t > b w+", "pdgs": [6, 5, 24], "scheme": "qcd"},
    "z_emep": {"process": "z > e- e+", "pdgs": [23, 11, -11], "scheme": "qcd"},
    "h_bbx_4fs": {"process": "h > b b~", "pdgs": [25, 5, -5], "scheme": "qcd-4fs"},
    "t_bwpg": {"process": "t > b w+ g", "pdgs": [6, 5, 24, 21], "scheme": "qcd"},
    "wp_udxg": {"process": "w+ > u d~ g", "pdgs": [24, 2, -1, 21], "scheme": "qcd"},
    "z_uuxg": {"process": "z > u u~ g", "pdgs": [23, 2, -2, 21], "scheme": "qcd"},
    # identical final particles (the symmetry factor 2! 2!), the QCD orders
    # only (MG5's default here also takes the QED^3 amplitudes)
    "z_uuxuux": {"process": "z > u u~ u u~", "pdgs": [23, 2, -2, 2, -2], "scheme": "qcd",
                 "orders": {"QCD": 2, "QED": 1}},
}
RESTRICTIONS = {"qcd": "no_b_mass", "qcd-4fs": "default"}
POINTS = 3


def row_spec(row):
    """The row as a toolkit process (scheme merged; ``required_spec.masses``)."""
    data = required_spec.load()
    entry = ROWS[row]
    scheme = json.loads(json.dumps(data["schemes"][entry["scheme"]]))
    return {"name": row, "pdgs": entry["pdgs"], "scheme": entry["scheme"], "scheme_data": scheme,
            "initial": 1}


def row_points(row):
    """The row's exact rest-frame points and their 32-digit decimal text."""
    spec = row_spec(row)
    masses = required_spec.masses(spec)
    values = {**spec["scheme_data"]["parameters"], **spec["scheme_data"]["fixed_parameters"]}
    resonances = [values[name] for name in ("MZ", "MW", "MH", "MT") if name in values and Fraction(values[name])]
    exact = decay_points.generate(masses, POINTS, resonances=resonances, pdgs=spec["pdgs"])
    return masses, exact, [decay_points.decimal_point(point) for point in exact]


def set_card(card, values):
    """Write each scheme value (exact decimal text) on the param_card line
    whose comment names it (any case); a value missing from the card must be
    zero (the restriction removed it). Returns the card text."""
    lines = card.read_text().splitlines(keepends=True)
    wanted = {name.lower(): (name, text) for name, text in values.items()}
    seen = set()
    out = []
    for line in lines:
        body, marker, comment = line.partition("#")
        name = comment.strip().split(" ")[0].lower() if marker and comment.strip() else ""
        # Dependent entries read "<particle> : <expression>"; leave them.
        if name in wanted and not re.match(r"^\S+ : ", comment.strip()):
            key, text = wanted[name]
            match = re.fullmatch(r"(\s*(?:DECAY\s+)?\S+\s+)(\S+)(\s*)", body, re.IGNORECASE)
            if match is None:
                raise SystemExit(f"cannot parse the card line {line!r}")
            if len(text) > 20 or float(text) != float(Decimal(text)):
                raise SystemExit(f"cannot write {key}={text} exactly")
            out.append(match.group(1) + text + match.group(3) + marker + comment)
            seen.add(name)
            continue
        out.append(line)
    for name, (key, text) in wanted.items():
        if name not in seen and Decimal(text) != 0:
            raise SystemExit(f"the card has no parameter {key} (value {text})")
    card.write_text("".join(out))
    return card.read_text()


def run_row(row, mg5, work):
    from tools.developer.madgraph_correctness import StandaloneMadGraphRunner

    spec = row_spec(row)
    entry = ROWS[row]
    model = spec["scheme_data"]["madloop_model"].replace("{mg5}", str(mg5))
    runner = StandaloneMadGraphRunner()
    process = runner.generate(installation=mg5, artifact=work / row, process=entry["process"], model_import=model,
                              coupling_orders=entry.get("orders"))
    values = {**spec["scheme_data"]["parameters"], **spec["scheme_data"]["fixed_parameters"]}
    card = set_card(process.standalone / "Cards/param_card.dat", values)
    masses, exact, points = row_points(row)
    results = []
    for point in points:
        results.append(runner.evaluate(process, [[float(x) for x in leg] for leg in point]).value)
    mg5_version = re.search(r"version = (\S+)", (mg5 / "VERSION").read_text()).group(1)
    fixture = {
        "row": row,
        "process": entry["process"],
        "pdgs": entry["pdgs"],
        **({"coupling_orders": entry["orders"]} if "orders" in entry else {}),
        "scheme": entry["scheme"],
        "pyamplicol_model": {"source": "loop_sm", "restriction": RESTRICTIONS[entry["scheme"]]},
        "mg5_model": Path(model).name,
        "source": f"MG5_aMC {mg5_version} output standalone, SMATRIX in binary64 at the binary64 "
                  "rounding of the points (tools/loop_reference/decay_tree_mg5.py)",
        "normalization": "summed over final helicities and colours, averaged over the decaying "
                         "particle's helicities and colours, divided by the final identical-particle factor",
        "parameters": values,
        "param_card": card,
        "masses": [decay_points.exact_text(m) for m in masses],
        "points": points,
        "exact_points": [[[decay_points.exact_text(x) for x in leg] for leg in point] for point in exact],
        "values": results,
    }
    FIXTURES.mkdir(parents=True, exist_ok=True)
    target = FIXTURES / f"tree_{row}.json"
    target.write_text(json.dumps(fixture, indent=1) + "\n")
    print(target, results, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mg5", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True, help="scratch directory of the MG5 outputs")
    parser.add_argument("rows", nargs="*", default=sorted(ROWS))
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    for row in args.rows:
        run_row(row, Path(os.path.abspath(args.mg5)), args.work.resolve())


if __name__ == "__main__":
    main()
