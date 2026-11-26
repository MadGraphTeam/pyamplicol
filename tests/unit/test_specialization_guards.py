# SPDX-License-Identifier: 0BSD
"""Specialisation guards: construction, the binding test and serialisation."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

pytest.importorskip("symbolica")

from symbolica import E

from pyamplicol.models.specialization_guards import (
    TOLERANCE,
    GuardEnvironment,
    SpecializationGuard,
    binding_refusal,
    compile_program,
    evaluate_program,
    guard_file_payload,
    guards_for_process,
    guards_from_file_payload,
)


def _environment() -> GuardEnvironment:
    # MT and aEWM1 mutable; ee a derived parameter; ZERO a constant.
    return GuardEnvironment(
        externals={"MT": 173.0 + 0j, "aEWM1": 132.507 + 0j, "MZ": 91.188 + 0j},
        definitions={
            "ee": E("2*UFO::aEWM1^(-1/2)*UFO::pi^(1/2)"),
            "coupling": E("(UFO::MT-173)*UFO::ee*UFO::complex(0,1)"),
        },
        constants={"ZERO": 0j, "pi": math.pi, "I": 1j},
    )


def _vanishing() -> SpecializationGuard:
    guard = SpecializationGuard.vanishing(
        _environment(),
        "UFO::coupling",
        subject="coupling GC_X removed by restriction simplification",
        producer="restriction-simplification",
        message="generate the artifact at the new values",
    )
    assert guard is not None
    return guard


def test_a_binding_dependent_zero_records_its_mutable_parameters() -> None:
    guard = _vanishing()
    assert guard.kind == "vanishing"
    assert guard.parameters == ("MT", "aEWM1")
    assert guard.generation_values == {"MT": (173.0, 0.0), "aEWM1": (132.507, 0.0)}
    assert guard.program is not None
    assert guard.failure({}) is None


def test_structural_specialisations_record_nothing() -> None:
    environment = _environment()
    for expression in (
        "UFO::ZERO*UFO::MT",  # a parameter the card fixed to zero
        "UFO::MT-UFO::MT",  # identically zero
        "(UFO::MT+1)^2-UFO::MT^2-2*UFO::MT-1",  # zero once expanded
        "3*UFO::pi",  # no mutable dependence
    ):
        assert (
            SpecializationGuard.vanishing(
                environment, expression, subject="s", producer="p", message="m"
            )
            is None
        )
    assert (
        SpecializationGuard.real(
            environment, "UFO::pi*UFO::I", subject="s", producer="p", message="m"
        )
        is None
    )


def test_a_binding_that_revives_the_zero_is_refused_and_others_are_not() -> None:
    guard = _vanishing()
    refusal = binding_refusal([guard], {"MT": 174.0})
    assert refusal is not None
    assert refusal.startswith(
        "specialisation-guard: binding MT invalidates a vanishing"
    )
    assert "coupling GC_X removed by restriction simplification" in refusal
    assert "generate the artifact at the new values" in refusal
    for binding in ({"MT": 173.0}, {"aEWM1": 128.0}, {"MZ": 90.0}):
        assert binding_refusal([guard], binding) is None
    # The current values complete a binding: with MT already moved, an aEWM1
    # binding fails too.
    assert binding_refusal([guard], {"aEWM1": 128.0}, {"MT": 174.0}) is not None


def test_rounding_is_the_boundary_of_the_vanishing_test() -> None:
    guard = _vanishing()
    # |MT - 173| <= TOLERANCE (MT + 173): about 2.5e-12 at MT = 173.
    ulp = math.nextafter(173.0, math.inf) - 173.0
    assert binding_refusal([guard], {"MT": 173.0 + 8 * ulp}) is None
    assert TOLERANCE * 346 < 1e-9
    assert binding_refusal([guard], {"MT": 173.0 + 1e-9}) is not None


def test_the_real_kind_tests_the_imaginary_part_with_the_same_scale() -> None:
    environment = _environment()
    # Real at MT = 173 only: (1 + i (MT - 173)) ee.
    guard = SpecializationGuard.real(
        environment,
        "(1+UFO::complex(0,1)*(UFO::MT-173))*UFO::ee",
        subject="derived parameter GC_R stored with one component",
        producer="recurrence-template",
        message="regenerate",
    )
    assert guard is not None and guard.kind == "real"
    assert binding_refusal([guard], {"MT": 173.0}) is None
    assert binding_refusal([guard], {"aEWM1": 100.0}) is None
    ulp = math.nextafter(173.0, math.inf) - 173.0
    assert binding_refusal([guard], {"MT": 173.0 + 8 * ulp}) is None
    refusal = binding_refusal([guard], {"MT": 174.0})
    assert refusal is not None and "not real" in refusal


def test_a_real_guard_is_structural_where_every_binding_is_real() -> None:
    environment = GuardEnvironment(
        externals={"MT": 173.0 + 0j, "aS": 0.118 + 0j, "CKM": 1.0 + 0j},
        definitions={"G": E("2*UFO::aS^(1/2)*UFO::pi^(1/2)")},
        constants={"pi": math.pi, "I": 1j},
        real_externals=frozenset({"MT", "aS"}),
    )

    def real(expression: str) -> SpecializationGuard | None:
        return SpecializationGuard.real(
            environment, expression, subject="s", producer="p", message="m"
        )

    # Real for every real MT and aS: nothing to record.
    assert real("UFO::MT^2*UFO::aS") is None
    assert real("UFO::complex(0,1)^2*UFO::MT") is None
    # A square root of a real parameter, or a complex-declared external, is
    # real only on part of the domain: recorded, and refused outside it.
    root = real("UFO::G")
    assert root is not None and root.parameters == ("aS",)
    assert binding_refusal([root], {"aS": 0.12}) is None
    assert binding_refusal([root], {"aS": -0.12}) is not None
    assert real("UFO::CKM*UFO::MT") is not None


def test_programs_agree_with_symbolica() -> None:
    expression = E(
        "sqrt(x)*cos(y)+exp(x-y)^2/(1+x^2)+log(x)*conj(y)+x^(3/2)-tan(y)/sinh(x)"
    )
    resolved = expression.replace(E("x"), E("UFO::x")).replace(E("y"), E("UFO::y"))
    environment = GuardEnvironment({"x": 0.7 + 0j, "y": 1.3 + 0j}, {}, {})
    program = compile_program(resolved, ("x", "y"), environment)
    for x, y in ((0.7, 1.3), (2.5, -0.4), (11.0, 3.0)):
        value, bound = evaluate_program(program, (complex(x), complex(y)))
        reference = complex(resolved.evaluate({E("UFO::x"): x, E("UFO::y"): y}))
        assert abs(value - reference) <= 1e-13 * max(1.0, abs(reference))
        assert bound >= abs(value) * (1 - 1e-15)


def test_an_unrepresentable_function_holds_the_parameters_at_their_values() -> None:
    environment = GuardEnvironment({"MT": 173.0 + 0j}, {}, {})
    guard = SpecializationGuard.vanishing(
        environment,
        "UFO::Theta(UFO::MT-174)*UFO::MT",
        subject="s",
        producer="p",
        message="m",
    )
    assert guard is not None and guard.program is None
    assert binding_refusal([guard], {"MT": 173.0}) is None
    assert binding_refusal([guard], {"MT": 173.5}) is not None


def test_guard_records_round_trip_and_select_their_processes() -> None:
    guard = _vanishing()
    scoped = guard.for_processes(("p2", "p1"))
    payload = guard_file_payload([guard, scoped])
    restored = guards_from_file_payload(payload)
    assert restored == (guard, scoped)
    assert scoped.process_ids == ("p1", "p2")
    assert guards_for_process(restored, "p1") == (guard, scoped)
    assert guards_for_process(restored, "other") == (guard,)
    with pytest.raises(ValueError, match="specialisation-guard record"):
        guards_from_file_payload({**payload, "kind": "something-else"})


def test_a_guarded_compiled_model_uses_the_new_schema_and_only_then(
    tmp_path,
) -> None:
    from dataclasses import replace

    from pyamplicol.models.loading import (
        COMPILED_MODEL_SCHEMA_VERSION,
        GUARDED_COMPILED_MODEL_SCHEMA_VERSION,
        CompiledModel,
        compile_model_source,
    )

    compiled = compile_model_source("built-in-sm", cache_dir=tmp_path)
    assert compiled.specialization_guards == ()
    plain = compiled.to_dict()
    assert plain["schema_version"] == COMPILED_MODEL_SCHEMA_VERSION
    assert "specialization_guards" not in plain
    guarded = replace(compiled, specialization_guards=(_vanishing(),))
    payload = guarded.to_dict()
    assert payload["schema_version"] == GUARDED_COMPILED_MODEL_SCHEMA_VERSION
    restored = CompiledModel.from_dict(payload, validate_fingerprint=False)
    assert restored.specialization_guards == guarded.specialization_guards
    # A released reader requires the plain schema exactly; this one refuses a
    # mismatched pair.
    with pytest.raises(ValueError, match="schema"):
        CompiledModel.from_dict(
            {**payload, "schema_version": COMPILED_MODEL_SCHEMA_VERSION},
            validate_fingerprint=False,
        )
    with pytest.raises(ValueError, match="no specialisation guards"):
        CompiledModel.from_dict(
            {**plain, "schema_version": GUARDED_COMPILED_MODEL_SCHEMA_VERSION},
            validate_fingerprint=False,
        )


def test_the_loop_runtime_refuses_a_binding_a_guard_rejects() -> None:
    from pyamplicol.loops.v2.artifact import V2VirtualRuntime

    runtime = SimpleNamespace(
        _externals={"MT", "aEWM1", "MZ"},
        _scale_parameter=None,
        _fixed={},
        _prepared_fixed=frozenset(),
        _specialization_guards=(_vanishing(),),
        _parameters={},
    )
    checked = V2VirtualRuntime._checked_parameters(runtime, {"aEWM1": "128"})
    assert checked == {"aEWM1": "128"}
    with pytest.raises(ValueError, match="specialisation-guard: binding MT"):
        V2VirtualRuntime._checked_parameters(runtime, {"MT": "174"})
