#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""MG5_aMC's own complex-mass-scheme model of a UFO, evaluated at one card.

MG5_aMC 3.7.0 imports the full UFO as ``import model`` does
(``import_ufo.import_full_model``, ``mdl_`` names), reads the card once with
the scheme off so that it knows which widths are zero (``import_model`` reads
the restriction card before it transforms), applies its own
``Model.change_mass_to_complex_scheme`` and evaluates every parameter and
coupling with its Python model reader
(``ModelReader.set_parameters_and_couplings``) at the card. The helper
``reglog`` takes the principal definition that MG5_aMC's model library writes
whatever the UFO binds (``export_v4``: the reserved helpers; [U3]); every
other helper is the UFO's. No restriction is applied (MG5 would merge
identical couplings and drop zero ones under new names), so every parameter,
counterterm-parameter piece (``mdl_<name>_FIN_``, ``_1EPS_``, ``_2EPS_``),
coupling piece (``<name>``, ``<name>_1eps``, ``<name>_2eps``) and field
counterterm coupling (``UVWfct_<particle>_<index>``) of the scheme is
written, by MG5 name, with MG5's transform record (``to_change`` masses,
real ``mass_widths``, Yukawa ties).

Run with the Python that runs MG5_aMC (it imports MG5 from ``--mg5``). The
UFO's ``.py`` files are copied into a temporary directory and imported from
there (MG5 writes a pickle next to the model it imports).

    mg5_cms_model.py --mg5 <MG5_aMC_v3_7_0> --ufo <UFO dir> --card <param card> \\
        --output <values.json>
"""

import argparse
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path

PRINCIPAL_REGLOG = "(0.0 if z==0.0 else cmath.log(z))"


def _pair(value):
    value = complex(value)
    return [repr(value.real), repr(value.imag)]


def cms_model_values(mg5: Path, ufo: Path, card: Path) -> dict:
    sys.dont_write_bytecode = True
    if str(mg5) not in sys.path:
        sys.path.insert(0, str(mg5))
    logging.getLogger("madgraph").setLevel(logging.ERROR)
    logging.getLogger("madgraph.models").setLevel(logging.ERROR)
    logging.getLogger("madevent").setLevel(logging.ERROR)
    import models.import_ufo as import_ufo

    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / ufo.name
        copy.mkdir()
        for source in ufo.glob("*.py"):
            shutil.copy2(source, copy / source.name)
        model = import_ufo.RestrictModel(
            import_ufo.import_full_model(str(copy), False, "mdl_")
        )
        # As import_model: the widths' values with the scheme still off.
        model.set_parameters_and_couplings(
            param_card=str(card), complex_mass_scheme=False
        )
        model.change_mass_to_complex_scheme(toCMS=True, bypass_check=True)
        for function in model["functions"]:
            if function.name == "reglog":
                function.expr = PRINCIPAL_REGLOG
        # The card is read as written: MG5's CMS card conversion
        # (``convert_to_complex_mass_scheme``) only drops the YUKAWA block,
        # which no longer has inputs, and rewrites an incomplete EW input set,
        # which the transform (no internal-mass branch) never needs.
        model.set_parameters_and_couplings(
            param_card=str(card), complex_mass_scheme=False
        )
        parameters = {
            parameter.name: parameter
            for group in model["parameters"].values()
            for parameter in group
        }
        couplings = {
            coupling.name: coupling
            for group in model["couplings"].values()
            for coupling in group
        }
        cmass = sorted(name for name in parameters if name.startswith("CMASS_"))
        return {
            "source": "MG5_aMC 3.7.0 change_mass_to_complex_scheme, Python model "
            "reader, binary64",
            "card": card.name,
            "cms_masses": cmass,
            "complex_parameters": sorted(
                name
                for name, parameter in parameters.items()
                if parameter.type == "complex"
            ),
            "expressions": {
                name: parameter.expr
                for name, parameter in parameters.items()
                if hasattr(parameter, "expr")
            },
            "parameters": {
                name: _pair(parameter.value) for name, parameter in parameters.items()
            },
            "couplings": {
                name: _pair(coupling.value) for name, coupling in couplings.items()
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mg5", type=Path, required=True, help="MG5_aMC source tree")
    parser.add_argument("--ufo", type=Path, required=True, help="UFO directory")
    parser.add_argument("--card", type=Path, required=True, help="param card")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    values = cms_model_values(
        arguments.mg5.resolve(), arguments.ufo.resolve(), arguments.card.resolve()
    )
    arguments.output.write_text(json.dumps(values, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
