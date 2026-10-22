# SPDX-License-Identifier: 0BSD
"""Replay a saved scalar-QCD control with the normally installed native module.

The PACBIN and exact input fixture are explicit arguments. This tool never
generates graphs, changes dependencies, stages an extension or supplies a licence.
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Any

CARRIERS = {
    "double": ("double", None, "fast"),
    "double_double": ("double-double", None, "generic"),
    "ap60": ("arbitrary", 60, "generic"),
    "ap80": ("arbitrary", 80, "generic"),
}
BLOCKS = ("virtual", "bare", "uv", "r2", "uv_local", "uv_external_fields")
FAILURE_FIELDS = (
    "point_id", "helicity", "order_index", "family_index", "external_leg",
    "color_component_index", "history_index", "direction", "stage", "detail",
)


def complete_record(result: Any) -> dict[str, Any]:
    count = len(result.point_ids)
    born = result.born.to_decimal()
    assert len(born) == count, "the retained fixture has one Born order"
    record = {
        "point_ids": result.point_ids,
        "requested_point_ids": result.requested_point_ids,
        "statuses": result.statuses,
        "failures": [
            {name: getattr(failure, name) for name in FAILURE_FIELDS}
            for failure in result.failures
        ],
        "born": born,
    }
    for name, batch in zip(BLOCKS, result.component_batches, strict=True):
        values = batch.to_decimal()
        assert len(values) == count * 3, "the retained fixture has one virtual order"
        record[name] = [values[3 * lane:3 * lane + 3] for lane in range(count)]
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pacbin", type=Path, required=True)
    parser.add_argument(
        "--inputs", type=Path,
        default=Path(__file__).with_name("sgluon_qcd.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--carriers", nargs="+", choices=tuple(CARRIERS), default=list(CARRIERS),
        help="which retained validation cases to execute (default: all four)",
    )
    args = parser.parse_args()
    fixture = json.loads(args.inputs.read_text())
    inputs = fixture.get("inputs", fixture)

    # This is the ordinary package loader, including its native identity check.
    from pyamplicol import _rusticol
    from pyamplicol.loops.native import load_loop_native

    native = load_loop_native()
    runtime = native.NativeLoopProgram(
        str(args.pacbin), arithmetic="double", reduction_engine="fast",
        parameters={key: (value, "0") for key, value in inputs["parameters"].items()},
    )
    metadata = json.loads(runtime.metadata_json())
    orders = metadata["order_layout"]
    assert metadata["external_pdgs"] == inputs["pdgs"]
    assert len(orders["born"]) == len(orders["virtual"]) == 1
    original_overrides = runtime.source_state.snapshot().overrides
    report: dict[str, Any] = {
        "scope": "saved scalar-QCD control; reference comparison is separate",
        "pacbin": str(args.pacbin),
        "inputs": str(args.inputs),
        "native_digest": _rusticol.native_build_inputs_sha256(),
        "orders": {
            "corrections": orders["correction_names"],
            "born_squared": [value["order"] for value in orders["born"]],
            "virtual_squared": [value["order"] for value in orders["virtual"]],
        },
        "counts": {
            "born": len(metadata["born"]["representative_for"]),
            "loop": len(metadata["loops"]["representative_for"]),
            "families": len(metadata["families"]),
            "counterterm_currents": len(metadata["currents"]),
            "normalization_divisor": str(metadata["initial_average"]),
        },
        "source_overrides": original_overrides,
        "carriers": {},
        "higher_stages": [],
    }

    def stage(name: str, **details: Any) -> None:
        report["higher_stages"].append({"name": name, **details})
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(name, details, flush=True)

    try:
        ids = list(range(len(inputs["points"])))
        for name in args.carriers:
            arithmetic, precision, engine = CARRIERS[name]
            owner = runtime if name == "double" else runtime.rebind(
                arithmetic=arithmetic, precision=precision, reduction_engine=engine,
            )
            assert owner.arithmetic == arithmetic
            assert owner.metadata_json() == runtime.metadata_json()
            assert owner.source_state.snapshot().overrides == original_overrides
            report["carriers"][name] = {
                "arithmetic": owner.arithmetic,
                "requested_decimal_precision": precision,
                "precision_bits": owner.precision_bits,
                "reduction_engine": engine,
            }
            stage("SAVED_OWNER_BOUND", carrier=name)
            result = owner.evaluate(inputs["points"], inputs["mu_r2"], point_ids=ids)
            report[name] = complete_record(result)
            stage("COMPLETE_RETURNED", carrier=name)
            assert not result.failures and result.point_ids == ids
            result = owner.evaluate(
                [inputs["points"][inputs["changed_scale"]["point_index"]]],
                [inputs["changed_scale"]["mu_r2"]], point_ids=[0],
            )
            report[name + "_scale"] = complete_record(result)
            stage("CHANGED_SCALE_RETURNED", carrier=name)
            assert not result.failures and result.point_ids == [0]
        stage("HIGHER_OUTPUTS_READY_FOR_INDEPENDENT_COMPARISON")
    except BaseException as error:
        report["higher_failure"] = {
            "type": type(error).__name__, "message": str(error),
            "traceback": traceback.format_exc(),
        }
        stage("SAVED_REPLAY_FAILED")
        raise
    finally:
        assert runtime.source_state.snapshot().overrides == original_overrides
        args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
