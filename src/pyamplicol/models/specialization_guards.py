# SPDX-License-Identifier: 0BSD
"""Specialisation guards: what generation specialised to the values of
runtime parameters, and the parameters it binds.

Generation specialises a model to the values its parameters have when it
runs. Restriction simplification removes a coupling whose value is zero at
the restriction card; a vertex passes a massless fermion only in the
chiralities whose coupling component is nonzero. Each is exact for every
binding of the runtime (mutable) parameters only when it holds identically.

The rule. A specialisation that is proven for every binding at generation
records nothing (no mutable dependence; a ``vanishing`` expression that
expands to zero; a ``real`` expression provably real with every external
declared real taken as a real symbol). Any other is recorded as a guard
that holds *only while every parameter it depends on keeps its generation
value*: the binary64 value (both components for a complex parameter) the
artifact recorded, compared exactly with the value as bound (after a text,
a parameter card or a JSON number has been read as binary64). Carriers that
evaluate exactly (the one-loop runtime's decimals, the tree lanes' extended
precision) read a parameter as the shortest decimal that rounds to its
binary64 (``exact_generation_value``: 91.188, not the binary64 nearest it,
as a card and the loop plan's defaults give it); a vanishing specialisation
must be exactly zero there, or the producer refuses it
(``InexactSpecialization``). No numerical
test accepts a changed value, whatever the tolerance: a guarded artifact
refuses any change of such a parameter, even one under which the condition
would in fact still hold, and the remedy is to generate again at the new
value. A vanishing expression with a factor that is exactly zero at the
generation values depends only on that factor's parameters (the factor
with the fewest).

A guard is

``kind``
    ``"vanishing"`` (the expression was zero) or ``"real"`` (it was real).
``subject``, ``producer``, ``message``
    What was specialised, who specialised it and what to do instead.
``parameters``
    The mutable (external) parameters it holds, sorted.
``generation_values``
    Their binary64 values at generation (real, imaginary).
``expression``
    The specialised expression as Symbolica text, for people.

Every runtime binding (``Runtime.set_model_parameters`` and the paths built
on it, the exported SDKs, the one-loop runtime) refuses, applying nothing, a
binding that gives a guarded parameter another value.

Where guards live: ``CompiledModel.specialization_guards`` (the model's own,
for every process; compiled-model schema ``GUARDED_COMPILED_MODEL_SCHEMA_
VERSION`` when there is one) and the process artifacts'
``specialization_guards`` (a generation-time producer's, for that process).
An artifact with at least one guard stores them all in ``GUARD_FILE_PATH``
under the payload role ``GUARD_PAYLOAD_ROLE``, which released readers refuse.
"""

from __future__ import annotations

import contextlib
import math
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from typing import Any

#: Where an artifact stores its guards, and the payload's role and kind.
GUARD_FILE_PATH = "model/specialization-guards.json"
GUARD_PAYLOAD_ROLE = "specialization-guards"
GUARD_FILE_KIND = "pyamplicol-specialization-guards"
GUARD_FILE_SCHEMA_VERSION = 1
KINDS = ("vanishing", "real")
#: The refusal prefix of a binding that a guard rejects.
REFUSAL_PREFIX = "specialisation-guard"
#: Symbolica's own constants are spelled "\U0001d70b" (pi) and "\U0001d452" (e).
_PI_SYMBOL = "\U0001d70b"
_E_SYMBOL = "\U0001d452"
_CONSTANTS = {"I": 1j, "pi": math.pi, _PI_SYMBOL: math.pi, _E_SYMBOL: math.e}


class InexactSpecialization(ValueError):
    """A vanishing expression that is zero at the generation values only in
    binary64 arithmetic, not exactly at their decimals: exact carriers would
    evaluate a term the specialisation dropped."""


def exact_generation_value(component: float) -> Fraction:
    """The exact value of a recorded binary64 generation value for an exact
    carrier: the shortest decimal that rounds to it (``repr``), as a card,
    the loop plan's defaults and the tree lanes' extended precision read it."""

    return Fraction(Decimal(repr(float(component))))


@dataclass(frozen=True)
class SpecializationGuard:
    kind: str
    subject: str
    producer: str
    parameters: tuple[str, ...]
    generation_values: Mapping[str, tuple[float, float]]
    expression: str
    message: str
    process_ids: tuple[str, ...] | None = field(default=None)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown specialisation-guard kind {self.kind!r}")
        if not self.parameters:
            raise ValueError("a specialisation guard holds at least one parameter")
        if tuple(sorted(set(self.parameters))) != tuple(self.parameters):
            raise ValueError(
                "specialisation-guard parameters must be sorted and unique"
            )
        if set(self.generation_values) != set(self.parameters):
            raise ValueError(
                "specialisation-guard generation values must name its parameters"
            )
        for name, value in self.generation_values.items():
            if not all(math.isfinite(component) for component in value):
                raise ValueError(
                    f"specialisation-guard generation value of {name!r} is not finite"
                )

    # -- construction -----------------------------------------------------------

    @classmethod
    def vanishing(
        cls,
        environment: GuardEnvironment,
        expression: Any,
        *,
        subject: str,
        producer: str,
        message: str,
    ) -> SpecializationGuard | None:
        """The guard of ``expression`` (zero at generation), or ``None`` when it
        vanishes for every binding (structural: nothing to record)."""

        return cls._build(
            "vanishing",
            environment,
            expression,
            subject=subject,
            producer=producer,
            message=message,
        )

    @classmethod
    def real(
        cls,
        environment: GuardEnvironment,
        expression: Any,
        *,
        subject: str,
        producer: str,
        message: str,
    ) -> SpecializationGuard | None:
        """The guard of ``expression`` (real at generation), or ``None`` when it
        is real for every binding (no mutable dependence, or provably real in
        the environment's real parameters: ``is_real_for_every_binding``)."""

        return cls._build(
            "real",
            environment,
            expression,
            subject=subject,
            producer=producer,
            message=message,
        )

    @classmethod
    def holding(
        cls,
        kind: str,
        generation_values: Mapping[str, complex],
        *,
        subject: str,
        producer: str,
        message: str,
        expression: str = "",
    ) -> SpecializationGuard:
        """A guard that holds the named parameters at the given generation
        values (a producer that knows the parameters directly)."""

        return cls(
            kind=kind,
            subject=subject,
            producer=producer,
            parameters=tuple(sorted(generation_values)),
            generation_values={
                name: (float(complex(value).real), float(complex(value).imag))
                for name, value in generation_values.items()
            },
            expression=expression,
            message=message,
        )

    @classmethod
    def _build(
        cls,
        kind: str,
        environment: GuardEnvironment,
        expression: Any,
        *,
        subject: str,
        producer: str,
        message: str,
    ) -> SpecializationGuard | None:
        resolved = environment.resolve(expression)
        parameters = environment.mutable_dependencies(resolved)
        if not parameters:
            return None
        if kind == "vanishing":
            if _is_identically_zero(resolved):
                return None
            parameters = _vanishing_factor_dependencies(environment, resolved)
            if not parameters:
                return None
            if not _exactly_zero_at_generation(
                environment, resolved, environment.mutable_dependencies(resolved)
            ):
                raise InexactSpecialization(
                    f"{subject}: the expression is zero at the generation values "
                    "only in binary64 arithmetic, not exactly at their decimals; "
                    "compile the model with simplify=False"
                )
        elif environment.is_real_for_every_binding(resolved):
            return None
        return cls(
            kind=kind,
            subject=subject,
            producer=producer,
            parameters=parameters,
            generation_values={
                name: environment.generation_value(name) for name in parameters
            },
            expression=resolved.to_canonical_string(),
            message=message,
        )

    def for_processes(self, process_ids: Iterable[str]) -> SpecializationGuard:
        return SpecializationGuard(
            kind=self.kind,
            subject=self.subject,
            producer=self.producer,
            parameters=self.parameters,
            generation_values=self.generation_values,
            expression=self.expression,
            message=self.message,
            process_ids=tuple(sorted(set(process_ids))),
        )

    # -- evaluation ---------------------------------------------------------------

    def failure(self, values: Mapping[str, complex]) -> str | None:
        """Why the guard fails at ``values`` (a parameter absent from it keeps
        its generation value), or ``None`` when every parameter it holds has
        exactly its generation value."""

        changed = []
        for name in self.parameters:
            if name not in values:
                continue
            value = complex(values[name])
            generation = self.generation_values[name]
            if (value.real, value.imag) != (generation[0], generation[1]):
                changed.append(
                    f"{name} = {_format_complex(value)} (generated at "
                    f"{_format_complex(complex(*generation))})"
                )
        if not changed:
            return None
        return (
            ", ".join(changed)
            + "; the artifact holds this parameter at its generation value"
        )

    # -- serialisation -------------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": self.kind,
            "subject": self.subject,
            "producer": self.producer,
            "parameters": list(self.parameters),
            "generation_values": {
                name: [float(value[0]), float(value[1])]
                for name, value in sorted(self.generation_values.items())
            },
            "expression": self.expression,
            "message": self.message,
        }
        if self.process_ids is not None:
            payload["process_ids"] = list(self.process_ids)
        return payload

    @staticmethod
    def from_dict(payload: Mapping[str, object]) -> SpecializationGuard:
        values = payload.get("generation_values")
        if not isinstance(values, Mapping):
            raise ValueError("specialisation-guard generation_values must be an object")
        process_ids = payload.get("process_ids")
        return SpecializationGuard(
            kind=str(payload["kind"]),
            subject=str(payload["subject"]),
            producer=str(payload["producer"]),
            parameters=tuple(str(name) for name in _sequence(payload["parameters"])),
            generation_values={
                str(name): (float(value[0]), float(value[1]))
                for name, value in values.items()
            },
            expression=str(payload["expression"]),
            message=str(payload["message"]),
            process_ids=None
            if process_ids is None
            else tuple(str(item) for item in _sequence(process_ids)),
        )


def guard_file_payload(guards: Sequence[SpecializationGuard]) -> dict[str, object]:
    return {
        "kind": GUARD_FILE_KIND,
        "schema_version": GUARD_FILE_SCHEMA_VERSION,
        "guards": [guard.to_dict() for guard in guards],
    }


def guards_from_file_payload(
    payload: Mapping[str, object],
) -> tuple[SpecializationGuard, ...]:
    if payload.get("kind") != GUARD_FILE_KIND:
        raise ValueError("file is not a pyAmpliCol specialisation-guard record")
    if payload.get("schema_version") != GUARD_FILE_SCHEMA_VERSION:
        raise ValueError("unsupported specialisation-guard record version")
    return tuple(
        SpecializationGuard.from_dict(_mapping(item))
        for item in _sequence(payload["guards"])
    )


def guards_for_process(
    guards: Iterable[SpecializationGuard], process_id: str | None
) -> tuple[SpecializationGuard, ...]:
    return tuple(
        guard
        for guard in guards
        if guard.process_ids is None
        or (process_id is not None and process_id in guard.process_ids)
    )


def binding_refusal(
    guards: Iterable[SpecializationGuard],
    binding: Mapping[str, complex],
    current: Mapping[str, complex] | None = None,
) -> str | None:
    """The refusal message of ``binding`` (the new values by name), or ``None``
    when it gives every guarded parameter its generation value. ``current`` is
    accepted for the callers' convenience and not needed: a refused binding
    applies nothing, so a guarded parameter's current value is its generation
    value."""

    del current
    failures = []
    for guard in guards:
        touched = sorted(set(guard.parameters) & set(binding))
        if not touched:
            continue
        failure = guard.failure(binding)
        if failure is not None:
            failures.append(describe_failure(guard, touched, failure))
    if not failures:
        return None
    return "; ".join(failures)


def exact_decimal_binding_refusal(
    guards: Iterable[SpecializationGuard], binding: Mapping[str, object]
) -> str | None:
    """``binding_refusal`` for an exact binding (decimal text or numbers read
    exactly, as the one-loop runtime binds them): a guarded parameter is
    unchanged only when its value equals the exact value of the recorded
    binary64 and the recorded imaginary part is zero."""

    failures = []
    for guard in guards:
        changed = []
        for name in guard.parameters:
            if name not in binding:
                continue
            real, imaginary = guard.generation_values[name]
            value = _exact_value(binding[name])
            if (
                imaginary != 0.0
                or value is None
                or value != exact_generation_value(real)
            ):
                changed.append(
                    f"{name} = {binding[name]} (generated at "
                    f"{_format_complex(complex(real, imaginary))})"
                )
        if changed:
            failures.append(
                describe_failure(
                    guard,
                    [entry.split(" ", 1)[0] for entry in changed],
                    ", ".join(changed)
                    + "; the artifact holds this parameter at its generation value",
                )
            )
    return "; ".join(failures) if failures else None


def _exact_value(value: object) -> Fraction | None:
    """``value`` as an exact rational: a float as its shortest decimal, an
    int, ``Fraction`` or ``Decimal`` exactly, text as a decimal or a
    fraction."""

    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        # A float binding is read as its shortest decimal, as the runtime
        # reads it.
        return exact_generation_value(value) if math.isfinite(value) else None
    if isinstance(value, int | Fraction | Decimal):
        try:
            return Fraction(value)
        except (ArithmeticError, ValueError):
            return None
    text = str(value).strip().replace("_", "")
    try:
        return Fraction(Decimal(text))
    except (ArithmeticError, ValueError):
        pass
    try:
        return Fraction(text)
    except (ArithmeticError, ValueError, ZeroDivisionError):
        return None


def admit_loop_specialization_guards(
    guards: Iterable[SpecializationGuard],
    fixed: Mapping[str, object],
    scale_parameter: str | None,
) -> None:
    """Refuse a one-loop plan whose guards it cannot honour: a guarded
    parameter that is the renormalisation scale (set per point), or one fixed
    at generation to a value other than its guarded one."""

    for guard in guards:
        for name in guard.parameters:
            if scale_parameter is not None and name == scale_parameter:
                raise ValueError(
                    f"{REFUSAL_PREFIX}: {guard.subject} holds the renormalisation-"
                    f"scale parameter {name!r}, which the one-loop runtime sets "
                    "per point; regenerate from a model compiled without that "
                    "specialisation"
                )
            if name in fixed:
                refusal = exact_decimal_binding_refusal([guard], {name: fixed[name]})
                if refusal is not None:
                    raise ValueError(f"{refusal} (a fixed parameter of the plan)")


def describe_failure(
    guard: SpecializationGuard, touched: Sequence[str], failure: str
) -> str:
    return (
        f"{REFUSAL_PREFIX}: binding {', '.join(touched)} invalidates a "
        f"{guard.kind} specialisation made at generation ({guard.subject}, "
        f"recorded by {guard.producer}): {failure}; {guard.message}"
    )


def _vanishing_factor_dependencies(
    environment: GuardEnvironment, resolved: Any
) -> tuple[str, ...]:
    """The parameters a vanishing ``resolved`` depends on through its zero: the
    mutable dependencies of the factor (of its top-level product or of its
    factorisation) that is exactly zero at the generation values, the one with
    the fewest; all its mutable dependencies when no factor is provably zero
    there. A factor ``f`` with ``f(generation) = 0`` exactly keeps the product
    zero while its own parameters keep their generation values."""

    candidates = [resolved]
    # Factorisation is an optional refinement: an expression Symbolica cannot
    # factor keeps its top-level product.
    with contextlib.suppress(Exception):
        candidates.append(_with_imaginary_unit(resolved).factor())
    best = environment.mutable_dependencies(resolved)
    for candidate in candidates:
        for factor in _product_factors(candidate):
            dependencies = environment.mutable_dependencies(factor)
            if not dependencies or len(dependencies) >= len(best):
                continue
            if _exactly_zero_at_generation(environment, factor, dependencies):
                best = dependencies
    return best


def _product_factors(expression: Any) -> list[Any]:
    """The factors of a top-level product (a positive integer power counts as
    its base), or the expression itself."""

    from symbolica import AtomType

    factors = (
        list(expression) if expression.get_type() == AtomType.Mul else [expression]
    )
    out = []
    for factor in factors:
        if factor.get_type() == AtomType.Pow:
            base, exponent = list(factor)
            if exponent.get_type() == AtomType.Num:
                try:
                    power = Fraction(str(exponent.to_canonical_string()))
                except (ValueError, ZeroDivisionError):
                    power = Fraction(0)
                if power > 0 and power.denominator == 1:
                    out.append(base)
                    continue
        out.append(factor)
    return out


def _exactly_zero_at_generation(
    environment: GuardEnvironment, factor: Any, dependencies: Sequence[str]
) -> bool:
    """Whether ``factor`` is exactly zero (in exact rational arithmetic) with
    its parameters at their binary64 generation values."""

    from symbolica import E, Expression

    substituted = _rational_literals(_with_imaginary_unit(factor))
    for symbol in factor.get_all_symbols(False):
        name = _short_name(symbol.get_name())
        if name not in dependencies:
            continue
        real, imaginary = environment.generation_value(name)
        value = E(_exact_text(real))
        if imaginary != 0.0:
            value = value + E(_exact_text(imaginary)) * Expression.I
        substituted = substituted.replace(symbol, value)
    try:
        expanded = substituted.expand()
        return bool(expanded.is_constant()) and expanded.to_canonical_string() == "0"
    except (TypeError, ValueError):
        return False


def _rational_literals(expression: Any) -> Any:
    """``expression`` with every binary64 literal (a UFO ``91.188``) read as
    its shortest decimal, as exact carriers read numbers."""

    from symbolica import AtomType, E

    found: dict[str, Any] = {}

    def collect(atom: Any) -> None:
        kind = atom.get_type()
        if kind == AtomType.Num:
            text = atom.to_canonical_string()
            if ("." in text or "e" in text) and text not in found:
                try:
                    value = float(text)
                except ValueError:
                    return
                if math.isfinite(value):
                    found[text] = (atom, value)
            return
        if kind in (AtomType.Add, AtomType.Mul, AtomType.Pow, AtomType.Fn):
            for child in atom:
                collect(child)

    collect(expression)
    for atom, value in found.values():
        exact = exact_generation_value(value)
        expression = expression.replace(
            atom, E(f"({exact.numerator}/{exact.denominator})")
        )
    return expression


def _exact_text(value: float) -> str:
    exact = exact_generation_value(value)
    return f"({exact.numerator}/{exact.denominator})"


# -- the parameter environment ---------------------------------------------------


@dataclass
class GuardEnvironment:
    """The parameters a guard's expression is written in.

    ``externals``: the mutable parameters and their generation values;
    ``definitions``: the other parameters' expressions (substituted, to any
    depth); ``constants``: parameters with a fixed value. Symbols are matched
    by their name after the last ``::``, so a UFO-namespaced and a
    model-namespaced spelling of one parameter are the same."""

    externals: dict[str, complex]
    definitions: dict[str, Any]
    constants: dict[str, complex]
    #: The externals a binding can only give a real value (declared real).
    real_externals: frozenset[str] = frozenset()
    _resolved: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_ufo_model(model: Any) -> GuardEnvironment:
        """The environment of a model of ``ufo_model_loader`` after its
        restriction (a parameter the card forced to zero is the internal
        ``ZERO``, a constant)."""

        externals = {
            str(parameter.name): complex(parameter.value)
            for parameter in model.get_external_parameters()
        }
        definitions: dict[str, Any] = {}
        constants = {
            _short_name(symbol.get_name()): complex(value)
            for symbol, value in model.get_model_variables().items()
        }
        for parameter in model.get_internal_parameters():
            if parameter.expression is None:
                constants[str(parameter.name)] = complex(parameter.value)
            else:
                definitions[str(parameter.name)] = parameter.expression
        real_externals = frozenset(
            str(parameter.name)
            for parameter in model.get_external_parameters()
            if str(parameter.parameter_type).lower() == "real"
        )
        return GuardEnvironment(externals, definitions, constants, real_externals)

    @staticmethod
    def from_parameter_records(
        records: Iterable[Any],
        extra_definitions: Mapping[str, Any] | None = None,
    ) -> GuardEnvironment:
        """The environment of a compiled model's parameter records
        (``CompiledModelIR.parameters``); ``extra_definitions`` adds derived
        quantities (a vertex term's coupling) by name."""

        from symbolica import E

        externals: dict[str, complex] = {}
        definitions: dict[str, Any] = {}
        constants: dict[str, complex] = dict(_CONSTANTS)
        real_externals: set[str] = set()
        for record in records:
            name = str(record.name)
            if str(record.nature).lower() != "internal":
                value = record.value or (0.0, 0.0)
                externals[name] = complex(float(value[0]), float(value[1]))
                if str(getattr(record, "parameter_type", "")).lower() == "real":
                    real_externals.add(name)
            elif record.expression is None:
                value = record.value or (0.0, 0.0)
                constants[name] = complex(float(value[0]), float(value[1]))
            else:
                definitions[name] = E(str(record.resolved_expression))
        for name, expression in (extra_definitions or {}).items():
            definitions[str(name)] = (
                E(expression) if isinstance(expression, str) else expression
            )
        return GuardEnvironment(
            externals, definitions, constants, frozenset(real_externals)
        )

    def generation_value(self, name: str) -> tuple[float, float]:
        value = self.externals[name]
        return (float(value.real), float(value.imag))

    def resolve(self, expression: Any) -> Any:
        """``expression`` with every non-external parameter replaced by its
        definition or value, to any depth."""

        from symbolica import E

        if isinstance(expression, str):
            expression = E(expression)
        return self._substitute(expression, ())

    def _substitute(self, expression: Any, visiting: tuple[str, ...]) -> Any:
        replacements = []
        for symbol in expression.get_all_symbols(False):
            name = _short_name(symbol.get_name())
            if name in self.externals:
                continue
            if name in self.constants:
                replacements.append((symbol, _number(self.constants[name])))
                continue
            if name in self.definitions:
                if name in visiting:
                    raise ValueError(
                        f"parameter {name!r} is defined in terms of itself"
                    )
                resolved = self._resolved.get(name)
                if resolved is None:
                    resolved = self._substitute(
                        _as_expression(self.definitions[name]), (*visiting, name)
                    )
                    self._resolved[name] = resolved
                replacements.append((symbol, resolved))
        for source, replacement in replacements:
            expression = expression.replace(source, replacement)
        return expression

    def is_real_for_every_binding(self, resolved: Any) -> bool:
        """Whether ``resolved`` (written in the externals) is real for every
        binding: provably real (Symbolica's ``is_real``) once each real
        external is a real symbol. A square root or a non-integer power of a
        real parameter is not (it is imaginary where its base is negative)."""

        from .._internal.physics.symbols import _symbol

        expression = _with_imaginary_unit(resolved)
        for position, symbol in enumerate(resolved.get_all_symbols(False)):
            name = _short_name(symbol.get_name())
            if name in self.real_externals:
                spelling = "".join(c if c.isalnum() else "_" for c in name)
                expression = expression.replace(
                    symbol,
                    _symbol(
                        f"pyamplicol_guard_real::r{position}_{spelling}",
                        is_real=True,
                    ),
                )
        try:
            return bool(expression.is_real())
        except (TypeError, ValueError):
            return False

    def mutable_dependencies(self, resolved: Any) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    _short_name(symbol.get_name())
                    for symbol in resolved.get_all_symbols(False)
                }
                & set(self.externals)
            )
        )


def _short_name(name: str) -> str:
    return str(name).rsplit("::", 1)[-1]


def _with_imaginary_unit(expression: Any) -> Any:
    """``expression`` with every UFO ``complex(a, b)`` written ``a + b i``."""

    from symbolica import AtomType, Expression

    found: list[Any] = []

    def collect(atom: Any) -> None:
        kind = atom.get_type()
        if kind == AtomType.Fn:
            children = list(atom)
            if _short_name(atom.get_name()) == "complex" and len(children) == 2:
                found.append((atom, children))
                return
            for child in children:
                collect(child)
        elif kind in (AtomType.Add, AtomType.Mul, AtomType.Pow):
            for child in atom:
                collect(child)

    collect(expression)
    for atom, (real, imaginary) in found:
        expression = expression.replace(
            atom,
            _with_imaginary_unit(real) + _with_imaginary_unit(imaginary) * Expression.I,
        )
    return expression


def _is_identically_zero(expression: Any) -> bool:
    expanded = _with_imaginary_unit(expression).expand()
    try:
        return bool(expanded.is_constant()) and complex(expanded.evaluate({})) == 0
    except (TypeError, ValueError):
        return False


def _as_expression(value: Any) -> Any:
    from symbolica import E

    return E(value) if isinstance(value, str) else value


def _number(value: complex) -> Any:
    """``value`` as a Symbolica number, exact when it is an integer (so a
    parameter fixed to zero cancels the terms it multiplies)."""

    from symbolica import Expression

    def part(component: float) -> Any:
        return Expression.num(int(component) if component.is_integer() else component)

    if value.imag == 0.0:
        return part(float(value.real))
    return part(float(value.real)) + part(float(value.imag)) * Expression.I


def _format_complex(value: complex) -> str:
    if value.imag == 0.0:
        return repr(value.real)
    return f"({value.real!r}{value.imag:+}j)"


def _sequence(value: object) -> Sequence[Any]:
    if not isinstance(value, list | tuple):
        raise ValueError("expected a list")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected an object")
    return value


# -- producer: restriction simplification -------------------------------------------

#: The producer name of the guards of couplings restriction simplification removed.
RESTRICTION_SIMPLIFICATION = "restriction-simplification"
_CAPTURE_LOCK = threading.Lock()


def load_ufo_model_with_guards(
    load_model: Callable[..., tuple[Any, Any]], *args: Any, **kwargs: Any
) -> tuple[Any, Any, tuple[SpecializationGuard, ...], tuple[dict[str, Any], ...]]:
    """``load_model(*args, **kwargs)`` of ``ufo_model_loader``, the guards of
    the couplings its restriction simplification removed, and the record of
    every coupling it removed (``removed_coupling_record``).

    The simplification (``Model.remove_zero_couplings``) removes every
    coupling whose value at the restriction card is zero. A removed coupling
    is a structural zero when it vanishes identically once the remaining
    internal parameters are written in the external (mutable) ones, the
    externals the card set to zero being the constant ``ZERO``; otherwise it
    is zero only at the card's values, and its guard ("vanishing") refuses a
    binding that revives it. A structural zero is structural only for the
    model's own parameter definitions: a transform that redefines parameters
    afterwards (the complex-mass scheme sets ``CMSParam`` to 1 and the Yukawa
    inputs to the masses) can revive it, so every removed coupling is
    recorded, guarded or not, for such a transform to evaluate again
    (``revived_removed_couplings``)."""

    from ufo_model_loader import model as ufo_model

    captured: list[SpecializationGuard] = []
    removed_records: list[dict[str, Any]] = []
    # The original method is read and restored under the lock, so overlapping
    # loads in one process can never leave a wrapper installed.
    with _CAPTURE_LOCK:
        original = ufo_model.Model.remove_zero_couplings

        def remove_zero_couplings(self: Any) -> Any:
            removed = original(self)
            captured.extend(_removed_coupling_guards(self, removed[0]))
            removed_records.extend(
                removed_coupling_record(coupling) for coupling in removed[0]
            )
            return removed

        ufo_model.Model.remove_zero_couplings = remove_zero_couplings
        try:
            model, card = load_model(*args, **kwargs)
        finally:
            ufo_model.Model.remove_zero_couplings = original
    unique = {guard.subject: guard for guard in captured}
    records = {record["name"]: record for record in removed_records}
    return (
        model,
        card,
        tuple(unique[subject] for subject in sorted(unique)),
        tuple(records[name] for name in sorted(records)),
    )


# -- removed couplings and the transforms that redefine parameters ----------------


def removed_coupling_record(coupling: Any) -> dict[str, Any]:
    """A coupling restriction simplification removed, in the loader's own
    serialised form (the ``couplings`` entries of a compiled model's
    ``model`` payload: name, expression, orders, value at the card), so that
    a transform can put it back into that payload and evaluate it with the
    code that evaluates the couplings it kept."""

    from ufo_model_loader.model import SerializableCoupling

    serial = SerializableCoupling.from_coupling(coupling)
    return {
        "name": str(serial.name),
        "expression": str(serial.expression),
        "orders": [[str(order), int(power)] for order, power in serial.orders],
        "value": None if serial.value is None else list(serial.value),
    }


def removed_coupling_records_from_payload(
    value: object,
) -> tuple[dict[str, Any], ...]:
    """The removed-coupling records of a compiled-model payload (validated)."""

    records = []
    for item in _sequence(value):
        record = _mapping(item)
        name, expression, orders = (
            record.get("name"),
            record.get("expression"),
            record.get("orders"),
        )
        if not isinstance(name, str) or not name or not isinstance(expression, str):
            raise ValueError("a removed coupling needs a name and an expression")
        records.append(
            {
                "name": name,
                "expression": expression,
                "orders": [
                    [str(_sequence(pair)[0]), int(_sequence(pair)[1])]
                    for pair in _sequence(orders)
                ],
                "value": (
                    None
                    if record.get("value") is None
                    else [float(component) for component in _sequence(record["value"])]
                ),
            }
        )
    names = [record["name"] for record in records]
    if names != sorted(set(names)):
        raise ValueError("removed couplings must be sorted and unique")
    return tuple(records)


@dataclass(frozen=True)
class RevivedCoupling:
    """A removed coupling a transform is not proven to leave zero
    (``revived_removed_couplings``): ``value`` in the transform's own binary64
    arithmetic (for the message only); ``parameters``, the external
    parameters it reads after the transform."""

    name: str
    value: complex
    parameters: tuple[str, ...] = ()

    @property
    def revived(self) -> bool:
        """Nonzero even in binary64 (otherwise only not proven zero)."""

        return self.value != 0

    def describe(self) -> str:
        if self.revived:
            return f"{self.name} = {_format_complex(self.value)}"
        if self.parameters:
            return (
                f"{self.name} (zero in binary64 here, but not identically in "
                f"{', '.join(self.parameters)}: a binding would revive it)"
            )
        return (
            f"{self.name} (zero in binary64 here, but not proven exactly zero: "
            "an exact carrier would evaluate it)"
        )


#: The literal readings of an exact carrier: a binary64 literal as its
#: shortest decimal (the one-loop runtime, extended precision) and as the
#: exact value of the binary64 (the native tree runtime promotes it).
_LITERAL_READINGS = ("decimal", "binary64")


def revived_removed_couplings(
    model: Any, removed: Iterable[Any]
) -> tuple[RevivedCoupling, ...]:
    """The couplings of ``removed`` that a parameter transform is not proven
    to leave zero.

    ``model`` is the ``ufo_model_loader`` model of a compiled model's tree
    payload after the transform (its parameters redefined and its values
    evaluated again); ``removed`` are the couplings restriction
    simplification removed (``removed_coupling_record``), as loader
    ``Coupling`` objects that went through the same transform as the kept
    couplings (their ``value`` set by its evaluation, for the message).

    The decision is exact, never numerical: a removed coupling stays removed
    only if it is provably zero for every binding, in every exact reading
    (``provably_zero_after_transform``). Its expression is written in the
    external (mutable) parameters, which stay symbols, through the
    transformed internal definitions (CMSParam = 1, a Yukawa input = its
    mass, a complex pole mass ``sqrt(M^2 - i M W)``), every internal constant
    and binary64 literal read both as its shortest decimal and as the exact
    binary64, and the result must expand to exactly 0. What the expansion
    cannot reduce is not proven, and refused: a square root of a non-square
    (``sqrt(10000000000000001) - 100000000``, zero in binary64 only), a
    branch identity Symbolica does not take (``sqrt(x^2) = x``), the
    conjugate of a real runtime parameter (``conj(MT) - MT``: the externals
    are complex symbols here), a model function it cannot reduce (a
    ``reglog`` of a non-trivial argument), an unresolved name. A term zero at the transformed values but not identically
    (a binding would revive it) is refused too: the transformed model holds
    no guard for it. Returned in ``removed``'s order."""

    environment: GuardEnvironment | None = None
    found = []
    for coupling in removed:
        value = complex(coupling.value if coupling.value is not None else math.nan)
        if environment is None:
            environment = GuardEnvironment.from_ufo_model(model)
            # A model variable that is not an exact integer (pi) stays a
            # symbol: no binary64 value of a transcendental constant may
            # cancel a literal.
            for symbol, number in model.get_model_variables().items():
                number = complex(number)
                if not (number.real.is_integer() and number.imag.is_integer()):
                    environment.constants.pop(_short_name(symbol.get_name()), None)
        try:
            parameters = environment.mutable_dependencies(
                environment.resolve(coupling.expression)
            )
            proven = provably_zero_after_transform(environment, coupling.expression)
        except (TypeError, ValueError, ArithmeticError):
            parameters, proven = ("(unresolved)",), False
        if not proven:
            found.append(RevivedCoupling(str(coupling.name), value, parameters))
    return tuple(found)


def provably_zero_after_transform(
    environment: GuardEnvironment, expression: Any
) -> bool:
    """Whether ``expression`` is exactly zero for every value of the external
    parameters of ``environment`` (which stay symbols), under every reading
    of its numbers (``_LITERAL_READINGS``).

    Each reading resolves ``expression`` exactly (``_exact_resolution``): no
    binary64 arithmetic ever runs, so no cancellation in binary64 can make a
    term look zero; the result must then expand to exactly 0. Symbolica's
    expansion is sound here (it does not take ``sqrt(x^2)`` for ``x``), and
    incomplete: what it cannot reduce is not proven."""

    for reading in _LITERAL_READINGS:
        resolved = _exact_resolution(environment, expression, reading, {}, ())
        if resolved.expand().to_canonical_string() != "0":
            return False
    return True


def _exact_resolution(
    environment: GuardEnvironment,
    expression: Any,
    reading: str,
    memo: dict[str, Any],
    visiting: tuple[str, ...],
) -> Any:
    """``expression`` with every non-external parameter replaced, to any
    depth, by its definition or its value, every number read exactly
    (``_exact_numbers``, ``_exact_complex``) before anything is combined."""

    expression = _exact_numbers(
        _with_imaginary_unit(_as_expression(expression)), reading
    )
    replacements = []
    for symbol in expression.get_all_symbols(False):
        name = _short_name(symbol.get_name())
        if name in environment.externals:
            continue
        if name in environment.constants:
            replacements.append(
                (symbol, _exact_complex(environment.constants[name], reading))
            )
        elif name in environment.definitions:
            if name in visiting:
                raise ValueError(f"parameter {name!r} is defined in terms of itself")
            resolved = memo.get(name)
            if resolved is None:
                resolved = memo[name] = _exact_resolution(
                    environment,
                    environment.definitions[name],
                    reading,
                    memo,
                    (*visiting, name),
                )
            replacements.append((symbol, resolved))
    for source, replacement in replacements:
        expression = expression.replace(source, replacement)
    return expression


def _exact_complex(value: complex, reading: str) -> Any:
    """A binary64 complex number as an exact Symbolica number, its parts
    read as the shortest decimal (``"decimal"``) or the exact binary64."""

    from symbolica import E, Expression

    def part(component: float) -> Any:
        if not math.isfinite(component):
            raise ValueError("a non-finite number is not exact")
        exact = (
            exact_generation_value(component)
            if reading == "decimal"
            else Fraction(component)
        )
        return E(f"({exact.numerator}/{exact.denominator})")

    value = complex(value)
    if value.imag == 0.0:
        return part(value.real)
    return part(value.real) + part(value.imag) * Expression.I


def _exact_numbers(expression: Any, reading: str) -> Any:
    """``expression`` with every floating-point number (a binary64 literal
    the source parse kept as a float, real or imaginary) replaced by its
    exact value in ``reading``, read from its value, not from its printed
    digits (Symbolica prints 15)."""

    from symbolica import AtomType

    found: dict[str, Any] = {}

    def collect(atom: Any) -> None:
        kind = atom.get_type()
        if kind == AtomType.Num:
            text = atom.to_canonical_string()
            if ("." in text or "e" in text) and text not in found:
                found[text] = atom
            return
        if kind in (AtomType.Add, AtomType.Mul, AtomType.Pow, AtomType.Fn):
            for child in atom:
                collect(child)

    collect(expression)
    for atom in found.values():
        expression = expression.replace(
            atom, _exact_complex(complex(atom.evaluate({})), reading)
        )
    return expression


def _removed_coupling_guards(
    model: Any, removed: Sequence[Any]
) -> list[SpecializationGuard]:
    if not removed:
        return []
    environment = GuardEnvironment.from_ufo_model(model)
    guards = []
    for coupling in removed:
        guard = SpecializationGuard.vanishing(
            environment,
            coupling.expression,
            subject=f"coupling {coupling.name} removed by restriction simplification",
            producer=RESTRICTION_SIMPLIFICATION,
            message=(
                "generate the artifact at the new values, or compile the model "
                "with simplify=False"
            ),
        )
        if guard is not None:
            guards.append(guard)
    return guards
