# SPDX-License-Identifier: 0BSD
"""Specialisation guards: construction, the exact binding rule, the one-loop
checks, the compiled-model record and the chiral-selection producer."""

from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

import pytest

pytest.importorskip("symbolica")

from symbolica import E

from pyamplicol.models.specialization_guards import (
    GuardEnvironment,
    SpecializationGuard,
    admit_loop_specialization_guards,
    binding_refusal,
    exact_decimal_binding_refusal,
    guard_file_payload,
    guards_for_process,
    guards_from_file_payload,
)


def _environment() -> GuardEnvironment:
    # MT, MZ and aEWM1 mutable (declared real); CKM complex; ee derived.
    return GuardEnvironment(
        externals={
            "MT": 173.0 + 0j,
            "aEWM1": 132.507 + 0j,
            "MZ": 91.188 + 0j,
            "CKM": 0.97 + 0.25j,
        },
        definitions={"ee": E("2*UFO::aEWM1^(-1/2)*UFO::pi^(1/2)")},
        constants={"ZERO": 0j, "pi": math.pi, "I": 1j},
        real_externals=frozenset({"MT", "aEWM1", "MZ"}),
    )


def _vanishing(expression: str) -> SpecializationGuard | None:
    return SpecializationGuard.vanishing(
        _environment(),
        expression,
        subject="coupling GC_X removed by restriction simplification",
        producer="restriction-simplification",
        message="generate the artifact at the new values",
    )


def test_a_sixth_power_zero_refuses_any_other_value() -> None:
    # At MT = 174 the factor (MT - 173)^6 is exactly 1: an ordinary coupling.
    guard = _vanishing("(UFO::MT-173)^6*UFO::ee*UFO::complex(0,1)")
    assert guard is not None
    assert guard.parameters == ("MT",)  # the zero factor's parameters only
    assert guard.generation_values == {"MT": (173.0, 0.0)}
    refusal = binding_refusal([guard], {"MT": 174.0})
    assert refusal is not None
    assert refusal.startswith(
        "specialisation-guard: binding MT invalidates a vanishing"
    )
    assert "MT = 174.0 (generated at 173.0)" in refusal
    assert "coupling GC_X removed by restriction simplification" in refusal
    # The smallest change is refused; exactly the generation value is not.
    assert binding_refusal([guard], {"MT": math.nextafter(173.0, 200.0)})
    assert binding_refusal([guard], {"MT": 173.0}) is None
    # The other factor's parameters stay free (the product stays zero).
    assert binding_refusal([guard], {"aEWM1": 128.0, "MZ": 91.0}) is None


def test_a_product_of_several_inputs_holds_its_zero_factor() -> None:
    guard = _vanishing("(UFO::MT-173)^3*(UFO::MZ-91.188)*UFO::aEWM1*UFO::MZ")
    assert guard is not None
    assert len(guard.parameters) == 1
    held = guard.parameters[0]
    assert held in {"MT", "MZ"}
    value = {"MT": 174.0, "MZ": 91.0}[held]
    assert binding_refusal([guard], {held: value}) is not None
    assert binding_refusal([guard], {"aEWM1": 1.0}) is None


def test_a_zero_without_a_zero_factor_holds_every_input() -> None:
    # Zero only where both terms cancel: no factor vanishes on its own.
    guard = _vanishing("(UFO::MT-173)+(UFO::MZ-91.188)")
    assert guard is not None
    assert guard.parameters == ("MT", "MZ")
    # A change that keeps the sum zero is refused too: no cancellation is
    # accepted numerically.
    assert binding_refusal([guard], {"MT": 174.0, "MZ": 90.188}) is not None


def test_structural_specialisations_record_nothing() -> None:
    environment = _environment()
    assert _vanishing("UFO::ZERO*UFO::MT") is None
    assert _vanishing("UFO::MT-UFO::MT") is None
    assert _vanishing("UFO::complex(0,1)*UFO::MT-UFO::MT*UFO::complex(0,1)") is None
    assert _vanishing("3-3") is None

    def real(expression: str) -> SpecializationGuard | None:
        return SpecializationGuard.real(
            environment, expression, subject="s", producer="p", message="m"
        )

    assert real("UFO::MT^2*UFO::aEWM1") is None
    assert real("UFO::complex(0,1)^2*UFO::MT") is None
    # A square root of a real parameter, or a complex-declared external, is
    # not real for every binding: recorded, holding its inputs.
    root = real("UFO::ee")
    assert root is not None and root.parameters == ("aEWM1",)
    assert binding_refusal([root], {"aEWM1": 132.507}) is None
    assert binding_refusal([root], {"aEWM1": 130.0}) is not None
    assert real("UFO::CKM*UFO::MT") is not None


def test_both_components_of_a_complex_parameter_are_held() -> None:
    guard = _vanishing("(UFO::CKM-0.97-0.25*UFO::complex(0,1))*UFO::MT")
    assert guard is not None and guard.parameters == ("CKM",)
    assert binding_refusal([guard], {"CKM": 0.97 + 0.25j}) is None
    assert binding_refusal([guard], {"CKM": 0.97 + 0.0j}) is not None
    assert binding_refusal([guard], {"CKM": 0.97 + 0.26j}) is not None


def test_a_refused_change_and_a_return_to_the_generation_value() -> None:
    guard = _vanishing("(UFO::MT-173)*UFO::ee")
    assert binding_refusal([guard], {"MT": 174.0}) is not None
    # A refused binding applies nothing; binding the generation value later
    # is accepted.
    assert binding_refusal([guard], {"MT": 173.0}) is None


def test_the_loop_runtime_compares_exact_decimals() -> None:
    guard = _vanishing("(UFO::MT-173)*UFO::ee")
    assert exact_decimal_binding_refusal([guard], {"MT": "173"}) is None
    assert exact_decimal_binding_refusal([guard], {"MT": "173.000"}) is None
    assert exact_decimal_binding_refusal([guard], {"MT": Fraction(173)}) is None
    # Equal in binary64, different as bound: refused.
    close = "173.00000000000000000001"
    assert float(close) == 173.0
    assert exact_decimal_binding_refusal([guard], {"MT": close}) is not None
    assert exact_decimal_binding_refusal([guard], {"MT": "174"}) is not None
    # The generation value as exact carriers read it is the shortest decimal
    # of the binary64 (91.188, as a card gives it), not the binary64 itself.
    from pyamplicol.models.specialization_guards import exact_generation_value

    assert exact_generation_value(91.188) == Fraction(22797, 250)
    tenth = _vanishing("(UFO::MZ-91.188)*UFO::ee")
    assert tenth is not None and tenth.parameters == ("MZ",)
    assert exact_decimal_binding_refusal([tenth], {"MZ": "91.188"}) is None
    assert exact_decimal_binding_refusal([tenth], {"MZ": 91.188}) is None
    assert exact_decimal_binding_refusal([tenth], {"MZ": Fraction(91.188)}) is not None


def test_a_zero_only_in_binary64_is_refused_at_generation() -> None:
    from pyamplicol.models.specialization_guards import InexactSpecialization

    # A term the producer found zero in binary64 (91.188 - 22797/250 - 1e-30
    # rounds to zero) that is not exactly zero at the decimal 91.188 exact
    # carriers evaluate.
    with pytest.raises(InexactSpecialization, match="simplify=False"):
        _vanishing("(UFO::MZ-22797/250-1/10^30)*UFO::ee")
    # A binary64 literal is read as its shortest decimal, as a card value is.
    literal = str(Decimal.from_float(91.188))
    guard = _vanishing(f"(UFO::MZ-{literal})*UFO::ee")
    assert guard is not None and guard.parameters == ("MZ",)


def test_a_loop_plan_that_fixes_or_scales_a_guarded_parameter_is_refused() -> None:
    guard = _vanishing("(UFO::MT-173)*UFO::ee")
    admit_loop_specialization_guards([guard], {"MT": "173"}, "MU_R")
    admit_loop_specialization_guards([guard], {"aEWM1": "128"}, None)
    with pytest.raises(ValueError, match="a fixed parameter of the plan"):
        admit_loop_specialization_guards([guard], {"MT": "174"}, None)
    with pytest.raises(ValueError, match="renormalisation-scale"):
        admit_loop_specialization_guards([guard], {}, "MT")


def test_the_loop_runtime_refuses_a_binding_a_guard_rejects() -> None:
    from pyamplicol.loops.v2.artifact import V2VirtualRuntime

    runtime = SimpleNamespace(
        _externals={"MT", "aEWM1", "MZ"},
        _scale_parameter=None,
        _fixed={},
        _prepared_fixed=frozenset(),
        _specialization_guards=(_vanishing("(UFO::MT-173)*UFO::ee"),),
        _parameters={},
    )
    checked = V2VirtualRuntime._checked_parameters(runtime, {"aEWM1": "128"})
    assert checked == {"aEWM1": "128"}
    assert V2VirtualRuntime._checked_parameters(runtime, {"MT": "173"})
    with pytest.raises(ValueError, match="specialisation-guard: binding MT"):
        V2VirtualRuntime._checked_parameters(runtime, {"MT": "174"})


def test_guard_records_round_trip_and_select_their_processes() -> None:
    guard = _vanishing("(UFO::MT-173)*UFO::ee")
    assert guard is not None
    scoped = guard.for_processes(("p2", "p1"))
    payload = guard_file_payload([guard, scoped])
    assert "program" not in payload["guards"][0]
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
    # The built-in SM runs no restriction simplification: no record field,
    # so its compiled model and prepared packs are unchanged.
    assert "specialization_record" not in plain
    guarded = replace(
        compiled, specialization_guards=(_vanishing("(UFO::MT-173)*UFO::ee"),)
    )
    payload = guarded.to_dict()
    assert payload["schema_version"] == GUARDED_COMPILED_MODEL_SCHEMA_VERSION
    restored = CompiledModel.from_dict(payload, validate_fingerprint=False)
    assert restored.specialization_guards == guarded.specialization_guards
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


def test_generation_refuses_a_simplified_model_without_its_record(tmp_path) -> None:
    from dataclasses import replace

    from pyamplicol.models.loading import (
        SPECIALIZATION_RECORD,
        CompiledModel,
        compile_model_source,
        require_specialization_record,
    )

    builtin = compile_model_source("built-in-sm", cache_dir=tmp_path)
    assert require_specialization_record(builtin) is builtin

    def as_source(kind: str, simplify: bool, record: bool) -> CompiledModel:
        source = dict(builtin.source)
        source["kind"] = kind
        source["options"] = {**dict(source.get("options", {})), "simplify": simplify}
        return replace(builtin, source=source, specialization_record=record)

    # A UFO or JSON model simplified without the record (written before it
    # existed) is refused; with it, or unsimplified, or built in, it is not.
    for kind in ("ufo", "json"):
        with pytest.raises(ValueError, match="prepare or compile the model again"):
            require_specialization_record(as_source(kind, True, False))
        require_specialization_record(as_source(kind, True, True))
        require_specialization_record(as_source(kind, False, False))
    marked = as_source("ufo", True, True).to_dict()
    assert marked["specialization_record"] == SPECIALIZATION_RECORD
    restored = CompiledModel.from_dict(marked, validate_fingerprint=False)
    assert restored.specialization_record
    legacy = {
        key: value for key, value in marked.items() if key != "specialization_record"
    }
    assert not CompiledModel.from_dict(
        legacy, validate_fingerprint=False
    ).specialization_record


def test_chiral_guards_follow_the_selection_that_dropped_a_current() -> None:
    from pyamplicol.generation.contracts import (
        runtime_coupling_component_guards,
        zero_coupling_decisions,
    )
    from pyamplicol.models.builtin.model import BuiltinSMModel

    model = BuiltinSMModel()
    vertices = {(v.kind, tuple(v.particles)): v for v in model.vertices}
    # Massless leptons on both sides of the W: the right-handed zero dropped
    # the right-handed currents.
    massive = vertices[(21, (5, -6, -24))]
    assert massive.coupling[1] == 0.0
    # A Dirac top keeps both chiralities while any component is nonzero: the
    # zero right-handed component dropped nothing.
    assert zero_coupling_decisions(model, massive) == frozenset()
    leptonic_vertices = [
        v
        for (kind, particles), v in vertices.items()
        if kind in {21, 22}
        and all(abs(p) in {11, 12, 24} for p in particles)
        and 0.0 in v.coupling
    ]
    assert leptonic_vertices
    assert all(zero_coupling_decisions(model, v) for v in leptonic_vertices)

    def record(vertex, component: int) -> dict[str, object]:
        particles = "_".join(str(p) for p in vertex.particles)
        return {
            "name": f"coupling.{vertex.kind}.{particles}.component_{component}",
            "default": float(vertex.coupling[component]),
        }

    lepton = leptonic_vertices[0]
    zero = lepton.coupling.index(0.0)
    guards = runtime_coupling_component_guards(
        model,
        [record(lepton, zero), record(lepton, 1 - zero), record(massive, 1)],
    )
    assert [guard.parameters for guard in guards] == [(record(lepton, zero)["name"],)]
    (guard,) = guards
    assert binding_refusal([guard], {guard.parameters[0]: 0.0}) is None
    assert binding_refusal([guard], {guard.parameters[0]: 1.5}) is not None
    # A model without a chirality selection records nothing.
    assert (
        runtime_coupling_component_guards(SimpleNamespace(), [record(lepton, zero)])
        == ()
    )
