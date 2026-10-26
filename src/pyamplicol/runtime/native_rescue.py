# SPDX-License-Identifier: 0BSD
"""Preparation-only binary128 current kernels; numerical execution is Symbolica-free."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from pyamplicol.api.errors import CompatibilityError
from pyamplicol.evaluators.symbolica_helpers import _symbolica_instruction_program
from pyamplicol.runtime.symbolica_exact import (
    _assign_stage_outputs,
    _canonical_amplitude_outputs,
    _pack_stage_inputs,
)

if TYPE_CHECKING:
    from pyamplicol.api.services import Runtime


def compile_correlated_rescue(
    runtime: Runtime, destination: os.PathLike[str] | str, *, compiler: str = "g++"
) -> Path:
    """Compile the retained complete current/amplitude plan, not new physics.

    Sources and mutable model inputs retain the native binary64 contract.
    Internal momenta, currents and amplitudes execute in GCC binary128.
    The SDK receives twofold amplitudes and applies its ordinary colour matrices.
    """
    executor: Any = runtime._correlator_evaluator()._executor
    executor._load_evaluators()
    execution = executor._execution
    schema = execution["runtime_schema"]
    layout = schema["parameter_layout"]
    state_size = max(
        layout["parameter_count_if_flattened"],
        layout["value_component_count"]
        + layout["momentum_parameter_count"]
        + layout["model_parameter_count"],
    )
    stages = execution["compiled"]["stage_evaluators"]
    helpers: list[str] = []
    statements: list[str] = []

    def emit(evaluator: Any, inputs: Any) -> list[str]:
        if evaluator.chunks:
            return [
                value
                for child, indices in zip(
                    evaluator.chunks, evaluator.chunk_input_indices, strict=True
                )
                for value in emit(child, [inputs[i] for i in indices])
            ]
        instructions, temporary_count, constants = _symbolica_instruction_program(
            evaluator.evaluator.get_instructions()
        )
        identifier = len(helpers)
        name = f"leaf_{identifier}"
        # Reserve the ID before emitting the body (each leaf has one definition).
        helpers.append("")
        exported = evaluator.evaluator.get_instructions()
        output_count = exported.output_count
        values = [value.evaluate({}, decimal_digit_precision=80) for value in constants]
        body = [
            f"static std::vector<C> {name}(const std::vector<C>& p) {{",
            "static const std::vector<C> c={{{}}};".format(
                ",".join(
                    f"q(strtoflt128({json.dumps(str(value.real))},nullptr),"
                    f"strtoflt128({json.dumps(str(value.imag))},nullptr))"
                    for value in values
                )
            ),
            f"std::vector<C> t({temporary_count}),o({output_count});",
        ]
        written = set()

        def ref(slot: Any, destination: bool = False) -> str:
            kind, index = slot
            sizes = dict(
                param=len(inputs),
                temp=temporary_count,
                const=len(constants),
                out=output_count,
            )
            if (
                kind not in sizes
                or not isinstance(index, int)
                or not 0 <= index < sizes[kind]
            ):
                raise CompatibilityError("Invalid rescue instruction reference")
            if destination and kind not in ("temp", "out"):
                raise CompatibilityError("Invalid rescue instruction destination")
            if (
                not destination
                and kind in ("temp", "out")
                and (kind, index) not in written
            ):
                raise CompatibilityError("Uninitialized rescue instruction reference")
            array = dict(param="p", temp="t", const="c", out="o")[kind]
            return f"{array}[{index}]"

        for instruction in instructions:
            op = instruction[0]
            if op not in ("add", "mul", "pow", "assign", "fun"):
                raise CompatibilityError(
                    "Unsupported native rescue instruction: " + repr(instruction)
                )
            target = ref(instruction[1], True)
            if op in ("add", "mul") and len(instruction) == 4:
                operands = [ref(slot) for slot in instruction[2]]
                expression = ("+" if op == "add" else "*").join(operands)
                if not expression:
                    raise CompatibilityError("Empty rescue arithmetic instruction")
            elif op == "pow" and len(instruction) == 5:
                exponent = instruction[3]
                if type(exponent) is not int or abs(exponent) >= 2**63:
                    raise CompatibilityError("Unsupported rescue integer exponent")
                expression = f"power({ref(instruction[2])},{exponent}LL)"
            elif op == "assign" and len(instruction) == 3:
                expression = ref(instruction[2])
            elif op == "fun" and len(instruction) == 6 and not instruction[3]:
                function_name = str(instruction[2]).split("::")[-1]
                functions = dict(
                    conj="conjq",
                    sqrt="csqrtq",
                    exp="cexpq",
                    log="clogq",
                    sin="csinq",
                    cos="ccosq",
                )
                if function_name not in functions or len(instruction[4]) != 1:
                    raise CompatibilityError(
                        "Unsupported native rescue function: " + repr(instruction)
                    )
                expression = f"{functions[function_name]}({ref(instruction[4][0])})"
            else:
                raise CompatibilityError(
                    "Unsupported native rescue instruction: " + repr(instruction)
                )
            body.append(target + "=" + expression + ";")
            written.add(tuple(instruction[1]))
        if any(("out", i) not in written for i in range(output_count)):
            raise CompatibilityError("Incomplete native rescue outputs")
        body.extend(["return o;", "}"])
        helpers[identifier] = "\n".join(body)
        variable = f"v{identifier}"
        statements.append(f"auto {variable}={name}({{{','.join(inputs)}}});")
        return [f"{variable}[{i}]" for i in range(output_count)]

    state: Any = [f"s[{i}]" for i in range(state_size)]
    for stage, evaluator in zip(
        stages["stages"], executor._stage_evaluators, strict=True
    ):
        outputs = emit(evaluator, _pack_stage_inputs(state, stage))
        updated: Any = list(state)
        # These layout-only helpers also apply to symbolic C++ expressions.
        _assign_stage_outputs(updated, cast(Any, outputs), stage)
        statements.extend(
            f"s[{i}]={value};" for i, value in enumerate(updated) if value != state[i]
        )
    amplitude = stages["amplitude_stage"]
    canonical: Any = _canonical_amplitude_outputs(
        emit(executor._amplitude_evaluator, _pack_stage_inputs(state, amplitude)),
        amplitude,
    )
    momentum = []
    initial = {
        particle["label"]
        for particle in schema["external_particles"]
        if particle["role"] == "initial"
    }
    for slot in schema["momentum_slots"]:
        for component in range(4):
            expression = "+".join(
                ("-" if leg in initial else "") + f"R(p[{4 * (leg - 1) + component}])"
                for leg in slot["external_labels"]
            )
            index = (
                layout["value_component_count"] + slot["component_start"] + component
            )
            momentum.append(f"s[{index}]=q({expression or '0'},0);")
    source = (
        r"""
#include <quadmath.h>
#include <vector>
#include <cmath>
using R=__float128;
using C=__complex128;
static C q(R real,R imag) {
    C value; __real__ value=real; __imag__ value=imag; return value;
}
static C power(C base,long long exponent) {
    bool inverse=exponent<0;
    unsigned long long n=inverse ? -exponent : exponent;
    C result=q(1,0);
    while(n) { if(n&1) result*=base; n>>=1; if(n) base*=base; }
    return inverse ? q(1,0)/result : result;
}
"""
        + "\n".join(helpers)
        + r"""
extern "C" const char* rusticol_rescue_artifact_id() { return ARTIFACT; }
extern "C" unsigned long long rusticol_rescue_state_size() { return STATE_SIZE; }
extern "C" unsigned long long rusticol_rescue_output_size() { return OUTPUT_SIZE; }
extern "C" int rusticol_rescue_evaluate(
    const double* input,const double* p,double* output) {
    try {
        std::vector<C> s(STATE_SIZE);
        for(unsigned long long i=0;i<STATE_SIZE;++i) s[i]=q(input[2*i],input[2*i+1]);
        MOMENTA
        STATEMENTS
        OUTPUTS
        return 0;
    } catch(...) { return 1; }
}
"""
    )
    serialized = []
    for i, value in enumerate(canonical):
        for component, part in enumerate(("__real__", "__imag__")):
            offset = 4 * i + 2 * component
            serialized.append(
                f"{{ R x={part} {value}; double hi=double(x); "
                f"output[{offset}]=hi; output[{offset + 1}]=double(x-R(hi)); }}"
            )
    for token, replacement in dict(
        ARTIFACT=json.dumps(runtime.artifact_id),
        STATE_SIZE=str(state_size),
        OUTPUT_SIZE=str(len(canonical)),
        MOMENTA="\n".join(momentum),
        STATEMENTS="\n".join(statements),
        OUTPUTS="\n".join(serialized),
    ).items():
        source = source.replace(token, replacement)
    destination = Path(destination).resolve()
    source_path = destination.with_suffix(".cc")
    source_path.write_text(source)
    # A failed rebuild must not truncate a previously usable companion.
    with tempfile.TemporaryDirectory(
        prefix=".native-rescue-", dir=destination.parent
    ) as temporary:
        library = Path(temporary) / "rescue.so"
        subprocess.run(
            [
                compiler,
                "-std=c++17",
                "-O2",
                "-fPIC",
                "-shared",
                str(source_path),
                "-lquadmath",
                "-o",
                str(library),
            ],
            check=True,
        )
        library.replace(destination)
    return destination
