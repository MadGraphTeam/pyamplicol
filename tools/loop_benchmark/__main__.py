# SPDX-License-Identifier: 0BSD
"""Command line of the gate-G1 benchmark (``python -m tools.loop_benchmark``).

Subcommands:

- ``streams``: freeze the phase-space streams (``streams.py``);
- ``pyamplicol``: time pyAmpliCol v2 on one process (``pyamplicol_v2.py``);
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
    v2.add_argument("--native-build", type=Path, help="staged native build directory")
    v2.add_argument("--scratch", type=Path, default=Path("/tmp"))
    v2.add_argument("--json", type=Path)

    stable = commands.add_parser(
        "stability", help="stability estimates at chosen stream points"
    )
    stable.add_argument("process")
    stable.add_argument("--points", type=int, nargs="+", required=True)
    stable.add_argument("--accuracy", choices=("full", "nlc", "lc"), default="full")
    stable.add_argument("--inputs", choices=("python", "native"), default="python")
    stable.add_argument("--native-build", type=Path)
    stable.add_argument("--scratch", type=Path, default=Path("/tmp"))
    stable.add_argument("--json", type=Path)
    stable.set_defaults(lanes=16, schedule="B")

    providers = commands.add_parser("providers", help="time the providers")
    providers.add_argument("process")
    providers.add_argument(
        "--providers", nargs="+", default=["openloops", "recola", "madloop"]
    )
    providers.add_argument("--points", type=int, default=16)
    providers.add_argument("--cpu", type=int, required=True)
    providers.add_argument("--work", type=Path, required=True)
    providers.add_argument("--madloop-export", type=Path)
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
    if options.command == "providers":
        from . import providers as module

        return module.main(options)
    from . import gate as module

    return module.main(options)


if __name__ == "__main__":
    sys.exit(main())
