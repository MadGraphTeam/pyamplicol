# SPDX-License-Identifier: 0BSD
"""Small native code-generation regressions; no physics process is rebuilt."""

import ctypes
import shutil
import sys
import tempfile
import unittest
from decimal import Decimal, localcontext
from pathlib import Path
from types import SimpleNamespace

from pyamplicol.api.errors import CompatibilityError
from pyamplicol.runtime.native_rescue import compile_correlated_rescue


class Constant:
    def evaluate(self, *unused, **options):
        return SimpleNamespace(real=Decimal(1) / Decimal(3), imag=Decimal(0))


@unittest.skipUnless(
    sys.platform.startswith("linux") and shutil.which("g++"),
    "binary128 companions require GCC and quadmath",
)
class NativeRescueTests(unittest.TestCase):
    def runtime(self, unsupported=False):
        instructions = [
            ("add", ("temp", 0), [("param", 0), ("param", 1)], 2),
            ("mul", ("temp", 1), [("param", 0), ("const", 0)], 2),
            ("add", ("out", 0), [("temp", 0), ("temp", 1)], 2),
        ]
        if unsupported:
            instructions.append(("goto", 0))
        program = SimpleNamespace(
            instructions=instructions,
            temporary_count=2,
            constants=[Constant()],
            output_count=1,
            sub_evaluators=[],
        )
        evaluator = SimpleNamespace(
            chunks=(), evaluator=SimpleNamespace(get_instructions=lambda: program)
        )
        stage = dict(
            parameter_count=2,
            output_length=1,
            output_slots=[
                dict(output_start=0, output_stop=1, component_start=0, component_stop=1)
            ],
        )
        schema = dict(
            parameter_layout=dict(
                parameter_count_if_flattened=2,
                value_component_count=2,
                momentum_parameter_count=0,
                model_parameter_count=0,
            ),
            model_parameters=[],
            external_particles=[],
            momentum_slots=[],
        )
        executor = SimpleNamespace(
            _load_evaluators=lambda: None,
            _stage_evaluators=(),
            _amplitude_evaluator=evaluator,
            _execution=dict(
                runtime_schema=schema,
                compiled=dict(stage_evaluators=dict(stages=[], amplitude_stage=stage)),
            ),
        )
        return SimpleNamespace(
            artifact_id="fixture-only",
            _correlator_evaluator=lambda: SimpleNamespace(_executor=executor),
        )

    def test_native_kernel_keeps_sub_binary64_terms(self):
        with tempfile.TemporaryDirectory() as directory, localcontext() as context:
            context.prec = 80
            destination = Path(directory) / "kernel.so"
            compile_correlated_rescue(self.runtime(), destination)
            native = ctypes.CDLL(str(destination))
            pointer = ctypes.POINTER(ctypes.c_double)
            native.rusticol_rescue_evaluate.argtypes = [pointer, pointer, pointer]
            inputs = (ctypes.c_double * 4)(3.0, 0.0, -3.0, 0.0)
            output = (ctypes.c_double * 4)()
            self.assertEqual(native.rusticol_rescue_evaluate(inputs, None, output), 0)
            value = Decimal.from_float(output[0]) + Decimal.from_float(output[1])
            self.assertLess(abs(value - 1), Decimal("1e-30"))
            inputs[0], inputs[2] = 1e16, 1.0
            self.assertEqual(native.rusticol_rescue_evaluate(inputs, None, output), 0)
            value = Decimal.from_float(output[0]) + Decimal.from_float(output[1])
            self.assertLess(
                abs(value - (Decimal("1e16") * 4 / 3 + 1)), Decimal("1e-15")
            )

    def test_unsupported_program_cannot_replace_a_kernel(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "kernel.so"
            destination.write_bytes(b"prior kernel")
            with self.assertRaises(CompatibilityError):
                compile_correlated_rescue(self.runtime(unsupported=True), destination)
            self.assertEqual(destination.read_bytes(), b"prior kernel")
