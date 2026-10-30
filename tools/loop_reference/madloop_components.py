#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Bare, R2 and UV-counterterm components of a MadLoop reference per loop sector.

For every loop sector of a committed reference fixture that has a Born partner,
``madloop_ct_selection.py`` evaluates the Born x CT interference of the export's
counterterm amplitudes on the run's own cards and points, split by the UFO
couplings their calls stand for (the export's ``ct_couplings.json``,
``madloop_ct_couplings.py``; MG5 calls merged couplings by one name): ``r2``
(R2 couplings), ``uv`` (UV couplings), ``rest`` (any other CT amplitude,
normally none) and ``ct`` (all). The bare loop is the
reference's sector value minus ``ct`` (m-sm/PLAN.md §1.4 rule 5: the engine's
bare, R2 and UV-CT components per sector equal MadLoop's). The CT amplitudes are
tree-like and are evaluated in double precision (CTModeRun 1); correctness
references only.

    python tools/loop_reference/madloop_components.py --work $RUNS/msm/uux_emep_ew \\
        --fixture tests/fixtures/loop/required/msm/uux_emep_ew.json \\
        --output tests/fixtures/loop/required/msm/components/uux_emep_ew.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
GROUPS = {"r2": "R2", "uv": "UV"}
DEFINITION = (
    "per loop squared split order and point: the Born x CT interference of the "
    "export's CT amplitudes whose calls pass an R2 coupling (r2), a UV coupling (uv), "
    "by the UFO couplings the call names stand for (ct_couplings.json), "
    "neither (rest) and all (ct), evaluated by madloop_ct_selection.py in double "
    "precision (CTModeRun 1); bare = the reference's sector value (quadruple "
    "precision) - ct"
)
LAURENT = ("finite", "single_pole", "double_pole")


def components(
    work: Path, fixture: dict, scratch: Path, export: Path, subprocess_dir: str | None
) -> dict:
    alpha_s = str(Decimal(fixture["parameters"]["aS"]))
    sectors = {}
    for sector in fixture["rows"][0]["sectors"]["loop"]:
        partner = sector["born_sector"]
        if partner is None:
            continue
        key = f"QCD^2={sector['QCD']},QED^2={sector['QED']}"
        output = scratch / key.replace("^", "").replace(",", "_").replace("=", "")
        orders = [partner["QCD"], partner["QED"], sector["QCD"], sector["QED"]]
        subprocess.run(
            [
                sys.executable,
                str(HERE / "madloop_ct_selection.py"),
                "--work",
                str(work),
                "--export",
                str(export),
                *(("--subprocess", subprocess_dir) if subprocess_dir else ()),
                "--ct-couplings",
                str(export.parent / f"{export.name}.ct_couplings.json"),
                "--orders",
                *map(str, orders),
                "--alpha-s",
                alpha_s,
                *(
                    x
                    for name, pattern in GROUPS.items()
                    for x in ("--group", f"{name}={pattern}")
                ),
                "--output",
                str(output),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        report = json.loads((output / "components.json").read_text())
        variants = report["variants"]
        rows = []
        for index, row in enumerate(fixture["rows"]):
            total = next(
                s
                for s in row["sectors"]["loop"]
                if (s["QCD"], s["QED"]) == (sector["QCD"], sector["QED"])
            )
            entry = {
                name: {k: variants[name][index][k] for k in LAURENT}
                for name in variants
            }
            entry["bare"] = {k: total[k] - variants["ct"][index][k] for k in LAURENT}
            entry["total"] = {k: total[k] for k in LAURENT}
            rows.append(entry)
        sectors[key] = {
            "born_sector": partner,
            "ct_amplitude_counts": report["ct_amplitude_counts"],
            "rows": rows,
        }
    return sectors


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--work",
        type=Path,
        required=True,
        help="the run's work directory (madloop-export, "
        "madloop-run/Cards, points.json)",
    )
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--export", type=Path, help="default: WORK/madloop-export")
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text())
    export = args.export or args.work / "madloop-export"
    subprocess_dir = fixture.get("mqcd_run", {}).get("subprocess")
    points = json.loads((args.work / "points.json").read_text())
    if points["points"] != fixture["points"]:
        raise SystemExit(f"{args.work}: points differ from {args.fixture}")
    with tempfile.TemporaryDirectory(dir=args.work) as scratch:
        sectors = components(args.work, fixture, Path(scratch), export, subprocess_dir)
    report = {
        "reference": args.fixture.name,
        "process": fixture["process"],
        "points": len(fixture["points"]),
        "groups": GROUPS,
        "definition": DEFINITION,
        "sectors": sectors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
