# SPDX-License-Identifier: 0BSD
"""Whether a model's vertex support holds for every permitted parameter binding.

A UFO model decides which vertex rows exist with a probe
(``ExternalKernelMixin._weyl_projection_is_nonzero``). The probe substitutes
the current values of the runtime parameters into the projected kernel. A
vertex whose coupling vanishes at those values is dropped, even when the
coupling depends on a parameter that the artifact declares mutable (an
external parameter of the model; ``Runtime.set_model_parameters`` may change
it). A coupling proportional to ``MT - 173`` is dropped at ``MT = 173``.

An empty colour flow is a zero amplitude for every binding only if no such
binding-dependent row exists. The zero-colour-flow certificate of the tree
lanes (the recurrence's topology-replay and all-flow plans, the compiled
lane's LC replay) asks ``binding_dependent_weyl_projections``. It re-probes
the projections the numeric probe dropped. The mutable external parameters
stay symbols, and every derived kernel parameter is its definition in them. A
projection that is not identically zero is binding dependent. The refusal
names it.

Restriction simplification (``ufo_model_loader``, as MadGraph's restricted
models) removes, before the probe ever runs, every coupling whose value at the
restriction card is exactly zero. That covers a coupling that is zero only
because a mutable parameter takes its card value. ``load_ufo_model`` records
those removals: the removed couplings that are not constants once the internal
parameters are written in the external ones, and that do not vanish at generic
bindings of those externals. ``loading`` keeps them as a compatibility issue
(``BINDING_DEPENDENT_ZERO_COUPLING``) of the compiled model, written only when
there is one.

Both tests run only where a zero colour flow is about to be certified
(``zero_flow_certification_blockers``), so generation of every other process
is unchanged.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Sequence
from typing import Any

from .._internal.physics.symbols import symbols
from . import compiler_symbolica as _sym
from .external_helpers import _is_zero

ProjectionKey = tuple[int, int, int, int]

#: The compiled-model issue code of couplings that restriction simplification
#: removed although they vanish only at the card values of mutable parameters.
BINDING_DEPENDENT_ZERO_COUPLING = "binding-dependent-zero-coupling"
#: Its context when the loader offers no hook to inspect the removals.
UNVERIFIED_REMOVALS = "<removals not inspectable>"
_CAPTURE_LOCK = threading.Lock()


def zero_flow_certification_blockers(model: Any) -> str | None:
    """Why ``model`` cannot certify a colour flow as zero for every permitted
    parameter binding, or ``None`` when it can: its vertex support depends
    on the values of mutable parameters (a coupling restriction removed, or a
    projection the numeric probe dropped)."""

    compiled = getattr(model, "compiled", None)
    for issue in getattr(compiled, "issues", ()):
        if issue.code == BINDING_DEPENDENT_ZERO_COUPLING:
            return (
                "restriction simplification removed couplings that vanish only "
                f"at the card values of mutable parameters ({issue.context})"
            )
    keys = binding_dependent_weyl_projections(model)
    if keys:
        return (
            "the vertex support probe dropped projections that vanish only at "
            "the current values of mutable parameters ("
            + describe_binding_dependent_projections(model, keys)
            + ")"
        )
    return None


def load_ufo_model(
    load_model: Callable[..., tuple[Any, Any]], *args: Any, **kwargs: Any
) -> tuple[Any, Any, tuple[str, ...]]:
    """``load_model(*args, **kwargs)`` of ``ufo_model_loader``, and the names
    of the couplings its restriction simplification removed although they
    are not zero for every binding of the mutable (external) parameters,
    sorted (``UNVERIFIED_REMOVALS`` if the loader offers no hook)."""

    from ufo_model_loader import model as ufo_model

    original = getattr(ufo_model.Model, "remove_zero_couplings", None)
    if original is None:
        model, card = load_model(*args, **kwargs)
        return model, card, (UNVERIFIED_REMOVALS,)
    captured: list[tuple[Any, Sequence[Any]]] = []

    def capture(self: Any) -> Any:
        removed = original(self)
        captured.append((self, tuple(removed[0])))
        return removed

    with _CAPTURE_LOCK:
        ufo_model.Model.remove_zero_couplings = capture
        try:
            model, card = load_model(*args, **kwargs)
        finally:
            ufo_model.Model.remove_zero_couplings = original
    names: set[str] = set()
    for loaded, removed in captured:
        names.update(_binding_dependent_couplings(loaded, removed))
    return model, card, tuple(sorted(names))


def _binding_dependent_couplings(loaded: Any, removed: Sequence[Any]) -> list[str]:
    """The removed couplings of a loaded UFO model that are not constant zero.

    A coupling is written in the external parameters by substituting the
    internal parameters' definitions (the zero-forced externals are internal
    ``ZERO`` after the restriction). One without an external parameter left is
    a constant, zero at the card and so for every binding. One with external
    parameters left is binding dependent unless it also vanishes at two generic
    bindings (every external value scaled by an irrational factor)."""

    from symbolica import S
    from ufo_model_loader.symbolica_processing import (
        evaluate_symbolica_expression_safe,
    )

    externals = {
        S(f"UFO::{parameter.name}"): parameter.value
        for parameter in loaded.get_external_parameters()
    }
    definitions = {}
    constants = dict(loaded.get_model_variables())
    for parameter in loaded.get_internal_parameters():
        symbol = S(f"UFO::{parameter.name}")
        if parameter.expression is None:
            constants[symbol] = parameter.value
        else:
            definitions[symbol] = parameter.expression
    functions = loaded.get_model_functions()
    dependent = []
    for coupling in removed:
        expression = coupling.expression
        for _ in range(256):
            inner = [
                symbol
                for symbol in expression.get_all_symbols()
                if symbol in definitions
            ]
            if not inner:
                break
            for symbol in inner:
                expression = expression.replace(symbol, definitions[symbol])
        else:
            dependent.append(str(coupling.name))
            continue
        if not any(symbol in externals for symbol in expression.get_all_symbols()):
            continue
        for scale in (math.sqrt(2) / 7.0, math.sqrt(3) / 5.0):
            values = dict(constants)
            for index, (symbol, value) in enumerate(externals.items()):
                values[symbol] = complex(value) * (1.0 + scale * (1.0 + index / 17.0))
            try:
                value = evaluate_symbolica_expression_safe(
                    expression, values, functions
                )
            except Exception:
                value = None
            if value is None or complex(value) != 0:
                dependent.append(str(coupling.name))
                break
    return dependent


def binding_dependent_weyl_projections(model: Any) -> tuple[ProjectionKey, ...]:
    """The (vertex kind, left, right, result chirality) projections that
    ``model`` drops at its current parameter values but that are not
    identically zero over the bindings of its mutable parameters, sorted.
    Empty for a model without the numeric probe (the built-in models, whose
    vertex table is fixed). Memoized on the model instance."""

    support_of = getattr(model, "weyl_projection_support", None)
    if support_of is None:
        return ()
    cached = getattr(model, "_binding_dependent_weyl_projections", None)
    if cached is not None:
        return tuple(cached)
    dropped = sorted(key for key, supported in support_of().items() if not supported)
    structural = _structural_parameter_values(model) if dropped else {}
    result = tuple(
        key for key in dropped if _structurally_nonzero(model, key, structural)
    )
    model._binding_dependent_weyl_projections = result
    return result


def describe_binding_dependent_projections(
    model: Any, keys: tuple[ProjectionKey, ...], *, limit: int = 4
) -> str:
    """A short description of ``keys`` for a refusal message."""

    described = []
    for kind, left, right, result in keys[:limit]:
        particles = model._kernel(kind).particles
        described.append(
            f"vertex {kind} ({', '.join(particles)}; chiralities {left}, {right} -> "
            f"{result})"
        )
    if len(keys) > limit:
        described.append(f"and {len(keys) - limit} more")
    return "; ".join(described)


def _structural_parameter_values(model: Any) -> dict[str, Any]:
    """Every runtime parameter of the model as a function of the mutable
    external parameters: an external one is its own symbol, a derived one its
    definition (written in the external symbols)."""

    values: dict[str, Any] = {
        name: model._model_symbols.symbol(name) for name in model._runtime_parameters
    }
    for name, definition in model._runtime_derived_definitions.items():
        values.setdefault(name, _sym.E(definition))
    return values


def _structurally_nonzero(
    model: Any, key: ProjectionKey, structural: dict[str, Any]
) -> bool:
    kind, left_chirality, right_chirality, result_chirality = key
    kernel = model._kernel(kind)
    left_pdg = model._particle_records_by_name[kernel.particles[0]].pdg_code
    right_pdg = model._particle_records_by_name[kernel.particles[1]].pdg_code

    def probe(side: str, part: str, count: int) -> tuple[Any, ...]:
        return tuple(
            symbols.weyl_probe(model.name, kind, side, part, index)
            for index in range(count)
        )

    parameter_values = {}
    for name in kernel.runtime_parameters:
        if name not in structural:
            # A parameter the model fixes (no runtime definition): its value.
            parameter_values[name] = model._parameter_value(name)
        else:
            parameter_values[name] = structural[name]
    components = model._projected_kernel_components(
        kernel,
        probe("left", "component", model.current_dimension(left_pdg, left_chirality)),
        probe(
            "right", "component", model.current_dimension(right_pdg, right_chirality)
        ),
        left_chirality=left_chirality,
        right_chirality=right_chirality,
        result_chirality=result_chirality,
        left_momentum=probe("left", "momentum", 4),
        right_momentum=probe("right", "momentum", 4),
        runtime_parameter_values=parameter_values,
    )
    return any(not _is_zero(_expanded(component)) for component in components)


def _expanded(value: Any) -> Any:
    if isinstance(value, _sym.Expression):
        return value.expand()
    return value
