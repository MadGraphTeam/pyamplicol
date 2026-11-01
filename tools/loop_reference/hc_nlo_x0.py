#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""MadLoop references of the HC_NLO_X0 genericity rows (M-FINAL MF-GM-HC).

The card ``hc_nlo_x0.json`` lists the rows (process, restriction, veto, the
MadLoop process and export), each row's parameter points and the scales. For
every row this builds ``madloop_total_driver.f90`` against the row's compiled
MadLoop 3.7.0 standalone export (``madloop_export.py --recompile``; the
export is never modified), writes each point's explicit parameter card into
its own run directory (by LHA block and code, every external parameter of
the restriction plus the zero widths) and takes the Born and the Laurent
coefficients at every phase-space point and scale. Every row's export has one
squared split order, so the all-orders answer is that order's. One fixture
per row is written to ``--output-dir`` (``<id lower case>.json``).

Run with the Python that runs MG5_aMC (``-I`` is fine: paths are arguments).
"""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402
import madloop_export  # noqa: E402
import references  # noqa: E402

LHA_VALUE_CHARACTERS = references.LHA_VALUE_CHARACTERS


def row_parameters(card: dict, row: dict, point: dict) -> dict[str, str]:
    """Every external parameter of a row point: the restriction's base card,
    the point's values and the fixed (zero) widths."""

    return {**card["restrictions"][row["restriction"]], **point, **card["fixed_parameters"]}


def build_driver(export: Path, work: Path) -> Path:
    process_dir = references.madloop_process_dir(export)
    prefix = references.madloop_prefix(process_dir)
    global_flag = madloop_export.make_opts_variables(export).get("GLOBAL_FLAG", "-O")
    work.mkdir(parents=True, exist_ok=True)
    driver = work / "madloop_total_driver.f90"
    driver.write_text((HERE / "madloop_total_driver.f90").read_text().replace("ML5_0_", prefix))
    fixes, _ = references.madloop_model_fix(export, work, global_flag)
    born_fixes, _ = references.madloop_born_fix(process_dir, work, global_flag)
    binary = work / "madloop-total"
    subprocess.run(
        ["gfortran", "-O2", "-ffree-line-length-none", "-I", str(process_dir), str(driver),
         *map(str, [*fixes, *born_fixes]), str(export / "lib/libMadLoop.a"), "-L" + str(export / "lib"),
         "-ldhelas", "-lmodel", *map(str, build.madloop_libraries(export)), "-lstdc++", "-o", str(binary)],
        check=True, cwd=work,
    )
    return binary


def write_param_card(export: Path, run_dir: Path, mg5: Path, lha: dict, values: dict[str, str]) -> str:
    """Copy the export's cards and resources into ``run_dir`` and set every
    value by its LHA block and code (exact decimal text, refused where
    MadLoop's 20-character reader would not reproduce the double)."""

    if str(mg5) not in sys.path:
        sys.path.insert(0, str(mg5))
    from models.check_param_card import ParamCard

    shutil.copytree(export / "Cards", run_dir / "Cards", dirs_exist_ok=True)
    shutil.copytree(export / "SubProcesses/MadLoop5_resources", run_dir / "SubProcesses/MadLoop5_resources",
                    dirs_exist_ok=True, symlinks=False)
    path = run_dir / "Cards/param_card.dat"
    card = ParamCard(str(path))
    for name, text in values.items():
        block, code = lha[name]
        exact = float(Decimal(text))
        written = text.strip() if len(text.strip()) <= LHA_VALUE_CHARACTERS else repr(exact)
        if len(written) > LHA_VALUE_CHARACTERS or float(written) != exact:
            raise RuntimeError(f"cannot write {name}={text} exactly into a MadLoop param_card")
        try:
            param = card[block.lower()].get((code,))
        except KeyError:
            param = None
        if param is None:
            if exact != 0:
                raise RuntimeError(f"MadLoop card has no {block} {code} ({name} = {text})")
            continue  # removed by the restriction, i.e. zero
        param.value, param.format = written, "str"
    card.write(str(path))
    reread = ParamCard(str(path))
    for name, text in values.items():
        block, code = lha[name]
        try:
            param = reread[block.lower()].get((code,))
        except KeyError:
            continue
        if float(param.value) != float(Decimal(text)):
            raise RuntimeError(f"MadLoop card does not reproduce {name}={text}")
    return path.read_text()


def run_row(card: dict, row: dict, exports: Path, mg5: Path, work: Path) -> dict:
    export = exports / row["madloop"]["export"]
    binary = build_driver(export, work / row["id"] / "build")
    scales = card["mu_r"]
    cards = []
    for index, point in enumerate(row["cards"]):
        values = row_parameters(card, row, point)
        run_dir = work / row["id"] / f"card{index}"
        write_param_card(export, run_dir, mg5, card["lha"], values)
        lines = [values["aS"], str(len(row["points"]) * len(scales))]
        for momenta in row["points"]:
            for mu in scales:
                lines.append(" ".join([mu, *(x for leg in momenta for x in leg)]))
        result = subprocess.run([str(binary)], input="\n".join(lines) + "\n", capture_output=True, text=True,
                                cwd=run_dir, check=True)
        (run_dir / "driver.out").write_text(result.stdout + result.stderr)
        totals = [line.split()[1:] for line in result.stdout.splitlines() if line.startswith("TOTAL ")]
        if len(totals) != len(row["points"]) * len(scales):
            raise RuntimeError(f"{row['id']} card {index}: MadLoop printed {len(totals)} rows")
        entries = []
        for k, fields in enumerate(totals):
            born, finite, single, double, accuracy = map(float, fields[2:7])
            entries.append({"point": k // len(scales), "mu_r": scales[k % len(scales)], "status": int(fields[1]),
                            "born": born, "finite": finite, "single_pole": single, "double_pole": double,
                            "accuracy": accuracy})
        cards.append({"parameters": values, "values": entries})
    return {
        "row": row["id"],
        "process": row["process"],
        "particle_veto": row["particle_veto"],
        "restriction": row["restriction"],
        "provider": {"name": "MadLoop", "version": "3.7.0", "process": row["madloop"]["process"],
                     "precision": "binary64 with MadLoop's own stability rescue (MLStabThres)"},
        "mu_r": scales,
        "points": row["points"],
        "cards": cards,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--card", type=Path, default=HERE / "hc_nlo_x0.json")
    parser.add_argument("--exports", type=Path, required=True, help="directory of the compiled exports")
    parser.add_argument("--mg5", type=Path, required=True, help="MG5_aMC 3.7.0 source tree")
    parser.add_argument("--work", type=Path, required=True, help="new or empty work directory")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--rows", nargs="*", help="row ids (default: every row)")
    args = parser.parse_args()
    card = json.loads(args.card.read_text())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for row in card["rows"]:
        if args.rows and row["id"] not in args.rows:
            continue
        fixture = run_row(card, row, args.exports.resolve(), args.mg5.resolve(), args.work.resolve())
        target = args.output_dir / f"{row['id'].lower()}.json"
        target.write_text(json.dumps(fixture, indent=1) + "\n")
        print("HC_REFERENCE", row["id"], target, flush=True)


if __name__ == "__main__":
    main()
