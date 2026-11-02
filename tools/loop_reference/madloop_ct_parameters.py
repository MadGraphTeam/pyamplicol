#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""MadLoop's own counterterm-parameter values of a loop UFO at one card.

MG5_aMC imports the UFO as the MadLoop standalone exports of this toolkit do
(``madloop_export.py``: the UFO's default restriction, real-mass scheme,
Feynman gauge) and writes its Fortran model library with the writer and the
options of a MadLoop standalone output (``export_v4.UFO_model_to_mg4``, export
format ``madloop``, quadruple precision on). A process export passes its own
couplings (``wanted_couplings``) and so writes only the CT parameters they
need; here no coupling is singled out, so the library holds every CT
parameter some CT coupling uses (MG5 never writes the others). The library is
compiled with MG5_aMC's production flags (``madloop_export.production_make_opts``);
its quadruple-precision model functions get the repairs every MadLoop
reference run of this toolkit applies (``references.fix_qp_model_functions``).

A driver reads the card through the library's own ``setpara`` (a
``param_card.dat`` written from MG5's default card of the restricted model,
with ``ident_card.dat``) and prints every Laurent piece MG5 writes
(``<name>_2EPS_``, ``_1EPS_``, ``_FIN_``) bit-exactly in double and quadruple
precision. The output JSON maps each CT parameter (its UFO name) and epsilon
power to the double value (``repr`` of the real and imaginary parts, signed
zeros kept) and the quadruple one (40 significant digits).

Run with the Python that runs MG5_aMC (it imports MG5 from ``--mg5``). The
UFO's ``.py`` and ``restrict_*.dat`` files are copied into the new
``--output`` directory and imported from there (no pickle of the UFO's own
directory is read or written).
"""

import argparse
import hashlib
import json
import logging
import platform
import shutil
import struct
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, localcontext
from pathlib import Path

POLES = {"2EPS": -2, "1EPS": -1, "FIN": 0}
_CUTS_INC = """        logical fixed_extra_scale
        integer maxjetflavor
        double precision mue_ref_fixed, mue_over_ref
"""


def _quadruple(bits: int) -> str:
    """The IEEE binary128 number with these bits, 40 significant digits."""

    sign = -1 if bits >> 127 else 1
    exponent = (bits >> 112) & 0x7FFF
    fraction = bits & ((1 << 112) - 1)
    if exponent == 0x7FFF:
        return "nan" if fraction else ("-inf" if sign < 0 else "inf")
    if exponent == 0:
        if fraction == 0:
            return "-0" if sign < 0 else "0"
        mantissa, power = fraction, -16382 - 112
    else:
        mantissa, power = fraction | (1 << 112), exponent - 16383 - 112
    with localcontext() as context:
        context.prec = 60
        value = Decimal(sign * mantissa) * (Decimal(2) ** power)
        context.prec = 40
        return str(+value)


def _double(bits: int) -> str:
    return repr(struct.unpack(">d", bits.to_bytes(8, "big"))[0])


def _pieces(builder):
    """[(UFO name, epsilon power, Fortran name, complex)] of every Laurent
    piece of a CT parameter the library holds."""

    pieces = []
    for parameter in builder.params_indep + builder.params_dep:
        name = parameter.name
        if not name.endswith("_"):
            continue
        stem, _, pole = name[:-1].rpartition("_")
        if pole not in POLES or not builder.check_needed_param(name):
            continue
        ufo = stem[4:] if stem.lower().startswith("mdl_") else stem
        pieces.append((ufo, POLES[pole], name.upper(), parameter.type == "complex"))
    return sorted(pieces)


def _driver(pieces) -> str:
    lines = [
        "      PROGRAM DUMPCT",
        "      IMPLICIT NONE",
        "      INCLUDE 'coupl.inc'",
        "      INCLUDE 'input.inc'",
        "      INCLUDE 'mp_coupl.inc'",
        "      INCLUDE 'mp_input.inc'",
        "      CALL SETPARA('param_card.dat')",
    ]
    for ufo, power, fortran, is_complex in pieces:
        routine = "PUTC" if is_complex else "PUTR"
        lines += [
            f"      CALL {routine}('{ufo}',{power},",
            f"     $ {fortran},",
            f"     $ MP__{fortran})",
        ]
    lines += ["      WRITE(*,'(A)') 'DUMPCT_DONE'", "      END", ""]
    lines += [
        "      SUBROUTINE PUTC(NAME, POWER, X, Q)",
        "      IMPLICIT NONE",
        "      CHARACTER*(*) NAME",
        "      INTEGER POWER",
        "      DOUBLE COMPLEX X",
        "      COMPLEX*32 Q",
        "      CALL PUT(NAME, POWER, DBLE(X), DIMAG(X), REAL(Q,KIND=16),",
        "     $ AIMAG(Q))",
        "      END",
        "",
        "      SUBROUTINE PUTR(NAME, POWER, X, Q)",
        "      IMPLICIT NONE",
        "      CHARACTER*(*) NAME",
        "      INTEGER POWER",
        "      DOUBLE PRECISION X",
        "      REAL*16 Q",
        "      CALL PUT(NAME, POWER, X, 0D0, Q, 0E0_16)",
        "      END",
        "",
        "      SUBROUTINE PUT(NAME, POWER, XR, XI, QR, QI)",
        "      IMPLICIT NONE",
        "      CHARACTER*(*) NAME",
        "      INTEGER POWER",
        "      DOUBLE PRECISION XR, XI",
        "      REAL*16 QR, QI",
        "      INTEGER*8 BR, BI",
        "      INTEGER*16 CR, CI",
        "      BR = TRANSFER(XR, BR)",
        "      BI = TRANSFER(XI, BI)",
        "      CR = TRANSFER(QR, CR)",
        "      CI = TRANSFER(QI, CI)",
        "      WRITE(*,'(A,1X,A,1X,I3,4(1X,Z0))') 'CT', NAME, POWER, BR, BI,",
        "     $ CR, CI",
        "      END",
        "",
    ]
    return "\n".join(lines)


def _param_card(model, default_card: Path, card: dict, output: Path) -> dict:
    """Write MG5's default card of the restricted model with the external
    parameters of ``card`` (UFO names) set to their decimal strings verbatim
    (the quadruple-precision reader parses the text, so the card's decimals
    reach both precisions exactly as given); returns {UFO name: value
    written} of every external parameter of the restricted model."""

    entries, names = {}, {}
    for parameter in model["parameters"][("external",)]:
        name = (
            parameter.name[4:]
            if parameter.name.lower().startswith("mdl_")
            else parameter.name
        )
        key = (parameter.lhablock.lower(), tuple(int(c) for c in parameter.lhacode))
        names[key] = name
        if name in card:
            entries[key] = card[name]
    lines, block, written = [], None, {}
    for line in default_card.read_text().splitlines():
        body, hash_, comment = line.partition("#")
        fields = body.split()
        key = None
        if fields and fields[0].upper() == "BLOCK":
            block = fields[1].lower()
        elif fields and fields[0].upper() == "DECAY":
            block, key = "decay", ("decay", (int(fields[1]),))
            value_at = 2
        elif block is not None and len(fields) >= 2:
            key, value_at = (block, tuple(int(f) for f in fields[:-1])), len(fields) - 1
        if key in names:
            if key in entries:
                fields[value_at] = entries[key]
                line = " ".join(fields) + (f" {hash_}{comment}" if hash_ else "")
            written[names[key]] = fields[value_at]
        lines.append(line)
    missing = set(names.values()) - set(written)
    if missing:
        raise RuntimeError(
            f"external parameters missing from the default card: {sorted(missing)}"
        )
    output.write_text("\n".join(lines) + "\n")
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mg5", type=Path, required=True, help="MG5_aMC source tree")
    parser.add_argument("--ufo", type=Path, required=True, help="loop UFO directory")
    parser.add_argument(
        "--card",
        type=Path,
        required=True,
        help="JSON {UFO external parameter name: decimal string}",
    )
    parser.add_argument("--output", type=Path, required=True, help="new work directory")
    parser.add_argument("--json", type=Path, required=True, help="result file")
    parser.add_argument("--compile-jobs", type=int, default=8)
    args = parser.parse_args()
    mg5, ufo, output = args.mg5.resolve(), args.ufo.resolve(), args.output.resolve()
    if output.exists():
        parser.error(f"refusing to overwrite {output}")
    card = json.loads(args.card.read_text())
    model_copy = output / "ufo" / ufo.name
    model_copy.mkdir(parents=True)
    for source in sorted(ufo.iterdir()):
        if source.suffix == ".py" or (
            source.name.startswith("restrict_") and source.suffix == ".dat"
        ):
            shutil.copy2(source, model_copy / source.name)

    sys.dont_write_bytecode = True
    sys.path.insert(0, str(mg5))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    logging.basicConfig(level=logging.INFO)
    from madgraph.interface.master_interface import MasterCmd
    from madgraph.iolibs import export_v4
    from madloop_export import production_make_opts
    from models import import_ufo
    from references import fix_qp_model_functions

    report = {"mg5": "MG5_aMC 3.7.0", "ufo": ufo.name, "host": platform.node()}
    import_ufo.ReadWrite = False
    command = MasterCmd()
    for setting in (
        "automatic_html_opening False",
        "auto_update 0",
        "complex_mass_scheme False",
    ):
        command.exec_cmd("set " + setting)
    start = time.perf_counter()
    command.exec_cmd(f"import model {model_copy}")
    command.exec_cmd("set gauge Feynman")
    model = command._curr_model
    restriction = model_copy / "restrict_default.dat"
    report["restriction"] = (
        {
            "file": "restrict_default.dat",
            "sha256": hashlib.sha256(restriction.read_bytes()).hexdigest(),
        }
        if restriction.exists()
        else None
    )
    library = output / "Source" / "MODEL"
    library.mkdir(parents=True)
    (output / "Cards").mkdir()
    builder = export_v4.UFO_model_to_mg4(
        model,
        str(library),
        {
            "complex_mass": False,
            "export_format": "madloop",
            "mp": True,
            "loop_induced": False,
            "output_options": {"vector_size": 0},
        },
    )
    builder.build([])
    report["export_s"] = time.perf_counter() - start
    pieces = _pieces(builder)

    text, repairs = fix_qp_model_functions((library / "model_functions.f").read_text())
    (library / "model_functions.f").write_text(text)
    report["quadruple_precision_model_function_repairs"] = repairs
    flags = production_make_opts(mg5)
    # A standalone export's Source/make_opts: FFLAGS = -w -fPIC, the global
    # flag, and gfortran's -ffixed-line-length-132.
    fflags = ["-w", "-fPIC", *flags["GLOBAL_FLAG"].split(), "-ffixed-line-length-132"]
    # The Source includes of couplings.f, as a MadLoop standalone export has
    # them (cuts.inc declares the running-scale settings, the others empty).
    (output / "Source" / "cuts.inc").write_text(_CUTS_INC)
    (output / "Source" / "maxparticles.inc").write_text("")
    (output / "Source" / "run.inc").write_text("")
    report["fortran_flags"] = {"FFLAGS": " ".join(fflags), "mg5_production": flags}
    # The library's objects, as its makefile lists them (makeinc.inc).
    listed = (library / "makeinc.inc").read_text().split("MODEL =", 1)[1].split()
    sources = [Path(obj).stem + ".f" for obj in listed]
    run = library / "run"
    run.mkdir()
    (run / "dumpct.f").write_text(_driver(pieces))
    start = time.perf_counter()
    # model_functions.f first: it defines the modules (b0f caching) the rest
    # may use; its repairs lengthen lines (references.madloop_model_fix).
    subprocess.run(
        ["gfortran", "-fno-common", "-ffixed-line-length-none"]
        + [flag for flag in fflags if flag != "-ffixed-line-length-132"]
        + ["-c", "model_functions.f", "-o", "model_functions.o"],
        cwd=library,
        check=True,
    )

    def compile_one(name: str) -> None:
        subprocess.run(
            ["gfortran", *fflags, "-c", name, "-o", f"{Path(name).stem}.o"],
            cwd=library,
            check=True,
        )

    rest = [name for name in sources if name != "model_functions.f"]
    with ThreadPoolExecutor(args.compile_jobs) as pool:
        list(pool.map(compile_one, rest))
    compiled = [library / f"{Path(name).stem}.o" for name in sources]
    subprocess.run(
        [
            "gfortran",
            *fflags,
            "-ffixed-line-length-none",
            "-I",
            str(library),
            "dumpct.f",
            *map(str, compiled),
            "-o",
            "dumpct",
        ],
        cwd=run,
        check=True,
    )
    report["compile_s"] = time.perf_counter() - start

    shutil.copy2(library / "ident_card.dat", run / "ident_card.dat")
    default_card = output / "Cards" / "param_card.dat"
    if not default_card.exists():
        default_card = library / "param_card.dat"
    report["card"] = _param_card(model, default_card, card, run / "param_card.dat")
    report["card_unknown"] = sorted(set(card) - set(report["card"]))
    result = subprocess.run(
        ["./dumpct"], cwd=run, check=True, capture_output=True, text=True
    )
    (run / "dumpct.log").write_text(result.stdout + result.stderr)
    if "DUMPCT_DONE" not in result.stdout:
        raise RuntimeError("the driver did not finish")
    values = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if not fields or fields[0] != "CT":
            continue
        name, power, *bits = fields[1:]
        br, bi, cr, ci = (int(b, 16) for b in bits)
        values.setdefault(name, {})[power] = {
            "double": [_double(br), _double(bi)],
            "quadruple": [_quadruple(cr), _quadruple(ci)],
        }
    report["pieces"] = len(pieces)
    report["values"] = values
    args.json.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print("MADLOOP_CT_PARAMETERS_DONE", len(pieces), flush=True)


if __name__ == "__main__":
    main()
