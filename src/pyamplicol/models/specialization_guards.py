# SPDX-License-Identifier: 0BSD
"""Specialisation guards: conditions on runtime parameters under which what
generation dropped or simplified stays valid.

Generation specialises a model to the values its parameters have when it
runs. Restriction simplification removes a coupling whose value is zero at
the restriction card; a derived parameter that is real at its default may be
stored with one runtime component; a colour flow without diagrams is a zero
amplitude. Each is exact for every binding of the runtime (mutable)
parameters only when it holds identically. When it holds only at the
generation-time values, the producer records a guard: the condition, the
mutable parameters it depends on and a message. Every runtime binding
(``Runtime.set_model_parameters`` and the paths built on it, the exported
SDKs, the one-loop runtime's parameter check) evaluates the guards of its
artifact and refuses, applying nothing, a binding under which one fails.
Structural specialisations (no mutable dependence, or an identically
vanishing expression) record nothing.

A guard is

``kind``
    ``"vanishing"``: the expression is zero; ``"real"``: it is real.
``subject``, ``producer``, ``message``
    What was specialised, who specialised it and what to do instead.
``parameters``
    The mutable (external) parameters the condition depends on, sorted.
``generation_values``
    Their values at generation, for a parameter the runtime does not expose
    (it cannot change there).
``program``
    The condition's expression, written in ``parameters`` alone, as a
    post-order program over complex binary64 (``evaluate_program``). ``None``
    when the expression uses a function the program cannot represent: the
    guard then holds only while every parameter keeps its generation value.
``expression``
    The same expression as Symbolica text, for people.

The test, at a binding: the program gives the value ``E`` and a magnitude
bound ``S`` (the sum of the moduli of the terms, products of the bounds of
the factors, the modulus of a function's value), the scale of the rounding
error of evaluating ``E`` in binary64. ``"vanishing"`` holds iff
``|E| <= TOLERANCE * S``, ``"real"`` iff ``|Im E| <= TOLERANCE * S``, with
``TOLERANCE = 64 * 2**-53``: a value zero up to rounding holds, any other
fails. A guard holds at its generation values by construction (the producer
checks it).

Where guards live: ``CompiledModel.specialization_guards`` (the model's own,
for every process; compiled-model schema ``GUARDED_COMPILED_MODEL_SCHEMA_
VERSION`` when there is one) and the process artifacts'
``specialization_guards`` (a generation-time producer's, for that process).
An artifact with at least one guard stores them all in ``GUARD_FILE_PATH``
(payload role ``GUARD_PAYLOAD_ROLE``) and requires the runtime capability
``GUARD_RUNTIME_CAPABILITY``: a reader that does not evaluate guards refuses
the artifact instead of ignoring them.
"""

from __future__ import annotations

import cmath
import math
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

#: Where an artifact stores its guards, and the payload's role and kind.
GUARD_FILE_PATH = "model/specialization-guards.json"
GUARD_PAYLOAD_ROLE = "specialization-guards"
GUARD_FILE_KIND = "pyamplicol-specialization-guards"
GUARD_FILE_SCHEMA_VERSION = 1
#: Required by an artifact that records a guard (released readers refuse it).
GUARD_RUNTIME_CAPABILITY = "rusticol.specialization-guards.v1"
#: A value whose modulus (``"vanishing"``) or imaginary part (``"real"``) is
#: at most this many times its magnitude bound is zero up to rounding.
TOLERANCE = 64.0 * 2.0**-53
KINDS = ("vanishing", "real")
#: The refusal prefix of a binding that a guard rejects.
REFUSAL_PREFIX = "specialisation-guard"

#: Functions a program can evaluate (complex binary64, principal branches).
_UNARY_FUNCTIONS = {
    "sqrt": cmath.sqrt,
    "exp": cmath.exp,
    "log": cmath.log,
    "sin": cmath.sin,
    "cos": cmath.cos,
    "tan": cmath.tan,
    "asin": cmath.asin,
    "acos": cmath.acos,
    "atan": cmath.atan,
    "sinh": cmath.sinh,
    "cosh": cmath.cosh,
    "tanh": cmath.tanh,
    "conj": lambda value: value.conjugate(),
    "abs": lambda value: complex(abs(value), 0.0),
}
#: UFO spellings of the same functions.
_FUNCTION_ALIASES = {
    "complexconjugate": "conj",
    "cmath.sqrt": "sqrt",
}
#: Symbolica's own constants are spelled "\U0001d70b" (pi) and "\U0001d452" (e).
_PI_SYMBOL = "\U0001d70b"
_E_SYMBOL = "\U0001d452"
_CONSTANTS = {"I": 1j, "pi": math.pi, _PI_SYMBOL: math.pi, _E_SYMBOL: math.e}


class UnrepresentableExpression(ValueError):
    """An expression a guard program cannot represent."""


@dataclass(frozen=True)
class SpecializationGuard:
    kind: str
    subject: str
    producer: str
    parameters: tuple[str, ...]
    generation_values: Mapping[str, tuple[float, float]]
    program: tuple[tuple[object, ...], ...] | None
    expression: str
    message: str
    process_ids: tuple[str, ...] | None = field(default=None)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown specialisation-guard kind {self.kind!r}")
        if tuple(sorted(set(self.parameters))) != tuple(self.parameters):
            raise ValueError(
                "specialisation-guard parameters must be sorted and unique"
            )
        if set(self.generation_values) != set(self.parameters):
            raise ValueError(
                "specialisation-guard generation values must name its parameters"
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
        """The guard that ``expression`` stays zero, or ``None`` when it is zero
        for every binding (structural: nothing to record)."""

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
        """The guard that ``expression`` stays real, or ``None`` when it is real
        for every binding (no mutable dependence, or provably real in the
        environment's real parameters: ``is_real_for_every_binding``)."""

        return cls._build(
            "real",
            environment,
            expression,
            subject=subject,
            producer=producer,
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
        if kind == "vanishing" and _is_identically_zero(resolved):
            return None
        if kind == "real" and environment.is_real_for_every_binding(resolved):
            return None
        try:
            program: tuple[tuple[object, ...], ...] | None = compile_program(
                resolved, parameters, environment
            )
        except UnrepresentableExpression:
            program = None
        generation_values = {
            name: environment.generation_value(name) for name in parameters
        }
        guard = cls(
            kind=kind,
            subject=subject,
            producer=producer,
            parameters=parameters,
            generation_values=generation_values,
            program=program,
            expression=resolved.to_canonical_string(),
            message=message,
        )
        if program is not None and guard.failure({}) is not None:
            # The program disagrees with the producer's own evaluation at the
            # generation values (a different rounding): hold the parameters
            # at those values instead.
            guard = replace(guard, program=None)
        return guard

    def for_processes(self, process_ids: Iterable[str]) -> SpecializationGuard:
        return SpecializationGuard(
            kind=self.kind,
            subject=self.subject,
            producer=self.producer,
            parameters=self.parameters,
            generation_values=self.generation_values,
            program=self.program,
            expression=self.expression,
            message=self.message,
            process_ids=tuple(sorted(set(process_ids))),
        )

    # -- evaluation ---------------------------------------------------------------

    def failure(self, values: Mapping[str, complex]) -> str | None:
        """Why the guard fails at ``values`` (a parameter absent from it keeps
        its generation value), or ``None`` when it holds."""

        bound = [
            complex(values[name])
            if name in values
            else complex(*self.generation_values[name])
            for name in self.parameters
        ]
        if self.program is None:
            changed = [
                name
                for name, value in zip(self.parameters, bound, strict=True)
                if value != complex(*self.generation_values[name])
            ]
            if not changed:
                return None
            return (
                f"{', '.join(changed)} changed and the condition is not evaluable "
                "outside its generation values"
            )
        value, magnitude = evaluate_program(self.program, bound)
        if not (math.isfinite(value.real) and math.isfinite(value.imag)):
            return f"the condition evaluates to {value}"
        if self.kind == "vanishing":
            if abs(value) <= TOLERANCE * magnitude:
                return None
            return f"the dropped value is {_format_complex(value)}, not zero"
        if abs(value.imag) <= TOLERANCE * magnitude:
            return None
        return f"the value is {_format_complex(value)}, not real"

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
            "program": None
            if self.program is None
            else [list(instruction) for instruction in self.program],
            "expression": self.expression,
            "message": self.message,
        }
        if self.process_ids is not None:
            payload["process_ids"] = list(self.process_ids)
        return payload

    @staticmethod
    def from_dict(payload: Mapping[str, object]) -> SpecializationGuard:
        program = payload.get("program")
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
            program=None
            if program is None
            else tuple(tuple(instruction) for instruction in _sequence(program)),
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
    """The refusal message of ``binding`` (new values over ``current``; a
    parameter in neither keeps its generation value), or ``None`` when every
    guard holds. Only guards that depend on a bound parameter are evaluated."""

    values = dict(current or {})
    values.update(binding)
    failures = []
    for guard in guards:
        touched = sorted(set(guard.parameters) & set(binding))
        if not touched:
            continue
        failure = guard.failure(values)
        if failure is not None:
            failures.append(describe_failure(guard, touched, failure))
    if not failures:
        return None
    return "; ".join(failures)


def describe_failure(
    guard: SpecializationGuard, touched: Sequence[str], failure: str
) -> str:
    return (
        f"{REFUSAL_PREFIX}: binding {', '.join(touched)} invalidates a "
        f"{guard.kind} specialisation made at generation ({guard.subject}, "
        f"recorded by {guard.producer}): {failure}; {guard.message}"
    )


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


# -- programs ---------------------------------------------------------------------
#
# A program is a post-order list of instructions over a stack of
# (value, magnitude) pairs:
#   ["c", re, im]    push a constant
#   ["p", k]         push parameter k of the guard's ``parameters``
#   ["add", n]       pop n, push their sum (magnitude: sum of magnitudes)
#   ["mul", n]       pop n, push their product (magnitude: product)
#   ["pow"]          pop exponent, base; push base**exponent (an integer
#                    exponent n >= 0: magnitude**n; otherwise |value|)
#   ["fn", name]     pop one, push name(value) (magnitude |value|; conj and
#                    abs keep the argument's magnitude)


def compile_program(
    resolved: Any,
    parameters: Sequence[str],
    environment: GuardEnvironment | None = None,
) -> tuple[tuple[object, ...], ...]:
    index = {name: position for position, name in enumerate(parameters)}
    program: list[tuple[object, ...]] = []
    _emit(resolved, index, program, environment)
    return tuple(program)


def _emit(
    expression: Any,
    index: Mapping[str, int],
    program: list[tuple[object, ...]],
    environment: GuardEnvironment | None,
) -> None:
    from symbolica import AtomType

    kind = expression.get_type()
    if kind == AtomType.Num:
        value = complex(expression.evaluate({}))
        program.append(("c", float(value.real), float(value.imag)))
        return
    if kind == AtomType.Var:
        name = _short_name(expression.get_name())
        if name in index:
            program.append(("p", index[name]))
            return
        if name in _CONSTANTS:
            value = _CONSTANTS[name]
            program.append(("c", float(value.real), float(value.imag)))
            return
        raise UnrepresentableExpression(f"unresolved symbol {name!r}")
    children = list(expression)
    if kind == AtomType.Add or kind == AtomType.Mul:
        for child in children:
            _emit(child, index, program, environment)
        program.append(("add" if kind == AtomType.Add else "mul", len(children)))
        return
    if kind == AtomType.Pow:
        base, exponent = children
        if (
            base.get_type() == AtomType.Var
            and _short_name(base.get_name()) == _E_SYMBOL
        ):
            _emit(exponent, index, program, environment)
            program.append(("fn", "exp"))
            return
        _emit(base, index, program, environment)
        _emit(exponent, index, program, environment)
        program.append(("pow",))
        return
    if kind == AtomType.Fn:
        name = _short_name(expression.get_name())
        name = _FUNCTION_ALIASES.get(name, name)
        if name == "complex" and len(children) == 2:
            _emit(children[0], index, program, environment)
            _emit(children[1], index, program, environment)
            program.append(("c", 0.0, 1.0))
            program.append(("mul", 2))
            program.append(("add", 2))
            return
        if name in _UNARY_FUNCTIONS and len(children) == 1:
            _emit(children[0], index, program, environment)
            program.append(("fn", name))
            return
        raise UnrepresentableExpression(f"function {name!r} is not representable")
    raise UnrepresentableExpression(f"atom {kind!r} is not representable")


def evaluate_program(
    program: Sequence[Sequence[object]], parameters: Sequence[complex]
) -> tuple[complex, float]:
    """The value and magnitude bound of ``program`` at ``parameters``."""

    stack: list[tuple[complex, float]] = []
    for instruction in program:
        op = instruction[0]
        if op == "c":
            value = complex(float(instruction[1]), float(instruction[2]))
            stack.append((value, abs(value)))
        elif op == "p":
            value = complex(parameters[int(instruction[1])])
            stack.append((value, abs(value)))
        elif op == "add" or op == "mul":
            count = int(instruction[1])
            if count < 1 or count > len(stack):
                raise ValueError("invalid specialisation-guard program")
            operands = stack[-count:]
            del stack[-count:]
            if op == "add":
                total = complex(0.0, 0.0)
                magnitude = 0.0
                for value, bound in operands:
                    total += value
                    magnitude += bound
            else:
                total = complex(1.0, 0.0)
                magnitude = 1.0
                for value, bound in operands:
                    total *= value
                    magnitude *= bound
            stack.append((total, magnitude))
        elif op == "pow":
            if len(stack) < 2:
                raise ValueError("invalid specialisation-guard program")
            exponent, _ = stack.pop()
            base, base_bound = stack.pop()
            integral = exponent.imag == 0.0 and exponent.real == math.floor(
                exponent.real
            )
            if integral and abs(exponent.real) <= 64:
                power = int(exponent.real)
                value = _integer_power(base, power)
                bound = base_bound**power if power >= 0 else abs(value)
            else:
                value = _complex_power(base, exponent)
                bound = abs(value)
            stack.append((value, bound))
        elif op == "fn":
            if not stack:
                raise ValueError("invalid specialisation-guard program")
            argument, bound = stack.pop()
            name = str(instruction[1])
            function = _UNARY_FUNCTIONS.get(name)
            if function is None:
                raise ValueError(f"unknown specialisation-guard function {name!r}")
            value = complex(function(argument))
            stack.append((value, bound if name in ("conj", "abs") else abs(value)))
        else:
            raise ValueError(f"unknown specialisation-guard instruction {op!r}")
    if len(stack) != 1:
        raise ValueError("invalid specialisation-guard program")
    return stack[0]


def _integer_power(base: complex, power: int) -> complex:
    if power < 0:
        return (
            1.0 / _integer_power(base, -power) if base != 0 else complex(math.inf, 0.0)
        )
    result = complex(1.0, 0.0)
    factor = base
    while power:
        if power & 1:
            result *= factor
        factor *= factor
        power >>= 1
    return result


def _complex_power(base: complex, exponent: complex) -> complex:
    if base == 0:
        return complex(0.0, 0.0) if exponent.real > 0 else complex(math.inf, 0.0)
    if exponent == 0.5:
        return cmath.sqrt(base)
    return cmath.exp(exponent * cmath.log(base))


# -- helpers ----------------------------------------------------------------------


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
) -> tuple[Any, Any, tuple[SpecializationGuard, ...]]:
    """``load_model(*args, **kwargs)`` of ``ufo_model_loader`` and the guards
    of the couplings its restriction simplification removed.

    The simplification (``Model.remove_zero_couplings``) removes every
    coupling whose value at the restriction card is zero. A removed coupling
    is a structural zero when it vanishes identically once the remaining
    internal parameters are written in the external (mutable) ones, the
    externals the card set to zero being the constant ``ZERO``; otherwise it
    is zero only at the card's values, and its guard ("vanishing") refuses a
    binding that revives it."""

    from ufo_model_loader import model as ufo_model

    original = ufo_model.Model.remove_zero_couplings
    captured: list[SpecializationGuard] = []

    def remove_zero_couplings(self: Any) -> Any:
        removed = original(self)
        captured.extend(_removed_coupling_guards(self, removed[0]))
        return removed

    with _CAPTURE_LOCK:
        ufo_model.Model.remove_zero_couplings = remove_zero_couplings
        try:
            model, card = load_model(*args, **kwargs)
        finally:
            ufo_model.Model.remove_zero_couplings = original
    unique = {guard.subject: guard for guard in captured}
    return model, card, tuple(unique[subject] for subject in sorted(unique))


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
