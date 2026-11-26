// SPDX-License-Identifier: 0BSD
//! Specialisation guards: the runtime parameters an artifact holds at their
//! generation values because generation specialised to those values
//! (`pyamplicol.models.specialization_guards` writes them; this module is its
//! checking twin).
//!
//! An artifact that records a guard lists `model/specialization-guards.json`
//! with the payload role `specialization-guards`. A guard holds only while
//! every parameter it names keeps exactly its generation value: the binary64
//! value (both components) the artifact recorded, compared with the value as
//! bound, in the precision the binding has (a tree binding is binary64; the
//! one-loop runtime compares its exact rationals with the exact value of the
//! recorded binary64). No numerical test accepts a changed value. Every
//! runtime binding (`NativeRuntime::set_model_parameters` and everything
//! built on it: the Python runtime, the C ABI and the SDKs, a model-parameter
//! file at load; the one-loop runtime's parameter setter) checks the guards of
//! its process before anything is applied, and a binding that changes a
//! guarded parameter is refused with a model-parameter error that names the
//! parameters, the specialisation and its producer.

use std::collections::BTreeMap;

use num_complex::Complex64;
use serde::Deserialize;

use crate::{PayloadRole, RusticolError, RusticolResult};

/// The kind of the payload, its schema and the refusal prefix.
pub const GUARD_FILE_KIND: &str = "pyamplicol-specialization-guards";
pub const GUARD_FILE_SCHEMA_VERSION: u32 = 1;
pub const REFUSAL_PREFIX: &str = "specialisation-guard";

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

/// How a binding treats one guarded parameter.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Bound {
    /// The binding does not set the parameter.
    Untouched,
    /// The binding sets it to exactly its generation value.
    Unchanged,
    /// The binding sets it to another value (described for the refusal).
    Changed,
}

/// One recorded guard.
#[derive(Clone, Debug)]
pub struct SpecializationGuard {
    kind: GuardKind,
    subject: String,
    producer: String,
    parameters: Vec<String>,
    generation_values: Vec<Complex64>,
    /// The exact decimals the producer recorded (real, imaginary), as text:
    /// exact readers parse them; nothing here formats a float to obtain them.
    generation_exact: Vec<[String; 2]>,
    message: String,
    process_ids: Option<Vec<String>>,
}

/// One guarded parameter as a binding check sees it.
#[derive(Clone, Copy, Debug)]
pub struct GuardedParameter<'a> {
    pub name: &'a str,
    /// The recorded binary64 value.
    pub generation: Complex64,
    /// The producer's exact decimal text of it (real, imaginary).
    pub exact: &'a [String; 2],
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GuardWire {
    kind: GuardKind,
    subject: String,
    producer: String,
    parameters: Vec<String>,
    generation_values: BTreeMap<String, [f64; 2]>,
    generation_exact: BTreeMap<String, [String; 2]>,
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
        if wire.parameters.is_empty() {
            return Err(invalid("a guard holds at least one parameter"));
        }
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
                let [re, im] = wire
                    .generation_values
                    .get(name)
                    .ok_or_else(|| invalid(format!("no generation value of {name:?}")))?;
                if !(re.is_finite() && im.is_finite()) {
                    return Err(invalid(format!(
                        "generation value of {name:?} is not finite"
                    )));
                }
                Ok(Complex64::new(*re, *im))
            })
            .collect::<RusticolResult<Vec<_>>>()?;
        if wire.generation_exact.len() != wire.parameters.len() {
            return Err(invalid("exact generation values must name the parameters"));
        }
        let generation_exact = wire
            .parameters
            .iter()
            .zip(&generation_values)
            .map(|(name, generation)| {
                let texts = wire
                    .generation_exact
                    .get(name)
                    .ok_or_else(|| invalid(format!("no exact generation value of {name:?}")))?;
                // The exact decimal rounds to the recorded binary64 (Rust's
                // parse is correctly rounded): a record whose two values
                // disagree is refused.
                let parsed = texts
                    .iter()
                    .map(|text| text.trim().parse::<f64>())
                    .collect::<Result<Vec<_>, _>>()
                    .map_err(|_| invalid(format!("exact value of {name:?} is not a decimal")))?;
                if parsed[0] != generation.re || parsed[1] != generation.im {
                    return Err(invalid(format!(
                        "exact value of {name:?} does not round to its binary64 value"
                    )));
                }
                Ok(texts.clone())
            })
            .collect::<RusticolResult<Vec<_>>>()?;
        Ok(Self {
            kind: wire.kind,
            subject: wire.subject,
            producer: wire.producer,
            parameters: wire.parameters,
            generation_values,
            generation_exact,
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

    /// The guarded parameters with their generation values (binary64 and
    /// the producer's exact decimal text).
    pub fn guarded(&self) -> impl Iterator<Item = GuardedParameter<'_>> {
        self.parameters
            .iter()
            .zip(&self.generation_values)
            .zip(&self.generation_exact)
            .map(|((name, generation), exact)| GuardedParameter {
                name,
                generation: *generation,
                exact,
            })
    }

    fn refusal(&self, changed: &[String]) -> String {
        format!(
            "{REFUSAL_PREFIX}: binding {} invalidates a {} specialisation made at generation ({}, recorded by {}): {}; the artifact holds this parameter at its generation value; {}",
            changed
                .iter()
                .map(|entry| entry.split(' ').next().unwrap_or(entry))
                .collect::<Vec<_>>()
                .join(", "),
            self.kind.as_str(),
            self.subject,
            self.producer,
            changed.join(", "),
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

    pub fn guards(&self) -> &[SpecializationGuard] {
        &self.guards
    }

    /// Check a binary64 binding (`binding`: the new values by name) before it
    /// is applied: a guarded parameter it sets must keep exactly its
    /// generation value (both components; `==` on binary64, so `-0.0` equals
    /// `0.0`).
    pub fn check_binding(&self, binding: &BTreeMap<String, (f64, f64)>) -> RusticolResult<()> {
        self.check_with(|parameter| match binding.get(parameter.name) {
            None => (Bound::Untouched, String::new()),
            Some(&(re, im)) if re == parameter.generation.re && im == parameter.generation.im => {
                (Bound::Unchanged, String::new())
            }
            Some(&(re, im)) => (Bound::Changed, format_complex(Complex64::new(re, im))),
        })
    }

    /// Check a binding through `bound(parameter)`, which says whether the
    /// binding leaves the parameter untouched, sets it to exactly its
    /// generation value (in the binding's own precision: an exact binding
    /// compares with `parameter.exact`, a binary64 one with
    /// `parameter.generation`), or changes it (with a description of the new
    /// value).
    pub fn check_with(
        &self,
        bound: impl Fn(GuardedParameter<'_>) -> (Bound, String),
    ) -> RusticolResult<()> {
        let mut failures = Vec::new();
        for guard in &self.guards {
            let changed = guard
                .guarded()
                .filter_map(|parameter| match bound(parameter) {
                    (Bound::Changed, value) => Some(format!(
                        "{} = {value} (generated at {})",
                        parameter.name, parameter.exact[0]
                    )),
                    _ => None,
                })
                .collect::<Vec<_>>();
            if !changed.is_empty() {
                failures.push(guard.refusal(&changed));
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
