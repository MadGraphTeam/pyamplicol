# SPDX-License-Identifier: 0BSD
"""Compare source-derived quark/gluon external-field factors to isolated MadLoop.

The Born values are inputs from the independent reference, so this validates
field normalization/multiplicity and scalar evaluation, not a full amplitude.
Native batch arithmetic and the reference comparison use binary64 here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from symbolica import Expression, S
from symbolica.community import hepkit as hep

from pyamplicol.loops.graphs import build_loop_process
from pyamplicol.loops.model import build_loop_model
from pyamplicol.loops.model_expressions import parse_exact_ufo
from pyamplicol.loops.wavefunction import match_external_field_counterterms
from pyamplicol.models.loop_import import load_raw_loop_model


def external_field_oracle(ufo: Path, reference: Path) -> dict:
    control = json.loads(reference.read_text())
    process = control["fixture"]["process"]
    if process == "u u~ > t t~":
        incoming, outgoing, expected_born, expected_fields = (
            ["u", "u~"],
            ["t", "t~"],
            1,
            2,
        )
    elif process == "g g > g g":
        incoming, outgoing, expected_born, expected_fields = (
            ["g", "g"],
            ["g", "g"],
            4,
            12,
        )
    else:
        raise ValueError("external-field control requires the top or gluon fixture")
    source = build_loop_model(load_raw_loop_model(ufo))
    native = hep.Model.qcd_qed()
    loops = build_loop_process(
        native.process(incoming, outgoing),
        selected_corrections=["QCD"],
        perturbative_orders={"QCD": 1},
        born_order_bounds={"QED": 0},
        loop_order_bounds={"QED": 0},
    )
    fields = match_external_field_counterterms(
        source, loops, selected_corrections=["QCD"]
    )
    per_born = [
        tuple(item for item in fields.insertions if item.born.id == graph.id)
        for graph in loops.born
    ]
    if len(per_born) != expected_born or any(
        len(items) != expected_fields for items in per_born
    ):
        raise ValueError("unexpected source field/Born multiplicity")
    # The reference Born includes all graph/basis interference. A common field
    # factor may multiply it only after proving identical ordered factors for
    # every Born graph; no graph is discarded from the physical amplitude.
    signatures = [
        sorted(
            (
                item.external_index,
                item.rule.pdg,
                item.rule.loop_group_index,
                item.alternative_index,
                tuple(item.coefficient(p).to_canonical_string() for p in (0, -1, -2)),
            )
            for item in items
        )
        for items in per_born
    ]
    if any(signature != signatures[0] for signature in signatures[1:]):
        raise ValueError("field factors are not universal across the Born graphs")
    factors = per_born[0]
    born = S("wavefunction_oracle::reference_born")
    expressions = []
    for power in (0, -1, -2):
        expression = 2 * born * sum(item.coefficient(power) for item in factors)
        expression = expression.replace(
            parse_exact_ufo("G"), parse_exact_ufo("cmath.sqrt(4*cmath.pi*alpha_s)")
        )
        expression = expression.replace(parse_exact_ufo("CF"), parse_exact_ufo("4/3"))
        expression = expression.replace(parse_exact_ufo("TF"), parse_exact_ufo("1/2"))
        expressions.append(expression)
    evaluator = Expression.evaluator_multiple(
        expressions,
        [born, *map(parse_exact_ufo, ("alpha_s", "MT", "MB", "MC", "MU_R"))],
        n_cores=1,
        jit_compile=False,
    )
    parameters = control["fixture"]["parameters"]
    inputs = np.asarray(
        [
            [
                row["born"],
                parameters["alpha_s"],
                parameters["mt"],
                parameters.get("mb", 0),
                parameters.get("mc", 0),
                parameters["mu"],
            ]
            for row in control["rows"]
        ],
        dtype=np.complex128,
    )
    actual = evaluator.evaluate_complex(inputs)
    expected = np.asarray(
        [
            [row["wf"][name] for name in ("finite", "single_pole", "double_pole")]
            for row in control["rows"]
        ]
    )
    errors = abs(actual - expected) / np.maximum(1.0, abs(expected))
    if float(errors.max()) > 5e-14:
        raise AssertionError(
            "source-derived field factors disagree with isolated MadLoop"
        )
    return {
        "kind": "external-field-source-factor-oracle",
        "process": process,
        "born_graph_count": len(loops.born),
        "total_source_field_records": len(fields.insertions),
        "reference": str(reference.resolve()),
        "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
        "born_values_from_reference": True,
        "native_and_reference_arithmetic": "binary64",
        "native_batch_size": len(inputs),
        "external_indices": [item.external_index for item in factors],
        "model_factors_per_born": len(factors),
        "extra_half_z_factor": False,
        "extra_loop_measure": False,
        "full_process_validated": False,
        "maximum_scaled_error": float(errors.max()),
        "computed_laurent": actual.real.tolist(),
        "exact_interference_expressions": [
            e.to_canonical_string() for e in expressions
        ],
    }


def top_pair_field_oracle(ufo: Path, reference: Path) -> dict:
    """Backward-compatible entry point; the fixture selects top or gluon fields."""
    return external_field_oracle(ufo, reference)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ufo", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = external_field_oracle(args.ufo, args.reference)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
