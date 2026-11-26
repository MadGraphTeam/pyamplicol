// SPDX-License-Identifier: 0BSD
//! Specialisation guards: conditions on runtime parameters under which what
//! generation dropped or simplified stays valid (`pyamplicol.models.
//! specialization_guards` writes them; this module is its evaluating twin).
//!
//! An artifact that records a guard lists `model/specialization-guards.json`
//! with the payload role `specialization-guards`. Every runtime binding
//! (`NativeRuntime::set_model_parameters` and everything built on it: the
//! Python runtime, the C ABI and the SDKs, a model-parameter file at load)
//! evaluates the guards of its process before anything is applied, and a
//! binding under which one fails is refused with a model-parameter error that
//! names the parameters, the specialisation and its producer.
//!
//! A guard's `program` evaluates its condition's expression `E` in complex
//! binary64 together with a magnitude bound `S` (sums add the bounds of their
//! terms, products multiply those of their factors, a function's bound is the
//! modulus of its value). `"vanishing"` holds iff `|E| <= TOLERANCE * S`,
//! `"real"` iff `|Im E| <= TOLERANCE * S`: zero (or real) up to rounding.
//! A guard without a program holds only while each of its parameters keeps
//! its generation value.

use std::collections::BTreeMap;

use num_complex::Complex64;
use serde::Deserialize;
use serde_json::Value;

use crate::{PayloadRole, RusticolError, RusticolResult};

/// The kind of the payload, its schema and the refusal prefix.
pub const GUARD_FILE_KIND: &str = "pyamplicol-specialization-guards";
pub const GUARD_FILE_SCHEMA_VERSION: u32 = 1;
pub const REFUSAL_PREFIX: &str = "specialisation-guard";
/// A value whose modulus (`vanishing`) or imaginary part (`real`) is at most
/// this many times its magnitude bound is zero up to rounding.
pub const TOLERANCE: f64 = 64.0 * f64::EPSILON / 2.0;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "kebab-case")]
pub enum GuardKind {
    Vanishing,
    Real,
}

impl GuardKind {
    const fn as_str(self) -> &'static str {
        match self {
            Self::Vanishing => "vanishing",
            Self::Real => "real",
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
enum Instruction {
    Constant(Complex64),
    Parameter(usize),
    Add(usize),
    Mul(usize),
    Pow,
    Function(Function),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Function {
    Sqrt,
    Exp,
    Log,
    Sin,
    Cos,
    Tan,
    Asin,
    Acos,
    Atan,
    Sinh,
    Cosh,
    Tanh,
    Conj,
    Abs,
}

impl Function {
    fn parse(name: &str) -> Option<Self> {
        Some(match name {
            "sqrt" => Self::Sqrt,
            "exp" => Self::Exp,
            "log" => Self::Log,
            "sin" => Self::Sin,
            "cos" => Self::Cos,
            "tan" => Self::Tan,
            "asin" => Self::Asin,
            "acos" => Self::Acos,
            "atan" => Self::Atan,
            "sinh" => Self::Sinh,
            "cosh" => Self::Cosh,
            "tanh" => Self::Tanh,
            "conj" => Self::Conj,
            "abs" => Self::Abs,
            _ => return None,
        })
    }

    fn apply(self, value: Complex64) -> Complex64 {
        match self {
            Self::Sqrt => value.sqrt(),
            Self::Exp => value.exp(),
            Self::Log => value.ln(),
            Self::Sin => value.sin(),
            Self::Cos => value.cos(),
            Self::Tan => value.tan(),
            Self::Asin => value.asin(),
            Self::Acos => value.acos(),
            Self::Atan => value.atan(),
            Self::Sinh => value.sinh(),
            Self::Cosh => value.cosh(),
            Self::Tanh => value.tanh(),
            Self::Conj => value.conj(),
            Self::Abs => Complex64::new(value.norm(), 0.0),
        }
    }

    /// Conjugation and modulus keep their argument's bound.
    const fn keeps_bound(self) -> bool {
        matches!(self, Self::Conj | Self::Abs)
    }
}

/// One recorded guard.
#[derive(Clone, Debug)]
pub struct SpecializationGuard {
    kind: GuardKind,
    subject: String,
    producer: String,
    parameters: Vec<String>,
    generation_values: Vec<Complex64>,
    program: Option<Vec<Instruction>>,
    message: String,
    process_ids: Option<Vec<String>>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GuardWire {
    kind: GuardKind,
    subject: String,
    producer: String,
    parameters: Vec<String>,
    generation_values: BTreeMap<String, [f64; 2]>,
    program: Option<Vec<Vec<Value>>>,
    expression: String,
    message: String,
    #[serde(default)]
    process_ids: Option<Vec<String>>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GuardFileWire {
    kind: String,
    schema_version: u32,
    guards: Vec<GuardWire>,
}

fn invalid(message: impl Into<String>) -> RusticolError {
    RusticolError::artifact(format!("specialisation-guard record: {}", message.into()))
}

impl SpecializationGuard {
    fn from_wire(wire: GuardWire) -> RusticolResult<Self> {
        let _informational = wire.expression;
        if wire.parameters.windows(2).any(|pair| pair[0] >= pair[1]) {
            return Err(invalid("parameters must be sorted and unique"));
        }
        if wire.generation_values.len() != wire.parameters.len() {
            return Err(invalid("generation values must name the parameters"));
        }
        let generation_values = wire
            .parameters
            .iter()
            .map(|name| {
                wire.generation_values
                    .get(name)
                    .map(|[re, im]| Complex64::new(*re, *im))
                    .ok_or_else(|| invalid(format!("no generation value of {name:?}")))
            })
            .collect::<RusticolResult<Vec<_>>>()?;
        let program = wire
            .program
            .map(|program| parse_program(&program, wire.parameters.len()))
            .transpose()?;
        Ok(Self {
            kind: wire.kind,
            subject: wire.subject,
            producer: wire.producer,
            parameters: wire.parameters,
            generation_values,
            program,
            message: wire.message,
            process_ids: wire.process_ids,
        })
    }

    /// Whether this guard applies to the stored process `process_id`.
    fn applies_to(&self, process_id: &str) -> bool {
        self.process_ids
            .as_ref()
            .is_none_or(|ids| ids.iter().any(|id| id == process_id))
    }

    pub fn parameters(&self) -> &[String] {
        &self.parameters
    }

    /// Why the guard fails at `values` (one per parameter, in order), or
    /// `None` when it holds.
    pub fn failure(&self, values: &[Complex64]) -> Option<String> {
        let Some(program) = &self.program else {
            let changed = self
                .parameters
                .iter()
                .zip(values.iter().zip(&self.generation_values))
                .filter(|(_, (value, generation))| value != generation)
                .map(|(name, _)| name.as_str())
                .collect::<Vec<_>>();
            if changed.is_empty() {
                return None;
            }
            return Some(format!(
                "{} changed and the condition is not evaluable outside its generation values",
                changed.join(", ")
            ));
        };
        let (value, bound) = match evaluate_program(program, values) {
            Ok(result) => result,
            Err(error) => return Some(error),
        };
        if !(value.re.is_finite() && value.im.is_finite()) {
            return Some(format!("the condition evaluates to {value}"));
        }
        match self.kind {
            GuardKind::Vanishing if value.norm() <= TOLERANCE * bound => None,
            GuardKind::Vanishing => Some(format!(
                "the dropped value is {}, not zero",
                format_complex(value)
            )),
            GuardKind::Real if value.im.abs() <= TOLERANCE * bound => None,
            GuardKind::Real => Some(format!("the value is {}, not real", format_complex(value))),
        }
    }

    fn refusal(&self, touched: &[&str], failure: &str) -> String {
        format!(
            "{REFUSAL_PREFIX}: binding {} invalidates a {} specialisation made at generation ({}, recorded by {}): {failure}; {}",
            touched.join(", "),
            self.kind.as_str(),
            self.subject,
            self.producer,
            self.message
        )
    }
}

fn format_complex(value: Complex64) -> String {
    if value.im == 0.0 {
        format!("{:?}", value.re)
    } else {
        format!("({:?}{:+?}j)", value.re, value.im)
    }
}

fn parse_program(
    program: &[Vec<Value>],
    parameter_count: usize,
) -> RusticolResult<Vec<Instruction>> {
    let mut depth = 0usize;
    let mut instructions = Vec::with_capacity(program.len());
    for instruction in program {
        let op = instruction
            .first()
            .and_then(Value::as_str)
            .ok_or_else(|| invalid("an instruction has no operation"))?;
        let number = |index: usize| {
            instruction
                .get(index)
                .and_then(Value::as_f64)
                .ok_or_else(|| invalid(format!("instruction {op:?} lacks operand {index}")))
        };
        let count = |index: usize| {
            instruction
                .get(index)
                .and_then(Value::as_u64)
                .and_then(|value| usize::try_from(value).ok())
                .ok_or_else(|| invalid(format!("instruction {op:?} lacks its count")))
        };
        let (parsed, arity, expected_length) = match op {
            "c" => (
                Instruction::Constant(Complex64::new(number(1)?, number(2)?)),
                0,
                3,
            ),
            "p" => {
                let index = count(1)?;
                if index >= parameter_count {
                    return Err(invalid("a parameter index is out of range"));
                }
                (Instruction::Parameter(index), 0, 2)
            }
            "add" | "mul" => {
                let n = count(1)?;
                if n == 0 {
                    return Err(invalid("an empty sum or product"));
                }
                let parsed = if op == "add" {
                    Instruction::Add(n)
                } else {
                    Instruction::Mul(n)
                };
                (parsed, n, 2)
            }
            "pow" => (Instruction::Pow, 2, 1),
            "fn" => {
                let name = instruction
                    .get(1)
                    .and_then(Value::as_str)
                    .ok_or_else(|| invalid("a function has no name"))?;
                let function = Function::parse(name)
                    .ok_or_else(|| invalid(format!("unknown function {name:?}")))?;
                (Instruction::Function(function), 1, 2)
            }
            _ => return Err(invalid(format!("unknown operation {op:?}"))),
        };
        if instruction.len() != expected_length {
            return Err(invalid(format!("instruction {op:?} has the wrong length")));
        }
        if depth < arity {
            return Err(invalid("an instruction reads past the stack"));
        }
        depth = depth - arity + 1;
        instructions.push(parsed);
    }
    if depth != 1 {
        return Err(invalid("a program must leave exactly one value"));
    }
    Ok(instructions)
}

fn evaluate_program(
    program: &[Instruction],
    parameters: &[Complex64],
) -> Result<(Complex64, f64), String> {
    let mut stack: Vec<(Complex64, f64)> = Vec::with_capacity(program.len());
    for instruction in program {
        match instruction {
            Instruction::Constant(value) => stack.push((*value, value.norm())),
            Instruction::Parameter(index) => {
                let value = parameters[*index];
                stack.push((value, value.norm()));
            }
            Instruction::Add(count) | Instruction::Mul(count) => {
                let operands = stack.split_off(stack.len() - count);
                let result = if matches!(instruction, Instruction::Add(_)) {
                    operands
                        .iter()
                        .fold((Complex64::new(0.0, 0.0), 0.0), |(sum, bound), (v, b)| {
                            (sum + v, bound + b)
                        })
                } else {
                    operands.iter().fold(
                        (Complex64::new(1.0, 0.0), 1.0),
                        |(product, bound), (v, b)| (product * v, bound * b),
                    )
                };
                stack.push(result);
            }
            Instruction::Pow => {
                let (exponent, _) = stack.pop().ok_or("invalid program")?;
                let (base, base_bound) = stack.pop().ok_or("invalid program")?;
                let integral = exponent.im == 0.0
                    && exponent.re == exponent.re.floor()
                    && exponent.re.abs() <= 64.0;
                let (value, bound) = if integral {
                    // The exponent is an integer of at most 64 in modulus.
                    #[allow(clippy::cast_possible_truncation)]
                    let power = exponent.re as i32;
                    let value = integer_power(base, power);
                    let bound = if power >= 0 {
                        base_bound.powi(power)
                    } else {
                        value.norm()
                    };
                    (value, bound)
                } else {
                    let value = complex_power(base, exponent);
                    (value, value.norm())
                };
                stack.push((value, bound));
            }
            Instruction::Function(function) => {
                let (argument, bound) = stack.pop().ok_or("invalid program")?;
                let value = function.apply(argument);
                let bound = if function.keeps_bound() {
                    bound
                } else {
                    value.norm()
                };
                stack.push((value, bound));
            }
        }
    }
    stack.pop().ok_or_else(|| "invalid program".to_string())
}

/// `base**power` by repeated squaring, as the Python twin computes it.
fn integer_power(base: Complex64, power: i32) -> Complex64 {
    if power < 0 {
        if base == Complex64::new(0.0, 0.0) {
            return Complex64::new(f64::INFINITY, 0.0);
        }
        return Complex64::new(1.0, 0.0) / integer_power(base, -power);
    }
    let mut result = Complex64::new(1.0, 0.0);
    let mut factor = base;
    let mut remaining = power;
    while remaining != 0 {
        if remaining & 1 == 1 {
            result *= factor;
        }
        factor *= factor;
        remaining >>= 1;
    }
    result
}

fn complex_power(base: Complex64, exponent: Complex64) -> Complex64 {
    if base == Complex64::new(0.0, 0.0) {
        return if exponent.re > 0.0 {
            Complex64::new(0.0, 0.0)
        } else {
            Complex64::new(f64::INFINITY, 0.0)
        };
    }
    if exponent == Complex64::new(0.5, 0.0) {
        return base.sqrt();
    }
    (exponent * base.ln()).exp()
}

/// The guards of one loaded process.
#[derive(Clone, Debug, Default)]
pub struct SpecializationGuards {
    guards: Vec<SpecializationGuard>,
}

impl SpecializationGuards {
    /// Parse a `model/specialization-guards.json` payload and keep the guards
    /// of the stored process `process_id`.
    pub fn parse(bytes: &[u8], process_id: &str) -> RusticolResult<Self> {
        let wire: GuardFileWire = serde_json::from_slice(bytes)
            .map_err(|error| invalid(format!("could not parse it: {error}")))?;
        if wire.kind != GUARD_FILE_KIND {
            return Err(invalid(format!("unexpected kind {:?}", wire.kind)));
        }
        if wire.schema_version != GUARD_FILE_SCHEMA_VERSION {
            return Err(invalid(format!(
                "unsupported schema version {}",
                wire.schema_version
            )));
        }
        let guards = wire
            .guards
            .into_iter()
            .map(SpecializationGuard::from_wire)
            .filter(|guard| {
                guard
                    .as_ref()
                    .map_or(true, |guard| guard.applies_to(process_id))
            })
            .collect::<RusticolResult<Vec<_>>>()?;
        Ok(Self { guards })
    }

    /// The guards an authenticated artifact records for the stored process
    /// `process_id` (none without a guard payload).
    pub fn load(artifact: &crate::VerifiedArtifact, process_id: &str) -> RusticolResult<Self> {
        let mut records = artifact
            .manifest()
            .payloads
            .iter()
            .filter(|payload| payload.role == PayloadRole::SpecializationGuards);
        let Some(record) = records.next() else {
            return Ok(Self::default());
        };
        if records.next().is_some() {
            return Err(invalid("an artifact has at most one guard payload"));
        }
        Self::parse(&artifact.read_payload(&record.path)?, process_id)
    }

    pub fn is_empty(&self) -> bool {
        self.guards.is_empty()
    }

    pub fn len(&self) -> usize {
        self.guards.len()
    }

    /// Check a binding (`binding`: the new values by name) before it is
    /// applied: every guard that depends on a bound parameter is evaluated at
    /// the binding over the current values (`current`: a parameter it does not
    /// know keeps its generation value). The refusal names every failing
    /// guard.
    pub fn check_binding(
        &self,
        binding: &BTreeMap<String, (f64, f64)>,
        current: impl Fn(&str) -> Option<(f64, f64)>,
    ) -> RusticolResult<()> {
        let mut failures = Vec::new();
        for guard in &self.guards {
            let touched = guard
                .parameters
                .iter()
                .filter(|name| binding.contains_key(name.as_str()))
                .map(String::as_str)
                .collect::<Vec<_>>();
            if touched.is_empty() {
                continue;
            }
            let values = guard
                .parameters
                .iter()
                .zip(&guard.generation_values)
                .map(|(name, generation)| {
                    binding
                        .get(name)
                        .copied()
                        .or_else(|| current(name))
                        .map_or(*generation, |(re, im)| Complex64::new(re, im))
                })
                .collect::<Vec<_>>();
            if let Some(failure) = guard.failure(&values) {
                failures.push(guard.refusal(&touched, &failure));
            }
        }
        if failures.is_empty() {
            Ok(())
        } else {
            Err(RusticolError::model_parameter(failures.join("; ")))
        }
    }
}

#[cfg(test)]
#[path = "specialization_guards_tests.rs"]
mod tests;
