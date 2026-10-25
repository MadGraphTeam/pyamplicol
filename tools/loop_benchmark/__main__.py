# SPDX-License-Identifier: 0BSD
"""Command line of the gate-G1 benchmark (``python -m tools.loop_benchmark``).

Subcommands:

- ``streams``: freeze the phase-space streams (``streams.py``);
- ``pyamplicol``: time pyAmpliCol v2 on one process (``pyamplicol_v2.py``),
  optionally followed by stability and every-pole checks of the same
  generation;
- ``stability``: stability estimates at chosen stream points (or at the
  reference fixture's points, ``--fixture``);
- ``ward``: the Ward identity at chosen stream points (``pyamplicol_v2.ward``);
- ``providers``: time MadLoop, Recola and OpenLoops in production mode on the
  same stream (``providers.py``);
- ``gate``: combine the records into the gate table (``gate.py``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.loop_benchmark")
    commands = parser.add_subparsers(dest="command", required=True)

    freeze = commands.add_parser("streams", help="write streams/<key>.json")
    freeze.add_argument("keys", nargs="*")

    v2 = commands.add_parser("pyamplicol", help="time pyAmpliCol v2")
    v2.add_argument("process")
    v2.add_argument("--accuracy", choices=("full", "nlc", "lc"), default="full")
    v2.add_argument("--inputs", choices=("python", "native"), default="python")
    v2.add_argument("--schedule", choices=("B", "M"), default="B")
    v2.add_argument("--lanes", type=int, default=16)
    v2.add_argument("--batches", type=int, nargs="+", default=[1, 8, 32, 128])
    v2.add_argument("--reps", type=int, default=3)
    v2.add_argument(
        "--min-points",
        type=int,
        default=8,
        help="points per B and round (several blocks of a small B)",
    )
    v2.add_argument(
        "--budget",
        type=float,
        default=900.0,
        help="seconds a B may take over all rounds; larger B are skipped",
    )
    v2.add_argument(
        "--warm-up",
        type=int,
        help="points of each B's untimed warm-up (default: the whole block; "
        "one chunk of lanes compiles every kernel)",
    )
    v2.add_argument("--native-build", type=Path, help="staged native build directory")
    v2.add_argument(
        "--scratch",
        type=Path,
        help="parent of the run's temporary model directory (default: the "
        "system's temporary directory)",
    )
    v2.add_argument("--json", type=Path)
    v2.add_argument(
        "--stability-points",
        type=int,
        nargs="+",
        help="after the timing: stability estimates at these stream points",
    )
    v2.add_argument(
        "--stability-arithmetic",
        nargs="+",
        choices=("double", "double-double"),
        default=["double"],
    )
    v2.add_argument("--stability-json", type=Path, help="the stability record")
    v2.add_argument(
        "--physical-points",
        type=int,
        nargs="+",
        help="after the timing: one evaluation with every pole at these points "
        "(components, Catani's poles)",
    )
    v2.add_argument(
        "--store",
        type=Path,
        help="after generation: store the process (the artifact's loop runtime "
        "member with native point inputs, and generation.json) in this new "
        "directory",
    )
    v2.add_argument(
        "--generate-only",
        action="store_true",
        help="stop after generation and --store (no accuracy check, no timing)",
    )
    v2.add_argument(
        "--load",
        type=Path,
        help="time a stored process (--store) instead of generating: loaded "
        "as the public runtime loads an artifact, nothing regenerated",
    )

    wardp = commands.add_parser(
        "ward", help="the Ward identity at chosen stream points"
    )
    wardp.add_argument("process")
    wardp.add_argument("--points", type=int, nargs="+", required=True)
    wardp.add_argument("--legs", type=int, nargs="+", required=True)
    wardp.add_argument("--factors", nargs="+", choices=("1", "i"), default=["1", "i"])
    wardp.add_argument("--lanes", type=int, default=16)
    wardp.add_argument(
        "--physical",
        action="store_true",
        help="also evaluate each point without the substitution (its physical "
        "scale for the gate's Ward bound)",
    )
    wardp.add_argument("--native-build", type=Path)
    wardp.add_argument("--scratch", type=Path, help="parent of the model directory")
    wardp.add_argument("--json", type=Path)

    stable = commands.add_parser(
        "stability", help="stability estimates at chosen stream points"
    )
    stable.add_argument("process")
    stable.add_argument("--points", type=int, nargs="+", required=True)
    stable.add_argument("--accuracy", choices=("full", "nlc", "lc"), default="full")
    stable.add_argument("--inputs", choices=("python", "native"), default="python")
    stable.add_argument(
        "--arithmetic",
        nargs="+",
        choices=("double", "double-double"),
        default=["double"],
    )
    stable.add_argument("--native-build", type=Path)
    stable.add_argument("--scratch", type=Path, help="parent of the model directory")
    stable.add_argument("--json", type=Path)
    stable.add_argument(
        "--load", type=Path, help="a stored process (pyamplicol --store)"
    )
    stable.add_argument(
        "--fixture",
        action="store_true",
        help="the points are the reference fixture's (the accuracy check's, at "
        "its own scales), each row with its deviation from every reference",
    )
    stable.set_defaults(lanes=16, schedule="B")

    providers = commands.add_parser("providers", help="time the providers")
    providers.add_argument("process")
    providers.add_argument(
        "--providers", nargs="+", default=["openloops", "recola", "madloop"]
    )
    providers.add_argument("--points", type=int, default=16)
    providers.add_argument("--cpu", type=int, required=True)
    providers.add_argument("--work", type=Path, required=True)
    providers.add_argument(
        "--reference-root",
        type=Path,
        help="provider reference root (default: $LOOP_REFERENCE_ROOT)",
    )
    providers.add_argument("--mg5", type=Path, help="MG5_aMC tree")
    providers.add_argument("--recola", type=Path, help="Recola2 tree")
    providers.add_argument("--openloops", type=Path, help="OpenLoops installation")
    providers.add_argument(
        "--madloop-export",
        type=Path,
        help="MadLoop export (default: madloop.export of processes.json)",
    )
    providers.add_argument(
        "--madloop-stages",
        action="store_true",
        help="also time MadLoop's stages with an instrumented driver",
    )
    providers.add_argument("--json", type=Path)

    gate = commands.add_parser("gate", help="combine records into the gate table")
    gate.add_argument("records", nargs="+", type=Path)
    gate.add_argument("--json", type=Path, required=True)
    gate.add_argument(
        "--values-json", type=Path, help="also write the per-point values"
    )
    gate.add_argument(
        "--reference-root",
        type=Path,
        help="provider reference root: every provider file (MadLoop exports "
        "and their generation times) is resolved relative to it, never through "
        "the absolute paths of the records (default: $LOOP_REFERENCE_ROOT)",
    )
    gate.add_argument(
        "--meta",
        nargs="*",
        metavar="KEY=VALUE",
        help="labels for the report (revisions, date, host)",
    )

    options = parser.parse_args(argv)
    if options.command == "streams":
        from . import streams

        streams.write(options.keys or streams.keys())
        return 0
    if options.command == "pyamplicol":
        from . import pyamplicol_v2

        return pyamplicol_v2.main(options)
    if options.command == "stability":
        from . import pyamplicol_v2

        return pyamplicol_v2.check_points(options)
    if options.command == "ward":
        from . import pyamplicol_v2

        return pyamplicol_v2.ward(options)
    if options.command == "providers":
        from . import providers as module

        return module.main(options)
    from . import gate as module

    return module.main(options)


if __name__ == "__main__":
    sys.exit(main())
