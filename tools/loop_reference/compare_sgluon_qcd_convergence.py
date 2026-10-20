# SPDX-License-Identifier: 0BSD
"""Read-only component-local convergence of genuine saved arithmetic views.

AP80 is an internal precision reference. Independent physics agreement is
checked separately against the binary64 fixture with compare_sgluon_qcd.py.
"""

import argparse
import json
from decimal import Decimal, localcontext
from pathlib import Path

from compare_sgluon_qcd import COMPONENTS, DEFAULT_REFERENCE

COMPARISONS = (
    ("double_double", "ap80", Decimal("1e-25")),
    ("ap60", "ap80", Decimal("1e-50")),
)
NAMES = ("born", *(name for name, _ in COMPONENTS))


def components(record, name, lane):
    values = [record[name][lane]] if name == "born" else record[name][lane]
    assert len(values) == (1 if name == "born" else 3)
    result = []
    for pair in values:
        assert len(pair) == 2
        for value in pair:
            scalar = Decimal(str(value))
            assert scalar.is_finite()
            result.append(scalar)
    return result


def require_complete(record, ids, families):
    assert record["point_ids"] == record["requested_point_ids"] == ids
    assert not record["failures"]
    assert len(record["statuses"]) == len(ids)
    for identity, statuses in zip(ids, record["statuses"], strict=True):
        assert len(statuses) == families
        assert all(
            lane == identity and status == "success" for lane, status in statuses
        )
    assert all(len(record[name]) == len(ids) for name in NAMES)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    args = parser.parse_args()
    producer = json.loads(args.producer.read_text())
    inputs = json.loads(args.reference.read_text())["inputs"]
    assert not producer.get("higher_failure"), producer.get("higher_failure")
    assert any(
        stage["name"] == "HIGHER_OUTPUTS_READY_FOR_INDEPENDENT_COMPARISON"
        for stage in producer["higher_stages"]
    ), "genuine higher-carrier execution is not complete"
    for name, arithmetic, precision in (
        ("double_double", "double-double", None),
        ("ap60", "arbitrary", 60),
        ("ap80", "arbitrary", 80),
    ):
        info = producer["carriers"][name]
        assert info["arithmetic"] == arithmetic
        assert info["requested_decimal_precision"] == precision
        assert info["reduction_engine"] == "generic"
    assert (
        producer["carriers"]["ap80"]["precision_bits"]
        > producer["carriers"]["ap60"]["precision_bits"]
    )
    rows = []
    with localcontext() as context:
        context.prec = 160
        for actual_name, reference_name, threshold in COMPARISONS:
            for suffix, ids in (
                ("", list(range(len(inputs["points"])))),
                ("_scale", [0]),
            ):
                actual = producer[actual_name + suffix]
                reference = producer[reference_name + suffix]
                for record in (actual, reference):
                    require_complete(record, ids, producer["counts"]["families"])
                for lane, point_id in enumerate(ids):
                    for name in NAMES:
                        a = components(actual, name, lane)
                        b = components(reference, name, lane)
                        norm = max(*map(abs, a), *map(abs, b))
                        absolute = [abs(x - y) for x, y in zip(a, b, strict=True)]
                        errors = (
                            [value / norm for value in absolute]
                            if norm != 0
                            else [Decimal(0)] * len(absolute)
                        )
                        rows.append(
                            {
                                "record": actual_name + suffix,
                                "reference": reference_name + suffix,
                                "point_id": point_id,
                                "component": name,
                                "actual": list(map(str, a)),
                                "reference_values": list(map(str, b)),
                                "component_norm": str(norm),
                                "both_exact_zero": norm == 0,
                                "absolute_errors": list(map(str, absolute)),
                                "normalized_errors": list(map(str, errors)),
                                "threshold": str(threshold),
                                "passed": max(errors) <= threshold,
                            }
                        )
    failures = [row for row in rows if not row["passed"]]
    report = {
        "scope": (
            "Internal convergence of actual generic DD/AP60/AP80 saved executions "
            "at identical inputs; AP80 is not an independent physics reference"
        ),
        "producer": str(args.producer),
        "norm": (
            "Maximum magnitude of both real/imaginary values in the same "
            "component across finite/single/double poles; Born uses its own "
            "complex value. No unit floor or Born normalization."
        ),
        "zero_policy": (
            "Two exactly zero components have zero error. If only one is zero, "
            "the nonzero component sets the norm and remains testable."
        ),
        "carriers": producer["carriers"],
        "comparisons": {
            name: {
                "reference": reference,
                "threshold": str(threshold),
                "max_component_normalized_error": str(
                    max(
                        Decimal(error)
                        for row in rows
                        if row["record"] in (name, name + "_scale")
                        for error in row["normalized_errors"]
                    )
                ),
            }
            for name, reference, threshold in COMPARISONS
        },
        "passed": not failures,
        "failures": failures,
        "rows": rows,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {key: report[key] for key in ("passed", "comparisons", "failures")},
            indent=2,
        ),
        flush=True,
    )
    assert not failures, "internal convergence failed; component errors preserved"
    print("SGLUON_QCD_HIGHER_CARRIER_CONVERGENCE_PASS", flush=True)


if __name__ == "__main__":
    main()
