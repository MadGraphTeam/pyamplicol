#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Compare actual virtual poles from native reference controls, plus QCD oracles."""

import argparse
import itertools
import json
import math
import os
import subprocess
from pathlib import Path

COEFFICIENTS = ("born", "finite", "single_pole", "double_pole")


def close(actual, expected):
    return math.isfinite(actual) and abs(actual - expected) <= 2e-9 * max(
        abs(expected), 1e-3
    )


def dot(p, q):
    return p[0] * q[0] - sum(a * b for a, b in zip(p[1:], q[1:], strict=True))


def analytic(point, alpha_s):
    s = 2 * dot(point[0], point[1])
    t = -2 * dot(point[0], point[2])
    u = -2 * dot(point[0], point[3])
    born = 4 / 9 * (4 * math.pi * alpha_s) ** 2 * (t * t + u * u) / (s * s)
    return {"born": born, "double_pole": -16 / 3 * alpha_s / (2 * math.pi) * born}


def top_pair(point, parameters):
    """Massive Dirac Born trace and the two massless external-leg double poles."""
    s = 2 * dot(point[0], point[1])
    mt2_minus_t = 2 * dot(point[0], point[2])
    mt2_minus_u = 2 * dot(point[0], point[3])
    mass_squared = parameters["mt"] ** 2
    born = 4 / 9 * (4 * math.pi * parameters["alpha_s"]) ** 2 * (
        mt2_minus_t**2 + mt2_minus_u**2 + 2 * mass_squared * s
    ) / s**2
    return {
        "born": born,
        "double_pole": -8 / 3 * parameters["alpha_s"] / (2 * math.pi) * born,
    }


def gluon_scattering(point, parameters):
    """PDG gg scattering Born, including the final identical-particle factor."""
    s = 2 * dot(point[0], point[1])
    t = -2 * dot(point[0], point[2])
    u = -2 * dot(point[0], point[3])
    born = 9 / 4 * (4 * math.pi * parameters["alpha_s"]) ** 2 * (
        3 - u * t / s**2 - s * u / t**2 - s * t / u**2
    )
    return {
        "born": born,
        "double_pole": -12 * parameters["alpha_s"] / (2 * math.pi) * born,
    }


def drell_yan(point, parameters):
    """Independent photon-exchange Born and timelike QCD form-factor control.

    Cepsilon=(4*pi)^eps/Gamma(1-eps), physical couplings, initial average.
    See README for the continuation and epsilon-prefactor conversion. This
    closed form is a validation oracle, never a production evaluator.
    """
    s = 2 * dot(point[0], point[1])
    t = -2 * dot(point[0], point[2])
    u = -2 * dot(point[0], point[3])
    e_squared = 4 * math.pi / parameters["aEWM1"]
    born = 2 * e_squared**2 * (4 / 9) / 3 * (t * t + u * u) / s**2
    prefactor = born * parameters["alpha_s"] * (4 / 3) / (2 * math.pi)
    logarithm = math.log(parameters["mu"] ** 2 / s)
    return {
        "born": born,
        "finite": prefactor * (math.pi**2 - 8 - 3 * logarithm - logarithm**2),
        "single_pole": prefactor * (-3 - 2 * logarithm),
        "double_pole": -2 * prefactor,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture", type=Path, default=Path(__file__).with_name("uudd_qcd.json")
    )
    parser.add_argument("--bin-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--providers",
        nargs="+",
        choices=("madloop", "recola", "openloops"),
        default=["madloop", "recola", "openloops"],
    )
    parser.add_argument("--madloop-dir", type=Path)
    parser.add_argument(
        "--batch-sizes", nargs="+", type=int, default=[3, 1, 8, 32, 128]
    )
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if args.repetitions <= 0 or any(b <= 0 for b in args.batch_sizes):
        parser.error("batch sizes and repetitions must be positive")
    fixture = json.loads(args.fixture.read_text())
    if fixture["process"] == "u u~ > d d~":
        case = "uudd"
    elif fixture["process"] == "u u~ > e- e+ / z":
        case = "drell-yan"
        if args.providers != ["madloop"]:
            parser.error("photon-only Drell-Yan requires --providers madloop")
    elif fixture["process"] == "u u~ > t t~":
        case = "top-pair"
    elif fixture["process"] == "g g > g g":
        case = "gluon-scattering"
    else:
        parser.error("the control drivers do not support this fixture process")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    if args.madloop_dir:
        environment["PYLOOP_MADLOOP_DIR"] = str(args.madloop_dir.resolve())
    p = fixture["parameters"]
    report = {
        "fixture": fixture,
        "validation": "passed",
        "measurements": [],
        "timing_scope": (
            "warm native provider calls including actual poles; control timings only"
        ),
    }
    for batch in args.batch_sizes:
        points = list(itertools.islice(itertools.cycle(fixture["points"]), batch))
        header = (
            f"{batch} {args.repetitions} {p['alpha_s']} {p['mu']} {p['mt']} {p['mb']} "
            f"{p.get('aEWM1', 132.507)}\n"
        )
        payload = (
            header
            + "\n".join(" ".join(map(str, leg)) for point in points for leg in point)
            + "\n"
        )
        measurements = []
        for provider in args.providers:
            completed = subprocess.run(
                [str(args.bin_dir.resolve() / f"{provider}-{case}")],
                input=payload,
                text=True,
                capture_output=True,
                env=environment,
                cwd=output,
            )
            (output / f"{provider}-batch{batch}.log").write_text(
                completed.stdout + completed.stderr
            )
            completed.check_returncode()
            lines = [
                line.split("LOOP_REFERENCE_JSON ", 1)[1]
                for line in completed.stdout.splitlines()
                if line.startswith("LOOP_REFERENCE_JSON ")
            ]
            if len(lines) != 1:
                raise RuntimeError(
                    f"{provider}: missing/ambiguous result; inspect {output}"
                )
            measurement = json.loads(lines[0])
            if not measurement["actual_poles"] or len(measurement["results"]) != batch:
                raise RuntimeError(f"{provider}: invalid result contract")
            for lane, (point, result) in enumerate(
                zip(points, measurement["results"], strict=True)
            ):
                expected_values = (
                    drell_yan(point, p)
                    if case == "drell-yan"
                    else top_pair(point, p)
                    if case == "top-pair"
                    else gluon_scattering(point, p)
                    if case == "gluon-scattering"
                    else analytic(point, p["alpha_s"])
                )
                for name, expected in expected_values.items():
                    if not close(result[name], expected):
                        raise AssertionError(
                            f"{provider} lane {lane}: analytic {name} mismatch"
                        )
            measurements.append(measurement)
        for left, right in itertools.combinations(measurements, 2):
            for lane, (lresult, rresult) in enumerate(
                zip(left["results"], right["results"], strict=True)
            ):
                for name in COEFFICIENTS:
                    if not close(lresult[name], rresult[name]):
                        raise AssertionError(
                            f"{left['provider']} vs {right['provider']}, "
                            f"batch {batch} lane {lane}: {name} mismatch "
                            f"({lresult[name]} vs {rresult[name]})"
                        )
        report["measurements"].extend(measurements)
        comparison = (
            "all coefficients agree"
            if len(measurements) > 1
            else "no pairwise comparison"
        )
        print(
            f"batch {batch}: {len(measurements)} providers, "
            f"analytic controls pass; {comparison}"
        )
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
