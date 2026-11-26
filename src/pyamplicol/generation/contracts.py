# SPDX-License-Identifier: 0BSD
from __future__ import annotations

import hashlib
import json
import marshal
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..models.base import Model
from ..models.specialization_guards import SpecializationGuard
from .dag_types import GenericDAG

LC_SECTOR_SELECTOR_PARAMETER = "runtime.lc_sector_id"
EXPRESSION_SCHEMA_CONTRACT_VERSION = 2
_REQUIRED_RUNTIME_SCHEMA_KEYS = frozenset(
    {
        "amplitude_stage",
        "current_storage",
        "momentum_slots",
        "parameter_layout",
        "stages",
        "value_storage",
    }
)


@dataclass(frozen=True, slots=True)
class RuntimeExpressionSchema:
    """Canonical, dependency-neutral stage compiler input schema."""

    canonical_json: str
    contract_version: int = EXPRESSION_SCHEMA_CONTRACT_VERSION
    _payload_blob: bytes = field(
        init=False,
        repr=False,
        compare=False,
        hash=False,
    )

    def __post_init__(self) -> None:
        if self.contract_version != EXPRESSION_SCHEMA_CONTRACT_VERSION:
            raise ValueError(
                "unsupported runtime expression-schema contract version "
                f"{self.contract_version}"
            )
        try:
            payload = json.loads(self.canonical_json)
        except json.JSONDecodeError as exc:
            raise ValueError("runtime expression schema is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("runtime expression schema root must be an object")
        missing = sorted(_REQUIRED_RUNTIME_SCHEMA_KEYS - payload.keys())
        if missing:
            raise ValueError(
                "runtime expression schema is missing: " + ", ".join(missing)
            )
        # The blob is an immutable, process-local cache of already validated JSON.
        # It is never persisted or loaded from untrusted input.
        object.__setattr__(self, "_payload_blob", marshal.dumps(payload))

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object] | RuntimeExpressionSchema,
    ) -> RuntimeExpressionSchema:
        if isinstance(payload, cls):
            return payload
        try:
            canonical = json.dumps(
                payload,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "runtime expression schema must contain canonical JSON values"
            ) from exc
        return cls(canonical_json=canonical)

    def to_mapping(self) -> dict[str, object]:
        payload = marshal.loads(self._payload_blob)
        if not isinstance(payload, dict):  # pragma: no cover - internal invariant
            raise RuntimeError("runtime expression schema cache is not an object")
        return {str(key): value for key, value in payload.items()}

    def __reduce__(self) -> tuple[object, tuple[str, int]]:
        return type(self), (self.canonical_json, self.contract_version)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class StageCompilationInput:
    dag: GenericDAG
    model: Model
    runtime_schema: RuntimeExpressionSchema

    def __post_init__(self) -> None:
        if not isinstance(self.dag, GenericDAG):
            raise TypeError("stage compilation input requires a GenericDAG")
        if not isinstance(self.model, Model):
            raise TypeError("stage compilation input requires a Model")
        if not isinstance(self.runtime_schema, RuntimeExpressionSchema):
            raise TypeError(
                "stage compilation input requires a RuntimeExpressionSchema"
            )


def runtime_coupling_parameter_names(
    vertex_kind: int,
    vertex_particles: Sequence[int],
    coupling: Sequence[object],
    *,
    model: Model | None = None,
) -> list[str | None]:
    runtime_names = getattr(model, "runtime_parameter_names_for_vertex", None)
    if callable(runtime_names):
        return [str(name) for name in runtime_names(int(vertex_kind))]
    lowering_rule = getattr(model, "vertex_lowering_rule", None)
    if callable(lowering_rule):
        rule = lowering_rule(int(vertex_kind))
        if rule.coupling_mode in {"fixed", "none"}:
            return [None for _value in coupling]
    particles = "_".join(str(int(pdg)) for pdg in vertex_particles)
    base = f"coupling.{int(vertex_kind)}.{particles}"
    names: list[str | None] = []
    for component, value in enumerate(coupling):
        if not isinstance(value, str | int | float):
            raise TypeError(
                f"runtime coupling components must be numeric, got {value!r}"
            )
        numeric_value = float(value)
        if component == 1 and numeric_value == -10.0:
            names.append(None)
        else:
            names.append(f"{base}.component_{component}")
    return names


#: The producer name of the guards of zero coupling components (below).
VERTEX_CHIRAL_SUPPORT = "vertex-chiral-support"
_RUNTIME_COUPLING_NAME = re.compile(
    r"coupling\.(?P<kind>\d+)\.(?P<particles>-?\d+(?:_-?\d+)*)"
    r"\.component_(?P<component>\d+)"
)


def zero_coupling_decisions(model: Model, vertex: Any) -> frozenset[int]:
    """The components of ``vertex.coupling`` that are zero and on whose zero
    the model's chirality selection (``model._vertex_result_chiralities``)
    depends: for some input state the model can produce (a chiral-eligible
    fermion as a Weyl state of either chirality or as a full current, any
    other particle as a full state), making the component nonzero changes the
    selected result chiralities. Only these zeros dropped a current at
    generation; a zero no selection reads (a Dirac input keeps every
    transition as soon as any component is nonzero) dropped nothing."""

    from dataclasses import replace
    from types import SimpleNamespace

    select = model._vertex_result_chiralities  # type: ignore[attr-defined]
    zeros = [index for index, value in enumerate(vertex.coupling) if value == 0.0]
    if not zeros:
        return frozenset()

    def states(pdg: int) -> tuple[Any, ...]:
        chiral = model.is_fermion(pdg) and model.is_chiral_eligible(pdg)
        return tuple(
            SimpleNamespace(
                particle_id=pdg,
                pdg=pdg,
                chirality=chirality,
                flavour_flow=(pdg,),
                coupling_orders=(),
            )
            for chirality in ((-1, 0, 1) if chiral else (0,))
        )

    decided: set[int] = set()
    for left in states(int(vertex.particles[0])):
        for right in states(int(vertex.particles[1])):
            selected = select(vertex, left, right)
            for index in zeros:
                coupling = list(vertex.coupling)
                coupling[index] = 1.0
                revived = replace(vertex, coupling=tuple(coupling))
                if select(revived, left, right) != selected:
                    decided.add(index)
    return frozenset(decided)


def runtime_coupling_component_guards(
    model: Model, records: Iterable[Mapping[str, object]]
) -> tuple[SpecializationGuard, ...]:
    """The specialisation guards of the coupling components a process exposes
    as runtime parameters (``runtime_coupling_parameter_names``) whose zero at
    generation the model's chirality selection read
    (``zero_coupling_decisions``: the built-in model drops the Weyl currents
    of a chirality whose component is zero).

    Such a component holds at zero: a binding that makes it nonzero would need
    the currents generation dropped. A component whose zero no selection read
    (a vertex with a Dirac input keeps both chiralities when any component is
    nonzero) records nothing and stays a working parameter. ``records``: the
    process's runtime model-parameter records (``name``, ``default``,
    ``runtime_name`` for the components of a complex parameter)."""

    select = getattr(model, "_vertex_result_chiralities", None)
    if not callable(select) or not callable(getattr(model, "is_chiral_eligible", None)):
        return ()

    def decisions(vertex: Any) -> frozenset[int]:
        return zero_coupling_decisions(model, vertex)

    defaults: dict[str, list[float]] = {}
    for record in records:
        name = str(record.get("runtime_name") or record["name"])
        defaults.setdefault(name, []).append(float(record["default"]))  # type: ignore[arg-type]
    vertices = {
        (int(vertex.kind), tuple(int(pdg) for pdg in vertex.particles)): vertex
        for vertex in getattr(model, "vertices", ())
    }
    guards: list[SpecializationGuard] = []
    for name in sorted(defaults):
        match = _RUNTIME_COUPLING_NAME.fullmatch(name)
        if match is None or any(value != 0.0 for value in defaults[name]):
            continue
        key = (
            int(match["kind"]),
            tuple(int(pdg) for pdg in match["particles"].split("_")),
        )
        vertex = vertices.get(key)
        if vertex is None or int(match["component"]) not in decisions(vertex):
            continue
        guards.append(
            SpecializationGuard.holding(
                "vanishing",
                {name: 0j},
                subject=(
                    f"coupling component {name}, zero at generation, decided "
                    "which chiralities of a massless fermion the vertex passes"
                ),
                producer=VERTEX_CHIRAL_SUPPORT,
                message=(
                    "the massless fermion lines carry only the chiralities this "
                    "component allowed at generation; generate with a model whose "
                    "vertex has it nonzero"
                ),
                expression=name,
            )
        )
    return tuple(guards)


__all__ = [
    "EXPRESSION_SCHEMA_CONTRACT_VERSION",
    "LC_SECTOR_SELECTOR_PARAMETER",
    "RuntimeExpressionSchema",
    "StageCompilationInput",
    "runtime_coupling_component_guards",
    "runtime_coupling_parameter_names",
    "zero_coupling_decisions",
]
