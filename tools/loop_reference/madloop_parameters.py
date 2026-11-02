#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Model parameters of a MadLoop export at a run's card, per renormalisation scale.

Links a small program against the export's ``libmodel.a`` that reads the run's
``Cards/param_card.dat`` (``setpara2``), sets each scale with
``update_as_param2`` (the loop parameters are recomputed per scale) and prints
the requested parameters of ``Source/MODEL/input.inc`` / ``coupl.inc`` in
double precision, the export's own arithmetic. Writes
``<work>/export_parameters.json``; ``mqcd_campaign.py fixture`` copies it
into the fixture of a run listing ``export_parameters`` (e.g. CM09's photon
conversion parameter ``MDL_ECOUP_DGMUA0_UV_EW_FIN_``, m-sm/PLAN.md §1.5).

    python tools/loop_reference/madloop_parameters.py --work $RUNS/msm/udx_epvea_cms \\
        --fixture tests/fixtures/loop/required/msm/udx_epvea_cms.json MDL_ECOUP_DGMUA0_UV_EW_FIN_
"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from references import madloop_model_fix  # noqa: E402

PROGRAM = """      PROGRAM EXPORT_PARAMETERS
      IMPLICIT NONE
      INCLUDE 'coupl.inc'
      INCLUDE 'input.inc'
      CHARACTER(512) CARD
      DOUBLE PRECISION SCALE, ALPHA
      INTEGER I, COUNT
      CARD = 'Cards/param_card.dat'
      CALL SETPARA2(CARD)
      READ(*,*) ALPHA, COUNT
      DO I = 1, COUNT
        READ(*,*) SCALE
        CALL UPDATE_AS_PARAM2(SCALE**2, ALPHA)
{writes}
      ENDDO
      END
"""


def evaluate(work: Path, export: Path, names: list[str], scales: list[str], alpha_s: str) -> dict:
    declared = (export / "Source/MODEL/input.inc").read_text() + (export / "Source/MODEL/coupl.inc").read_text()
    for name in names:
        if not re.search(rf"\b{re.escape(name)}\b", declared, re.I):
            raise SystemExit(f"{name} is not a parameter of {export}/Source/MODEL")
    writes = "\n".join(f"        WRITE(*,'(A,I4,2ES26.17E3)') '{name} ', I, DCMPLX({name})" for name in names)
    with tempfile.TemporaryDirectory(dir=work) as scratch:
        scratch = Path(scratch)
        (scratch / "Cards").symlink_to(work / "madloop-run/Cards")
        (scratch / "export_parameters.f").write_text(PROGRAM.format(writes=writes))
        fixes, _ = madloop_model_fix(export, scratch, "-O")
        subprocess.run(["gfortran", "-O", "-ffixed-line-length-132", "-I", str(export / "Source/MODEL"),
                        str(scratch / "export_parameters.f"), *map(str, fixes), str(export / "lib/libmodel.a"),
                        "-o", str(scratch / "export_parameters")], check=True, cwd=scratch)
        run = subprocess.run([str(scratch / "export_parameters")], input=f"{alpha_s} {len(scales)}\n"
                             + "\n".join(scales) + "\n", text=True, capture_output=True, check=True, cwd=scratch)
    values = {name: [None] * len(scales) for name in names}
    for line in run.stdout.splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[0] in values:
            values[fields[0]][int(fields[1]) - 1] = [float(fields[2]), float(fields[3])]
    if any(v is None for column in values.values() for v in column):
        raise SystemExit(f"missing values in the output:\n{run.stdout[-2000:]}")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--work", type=Path, required=True, help="the run's work directory (madloop-run/Cards)")
    parser.add_argument("--export", type=Path, help="default: WORK/madloop-export")
    parser.add_argument("--fixture", type=Path, required=True, help="the run's fixture (mu_r per row, aS)")
    parser.add_argument("names", nargs="+", help="Fortran parameter names (input.inc / coupl.inc)")
    args = parser.parse_args()
    work = args.work.resolve()
    export = (args.export or work / "madloop-export").resolve()
    fixture = json.loads(args.fixture.read_text())
    scales = [str(s) for s in fixture["mu_r"]]
    values = evaluate(work, export, args.names, scales, str(fixture["parameters"]["aS"]))
    record = {
        "source": "MadLoop export's Source/MODEL at the run's param_card (setpara2, update_as_param2 per mu_R), "
                  "double precision; [real, imaginary] per fixture row (madloop_parameters.py)",
        "mu_r": scales,
        "values": values,
    }
    (work / "export_parameters.json").write_text(json.dumps(record, indent=1) + "\n")
    print(work / "export_parameters.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
