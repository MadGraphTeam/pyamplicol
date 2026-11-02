#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""The UFO counterterm couplings behind a MadLoop export's calls.

MG5_aMC renames couplings twice before it writes a call:

* the UFO conversion gives couplings with identical expressions the first
  one's name (``UFOMG5Converter.optimise_interaction``);
* the model restriction merges couplings of equal value at the restriction
  card's point, up to a sign, into the alphabetically first name
  (``RestrictModel.detect_identical_couplings`` / ``merge_iden_couplings``):
  on loop_qcd_qed_sm_Gmu's default restriction ``R2_uuA2Cp`` is called as
  ``R2_ccA2Cp``, ``R2_GTT2Cpb`` as ``R2_GCC2Cps`` and the UV coupling
  ``c_UVvexveA1EW_1eps`` as ``R2_AWWcs``.

The export's coupling names therefore do not say which UFO couplings MadLoop
inserts. This script regenerates the export's amplitudes with the export's
own MG5 settings (``madloop_export.mg5_session``; no output, no model pickle
written), records both renamings and writes ``<export>.ct_couplings.json``
next to the export, per subprocess (MG5's ``shell_string`` without the
process number, i.e. the ``P<n>_`` directory suffix):

* ``r2``: the UFO couplings of the R2 vertices MadLoop attaches to the loops
  (``CT_vertices`` of the loop diagrams; couplings the restriction sets to
  zero are absent), the input of the rule-1 R2 correction of
  m-sm/PLAN.md §1.4;
* ``r2_called_as``: those whose call passes another name (``-`` = the merge's
  sign);
* ``ct_tokens``: per helas-call file kind (``ampb``: CT vertices of the loops,
  ``uvct``: UV counterterm diagrams), every coupling name the calls pass ->
  the UFO couplings it stands for (``madloop_ct_selection.py`` classifies the
  CT amplitudes by them).

madloop_export.py writes the same record for every new export. Run with the
Python that runs MG5_aMC:

    python tools/loop_reference/madloop_ct_couplings.py --mg5 $MG5 \\
        --spec tools/loop_reference/required_processes.json --process uux_emep_ew \\
        --export $RUNS/msm/uux_emep_ew/madloop-export
"""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

HERE = Path(__file__).resolve().parent
SOURCE = ("MG5_aMC regeneration of the export's amplitudes with its own settings (madloop_ct_couplings.py): "
          "UFO couplings of the R2 vertices attached to the loops; called_as = the merged name its call passes")


def record_path(export):
    export = Path(export)
    return export.parent / f"{export.name}.ct_couplings.json"


class Recorder:
    """Records MG5's coupling renamings of the last model import (conversion
    and restriction); install before ``import model``."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.original = {}    # interaction id -> UFO coupling names before the conversion's renaming
        self.renamed = {}     # conversion: name -> name of the identical expression
        self.merged = {}      # restriction: name -> (kept name, sign)
        self.zero = set()     # restriction: couplings set to zero
        self.counterterms = {}  # pdg -> [names of the particle counterterms before the restriction]

    def install(self):
        from models import import_ufo
        import madgraph.iolibs.files as files

        recorder = self
        converter, restrict = import_ufo.UFOMG5Converter, import_ufo.RestrictModel
        load_model, optimise = converter.load_model, converter.optimise_interaction
        restrict_model, merge = restrict.restrict_model, restrict.merge_iden_couplings
        remove = restrict.remove_interactions
        full_model = import_ufo.import_full_model

        def full(*args, **kwargs):
            # The UFO is converted from its .py files (a model pickle holds the
            # converted, already renamed interactions); nothing is written
            # (import_ufo.ReadWrite = False).
            uptodate = files.is_uptodate
            files.is_uptodate = lambda *a, **k: False
            try:
                return full_model(*args, **kwargs)
            finally:
                files.is_uptodate = uptodate

        def load(self, *args, **kwargs):
            recorder.reset()
            return load_model(self, *args, **kwargs)

        def optimise_interaction(self, interaction):
            recorder.original.setdefault(interaction["id"], sorted(set(interaction["couplings"].values())))
            result = optimise(self, interaction)
            recorder.renamed = dict(getattr(self, "iden_couplings", {}))
            return result

        def restriction(self, *args, **kwargs):
            recorder.merged, recorder.zero = {}, set()
            recorder.counterterms = {
                particle["pdg_code"]: sorted({name for value in particle["counterterm"].values()
                                              for name in value.values()})
                for particle in self["particles"] if particle.get("counterterm")}
            return restrict_model(self, *args, **kwargs)

        def merge_identical(self, couplings):
            main = couplings[0][0]
            for name, sign in couplings[1:]:
                recorder.merged[name] = (main, sign)
            return merge(self, couplings)

        def remove_interactions(self, zero_couplings):
            recorder.zero.update(zero_couplings)
            return remove(self, zero_couplings)

        import_ufo.import_full_model = full
        converter.load_model, converter.optimise_interaction = load, optimise_interaction
        restrict.restrict_model, restrict.merge_iden_couplings = restriction, merge_identical
        restrict.remove_interactions = remove_interactions

    def called(self, name, particle=False):
        """The name a UFO coupling is called by (``-`` prefix: opposite sign),
        or None when the restriction sets it to zero. A particle counterterm
        takes the kept name without the sign (``merge_iden_couplings``)."""
        name = self.renamed.get(name, name)
        if name == "ZERO" or name in self.zero:
            return None
        main, sign = self.merged.get(name, (name, 1))
        return main if particle or sign == 1 else f"-{main}"

    def resolve(self, interaction):
        """[(UFO coupling, called name)] of a final interaction; the called
        names must be exactly the interaction's couplings."""
        pairs = [(name, self.called(name)) for name in self.original.get(interaction["id"], ())]
        pairs = [(name, called) for name, called in pairs if called is not None]
        final = {value.lstrip("-") for value in interaction["couplings"].values()}
        if {called.lstrip("-") for _, called in pairs} != final:
            raise RuntimeError(f"interaction {interaction['id']}: couplings {sorted(final)} are not the renamed "
                               f"UFO couplings {pairs}")
        return pairs


def subprocess_record(amplitude, recorder):
    model = amplitude["process"]["model"]
    interactions = model["interaction_dict"]
    r2, called_as = set(), {}
    tokens = {"ampb": {}, "uvct": {}}

    def add(kind, ufo, called):
        tokens[kind].setdefault(called.lstrip("-").upper(), set()).add(ufo)

    for diagram in amplitude["loop_diagrams"]:
        for vertex in diagram["CT_vertices"]:
            interaction = interactions[vertex["id"]]
            for ufo, called in recorder.resolve(interaction):
                add("ampb", ufo, called)
                if interaction.is_R2():
                    r2.add(ufo)
                    if called != ufo:
                        called_as[ufo] = called
    legs = {abs(leg["id"]) for leg in amplitude["process"]["legs"]}
    for diagram in amplitude["loop_UVCT_diagrams"]:
        for vertex in diagram["vertices"]:
            if vertex["id"] in interactions:
                for ufo, called in recorder.resolve(interactions[vertex["id"]]):
                    add("uvct", ufo, called)
        for name in diagram["UVCT_couplings"]:
            if isinstance(name, str):
                ufos = {ufo for pdg in legs for ufo in recorder.counterterms.get(pdg, ())
                        if recorder.called(ufo, particle=True) == name}
                for ufo in ufos or {name}:
                    add("uvct", ufo, name)
    return {"r2": sorted(r2), "r2_called_as": dict(sorted(called_as.items())),
            "ct_tokens": {kind: {k: sorted(v) for k, v in sorted(m.items())} for kind, m in tokens.items()}}


def records(amplitudes, recorder):
    """The record of every amplitude, keyed by its subprocess directory suffix."""
    out = {}
    for amplitude in amplitudes:
        key = amplitude["process"].shell_string(print_id=False)
        if key in out:
            raise RuntimeError(f"two amplitudes share the subprocess name {key}")
        out[key] = subprocess_record(amplitude, recorder)
    return out


def subprocess_key(directory):
    """``P3_uux_ttx`` -> ``uux_ttx`` (MG5's ``P<process number>_<shell string>``)."""
    match = re.fullmatch(r"P\d+_(.+)", Path(directory).name)
    if not match:
        raise ValueError(f"{directory} is not a MadLoop subprocess directory")
    return match.group(1)


def fortran_tokens(export, subprocess_dir):
    """Upper-case names in the non-comment lines of a subprocess's Fortran sources."""
    found = set()
    token = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    for source in sorted((Path(export) / "SubProcesses" / subprocess_dir).glob("*.f")):
        for line in source.read_text(errors="replace").splitlines():
            if line[:1] in ("C", "c", "*", "!"):
                continue  # fixed-form comment line
            found.update(word.upper() for word in token.findall(line.split("!", 1)[0]))
    return found


def check_export(export, record):
    """Every subprocess directory has a record and every recorded CT call name
    occurs in its Fortran sources."""
    directories = sorted(p.name for p in (Path(export) / "SubProcesses").glob("P*_*") if p.is_dir())
    for directory in directories:
        key = subprocess_key(directory)
        if key not in record["subprocesses"]:
            raise RuntimeError(f"{export}: no record for {directory}")
        missing = sorted(set().union(*map(set, record["subprocesses"][key]["ct_tokens"].values()))
                         - fortran_tokens(export, directory))
        if missing:
            raise RuntimeError(f"{export}/{directory}: recorded call names absent from the sources: {missing[:8]}")
    return directories


def write_record(export, command_text, model, complex_mass_scheme, amplitudes, recorder):
    report = {
        "description": __doc__.split("\n\n")[0],
        "source": SOURCE,
        "model": Path(model).name,
        "command": command_text,
        "complex_mass_scheme": complex_mass_scheme,
        "attached_CT_vertices": sum(len(d["CT_vertices"]) for a in amplitudes for d in a["loop_diagrams"]),
        "subprocesses": records(amplitudes, recorder),
    }
    record_path(export).write_text(json.dumps(report, indent=1) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--process", required=True)
    parser.add_argument("--mg5", type=Path, required=True)
    parser.add_argument("--export", type=Path, required=True, help="the existing MadLoop export")
    parser.add_argument("--reference-root", type=Path)
    args = parser.parse_args()

    import madloop_export
    from required_spec import load_process

    mg5 = args.mg5.resolve()
    roots = {"mg5": mg5, "reference": (args.reference_root or mg5.parent.parent).resolve()}
    spec = load_process(args.spec, args.process, roots)
    export = args.export.resolve()
    generation = json.loads((export.parent / f"{export.name}.generation.json").read_text())
    if Path(generation["model"]).name != Path(spec["madloop"]["model"]).name or \
            generation["command"] != spec["madloop"]["process"]:
        raise SystemExit(f"{export}: generated as {generation['model']} / {generation['command']!r}, not as "
                         f"{args.process}'s {spec['madloop']['model']} / {spec['madloop']['process']!r}")
    start = time.perf_counter()
    recorder = Recorder()
    command = madloop_export.mg5_session(spec, mg5, recorder)
    command.exec_cmd("generate " + spec["madloop"]["process"])
    report = write_record(export, spec["madloop"]["process"], spec["madloop"]["model"],
                          madloop_export.complex_mass_scheme(spec), command._curr_amps, recorder)
    if generation.get("attached_CT_vertices") not in (None, report["attached_CT_vertices"]):
        raise SystemExit(f"{export}: {report['attached_CT_vertices']} attached CT vertices, the export has "
                         f"{generation['attached_CT_vertices']}")
    directories = check_export(export, report)
    print(f"MADLOOP_CT_COUPLINGS_DONE {record_path(export)} {len(directories)} subprocess directories "
          f"{time.perf_counter() - start:.1f} s", flush=True)


if __name__ == "__main__":
    sys.path.insert(0, os.fspath(HERE))
    main()
