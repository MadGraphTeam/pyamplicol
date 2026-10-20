# SPDX-License-Identifier: 0BSD
"""Compare saved complete records with the frozen binary64 MadLoop reference.

This tool reads JSON only. It never evaluates a process or changes a reference.
For another arithmetic view, pass its record name, such as ``--record ap80``.
The independent reference accuracy remains binary64.
"""

import argparse
import json
from decimal import Decimal, localcontext
from pathlib import Path

DEFAULT_REFERENCE = Path(__file__).with_name("sgluon_qcd.json")
TARGET = Decimal("3e-9")
FLOOR = Decimal("1e-30")
EPSILON = ("finite", "single_pole", "double_pole")
COMPONENTS = (
    ("bare", "bare"),
    ("uv_local", "uv_local"),
    ("uv_external_fields", "fields"),
    ("uv", "uv"),
    ("r2", "r2"),
    ("virtual", "full"),
)


def canonical_order(value):
    return tuple(sorted((name, int(power)) for name, power in value if int(power)))


def real_pair(value):
    assert len(value) == 2
    real, imag = (Decimal(str(x)) for x in value)
    assert real.is_finite() and imag.is_finite() and imag == 0, value
    return real


def compare(actual, expected):
    assert len(actual) == len(expected)
    norm = max(*map(abs, actual), *map(abs, expected), FLOOR)
    errors = [abs(a - b) / norm for a, b in zip(actual, expected, strict=True)]
    return {
        "native": list(map(str, actual)),
        "madloop": list(map(str, expected)),
        "component_norm": str(norm),
        "normalized_errors": list(map(str, errors)),
        "passed": max(errors) < TARGET,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--record", default="double")
    parser.add_argument("--scale-record")
    args = parser.parse_args()
    scale_record = args.scale_record or args.record + "_scale"
    producer = json.loads(args.producer.read_text())
    fixture = json.loads(args.reference.read_text())
    reference, inputs = fixture["madloop"], fixture["inputs"]
    assert {args.record, scale_record} <= producer.keys(), "complete output pending"
    assert producer["orders"]["corrections"] == inputs["corrections"]
    for native_key, reference_key in (
        ("born_squared", "born_orders"),
        ("virtual_squared", "loop_orders"),
    ):
        actual = {canonical_order(order) for order in producer["orders"][native_key]}
        expected = {
            canonical_order(order.items())
            for order in reference[reference_key].values()
        }
        assert actual == expected, (native_key, actual, expected)
        assert len(actual) == 1, (
            "this retained inclusive fixture has one generated sector"
        )
    (born_id,) = reference["born_orders"]
    (loop_id,) = reference["loop_orders"]
    assert (
        Decimal(producer["counts"]["normalization_divisor"])
        == reference["generated_IDEN"]
    )
    assert producer["counts"]["born"] == reference["born"]
    assert producer["counts"]["loop"] == reference["loops"]
    expected_points = [
        *inputs["points"],
        inputs["points"][inputs["changed_scale"]["point_index"]],
    ]
    expected_scales = [*inputs["mu_r2"], inputs["changed_scale"]["mu_r2"]]
    assert reference["points"] == expected_points
    assert reference["mu_r2"] == expected_scales
    assert (
        reference["runtime_parameter_values"]
        == inputs["parameters"] | inputs["fixed_parameters"]
    )
    rows = []
    with localcontext() as ctx:
        ctx.prec = 90
        for index, expected in enumerate(reference["rows"]):
            is_scale = index == len(inputs["points"])
            actual = producer[scale_record if is_scale else args.record]
            lane = 0 if is_scale else index
            assert all(status == "success" for _, status in actual["statuses"][lane])
            components = {
                "born": compare(
                    [real_pair(actual["born"][lane])],
                    [Decimal(str(expected["born"][born_id]))],
                )
            }
            for key, reference_key in COMPONENTS:
                components[key] = compare(
                    [real_pair(value) for value in actual[key][lane]],
                    [
                        Decimal(str(expected[reference_key][loop_id][power]))
                        for power in EPSILON
                    ],
                )
            rows.append(
                {
                    "index": index,
                    "mu_r2": expected_scales[index],
                    "components": components,
                }
            )
    failures = [
        {"point": row["index"], "component": name, **result}
        for row in rows
        for name, result in row["components"].items()
        if not result["passed"]
    ]
    report = {
        "scope": (
            "Full-colour model-rule scalar-QCD u ubar -> sig8 sig8 g against "
            "the unchanged binary64 MadLoop reference; no performance or "
            "independent high-precision oracle claim"
        ),
        "record": args.record,
        "scale_record": scale_record,
        "carrier": producer.get("carriers", {}).get(args.record),
        "epsilon_powers": [0, -1, -2],
        "target_component_normalized_error": str(TARGET),
        "near_zero_floor": str(FLOOR),
        "normalization": (
            "physical couplings, Cepsilon=(4pi)^epsilon/Gamma(1-epsilon); "
            "initial divisor36 and identical-pair divisor2"
        ),
        "native_counts": producer["counts"],
        "native_orders": producer["orders"],
        "max_component_normalized_error": str(
            max(
                Decimal(error)
                for row in rows
                for result in row["components"].values()
                for error in result["normalized_errors"]
            )
        ),
        "passed": not failures,
        "failures": failures,
        "rows": rows,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("passed", "max_component_normalized_error", "failures")
            },
            indent=2,
        ),
        flush=True,
    )
    assert not failures, (
        "complete scalar-QCD comparison failed; diagnostic record preserved"
    )
    print("SGLUON_QCD_ORDINARY_COMPONENT_GATE_PASS", flush=True)


if __name__ == "__main__":
    main()
