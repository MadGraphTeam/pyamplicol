// SPDX-License-Identifier: 0BSD

//! Coherent bare one-loop amplitudes for momentum-independent, color-singlet
//! scalar theories. FeynKit owns diagrams and their factors; NinjaRS and OneLOop
//! own numerical reduction. No Born contraction is used during preparation.
//!
//! The returned coefficients use the existing MadLoop/BLHA C-epsilon-stripped
//! convention: multiply Ninja's integral by `i/(16*pi^2)`. They are bare Laurent
//! coefficients, without UV counterterms or infrared remainder conversion.
//! In particular, the finite coefficient is not an NSC `R1`, and its absolute
//! square is not a finite one-loop norm. See the retained convention derivation
//! in the normalization section of `src/pyamplicol/loops/v2/conventions.py`.
//! Amplitudes are unaveraged, with labelled external legs. Flux factors and
//! identical-final-state phase-space factors belong to the consumer.

mod preparation;
#[cfg(test)]
mod tests;

use std::{
    collections::{BTreeMap, BTreeSet},
    sync::Arc,
};

use feynkit_generator::{GenerationOptions, Process};
use feynkit_model::{Model, ParameterCard};
use rusticol_core::{RusticolError, RusticolResult};
use symbolica::atom::{Atom, Symbol};

use crate::{
    Complex,
    runtime::{
        Arithmetic, Batch, BatchCarrier, CoefficientEvaluator, Data, PolynomialPlan,
        arithmetic_mode,
    },
};

fn error(message: impl std::fmt::Display) -> RusticolError {
    RusticolError::invalid_argument(format!("native scalar loop: {message}"))
}

/// Immutable exact program. Each diagram retains its full complex coefficient.
pub struct ScalarLoopProgram {
    prepared: preparation::PreparedScalarLoop,
}

impl ScalarLoopProgram {
    /// Prepare the declared scalar class; unsupported model structures fail
    /// explicitly. Exact scalar bindings are fixed for this prepared program.
    pub fn prepare(
        model: Arc<Model>,
        process: &Process,
        options: &GenerationOptions,
        card: Option<&ParameterCard>,
        exact_overrides: &BTreeMap<Symbol, Atom>,
    ) -> RusticolResult<Self> {
        let prepared = preparation::prepare(model, process, options, card, exact_overrides)?;
        if prepared.diagrams.is_empty() {
            return Err(RusticolError::unsupported_runtime_capability(
                "native-scalar-loop",
                "no supported one-loop diagrams were generated",
            ));
        }
        Ok(Self { prepared })
    }

    pub fn momentum_legs(&self) -> &[usize] {
        &self.prepared.momentum_legs
    }
    pub fn diagram_count(&self) -> usize {
        self.prepared.diagrams.len()
    }

    /// Create independent evaluator/reducer state at the requested precision.
    pub fn evaluator(
        &self,
        arithmetic: &str,
        precision: Option<u32>,
    ) -> RusticolResult<ScalarLoopEvaluator> {
        let (arithmetic, bits) = arithmetic_mode(arithmetic, precision).map_err(error)?;
        self.evaluator_with_precision_bits(arithmetic, bits)
    }

    /// Use the exact working-bit context throughout coefficients, normalization,
    /// sampling and reduction, without decimal conversion or hidden guard bits.
    pub fn evaluator_with_precision_bits(
        &self,
        arithmetic: Arithmetic,
        bits: u32,
    ) -> RusticolResult<ScalarLoopEvaluator> {
        let coefficients = CoefficientEvaluator::with_precision_bits(
            &self.prepared.evaluator_state,
            arithmetic,
            bits,
        )
        .map_err(error)?;
        let mut diagrams = Vec::with_capacity(self.diagram_count());
        for layout in &self.prepared.diagrams {
            diagrams.push((
                layout.offset,
                layout.propagators,
                PolynomialPlan::with_precision_bits(
                    layout.propagators,
                    ["a".into(), "0".into(), "0".into()],
                    vec!["a".into()],
                    arithmetic,
                    bits,
                    "generic",
                )
                .map_err(error)?,
            ));
        }
        Ok(ScalarLoopEvaluator {
            coefficients,
            diagrams,
            momentum_columns: self.momentum_legs().len() * 4,
        })
    }
}

/// Per-worker mutable execution state; no global numeric compilation is needed.
pub struct ScalarLoopEvaluator {
    coefficients: CoefficientEvaluator,
    diagrams: Vec<(usize, usize, PolynomialPlan)>,
    momentum_columns: usize,
}

/// Full coherent complex bare Laurent coefficients, ordered finite, 1/epsilon,
/// 1/epsilon^2. Only lanes successful in every diagram have numerical values.
pub struct BareScalarLoopBatch {
    statuses: Vec<(u64, String)>,
    values: Batch,
}

impl BareScalarLoopBatch {
    pub fn statuses(&self) -> &[(u64, String)] {
        &self.statuses
    }
    pub fn successful_values(&self) -> &Batch {
        &self.values
    }
}

fn validate_real<T: BatchCarrier>(values: &[Complex<T>], positive: bool) -> bool {
    values.iter().all(|value| {
        value.re.is_finite()
            && value.im.is_finite()
            && value.im == value.im.zero()
            && (!positive || value.re > value.re.zero())
    })
}

fn physical_input(batch: &Batch, positive: bool) -> bool {
    match batch.data() {
        Data::Double(values) => validate_real(values, positive),
        Data::DoubleDouble(values) => validate_real(values, positive),
        Data::Arbitrary(values) => validate_real(values, positive),
    }
}

fn empty_result(
    input: &Batch,
    statuses: Vec<(u64, String)>,
) -> RusticolResult<BareScalarLoopBatch> {
    let values = match input.data() {
        Data::Double(_) => Batch::typed::<f64>(vec![], vec![], 3, input.precision_bits()),
        Data::DoubleDouble(_) => Batch::typed::<symbolica::domains::float::DoubleFloat>(
            vec![],
            vec![],
            3,
            input.precision_bits(),
        ),
        Data::Arbitrary(_) => Batch::typed::<symbolica::domains::float::Float>(
            vec![],
            vec![],
            3,
            input.precision_bits(),
        ),
    }
    .map_err(error)?;
    Ok(BareScalarLoopBatch { statuses, values })
}

fn coherent_sum<T: BatchCarrier>(
    parts: &[&[Complex<T>]],
    ids: Vec<u64>,
    bits: u32,
) -> RusticolResult<Batch> {
    let first = parts
        .first()
        .ok_or_else(|| error("no diagram reductions"))?;
    if first.is_empty() {
        return Err(error("empty coherent sum"));
    }
    // A cancellation in a coefficient can lower its tracked reliability.
    // Constants and accumulators must start at the requested working precision,
    // independently of the first diagram or lane.
    let prototype = T::parse_decimal("0", bits).map_err(error)?;
    let pi = prototype.pi();
    let sixteen = T::parse_decimal("16", bits).map_err(error)?;
    let factor = prototype.one() / (sixteen * pi.clone() * pi);
    let zero = Complex::new(prototype.zero(), prototype.zero());
    let mut values = vec![zero; first.len()];
    for part in parts {
        if part.len() != values.len() {
            return Err(error("inconsistent diagram rows"));
        }
        for (sum, value) in values.iter_mut().zip(part.iter()) {
            // Multiply by i/(16*pi^2) without passing through binary64.
            sum.re = sum.re.clone() - value.im.clone() * factor.clone();
            sum.im = sum.im.clone() + value.re.clone() * factor.clone();
        }
    }
    Batch::typed(values, ids, 3, bits).map_err(error)
}

impl ScalarLoopEvaluator {
    /// Evaluate physical real momenta in `momentum_legs()` order (E,px,py,pz).
    /// `mu_squared` has one positive real value per identical lane identity.
    /// The caller owns signed momentum conservation: FeynKit routing eliminates
    /// dependent external momenta using that identity. Off-shell Green functions
    /// are supported; scattering callers additionally own on-shell validation.
    /// Failed coefficient or reduction lanes never expose partial diagram sums.
    pub fn evaluate_batch(
        &mut self,
        momenta: &Batch,
        mu_squared: &Batch,
    ) -> RusticolResult<BareScalarLoopBatch> {
        momenta.same_rows(mu_squared).map_err(error)?;
        if momenta.columns() != self.momentum_columns || mu_squared.columns() != 1 {
            return Err(error("momentum or renormalization-scale dimensions differ"));
        }
        if momenta.ids().iter().copied().collect::<BTreeSet<_>>().len() != momenta.rows() {
            return Err(error("duplicate lane identities"));
        }
        if !physical_input(momenta, false) || !physical_input(mu_squared, true) {
            return Err(error(
                "momenta must be finite and real; mu squared must be finite, real and positive",
            ));
        }
        if momenta.rows() == 0 {
            return empty_result(momenta, vec![]);
        }
        let coefficients = self.coefficients.evaluate_batch(momenta).map_err(error)?;
        let mut failures: BTreeMap<u64, String> = coefficients
            .nonfinite_rows()
            .into_iter()
            .map(|id| (id, "nonfinite prepared coefficient or pole".into()))
            .collect();
        let active_rows: Vec<_> = momenta
            .ids()
            .iter()
            .enumerate()
            .filter_map(|(row, id)| (!failures.contains_key(id)).then_some(row))
            .collect();
        let active = coefficients
            .take_rows(active_rows.clone(), None)
            .map_err(error)?;
        let scales = mu_squared.take_rows(active_rows, None).map_err(error)?;
        let mut parts = Vec::with_capacity(self.diagrams.len());
        if active.rows() > 0 {
            for (diagram, (offset, count, plan)) in self.diagrams.iter_mut().enumerate() {
                let base = *offset;
                let shifts = active
                    .take_columns(
                        (0..*count)
                            .flat_map(|p| (0..4).map(move |mu| base + 1 + 5 * p + mu))
                            .collect(),
                    )
                    .map_err(error)?;
                let masses = active
                    .take_columns((0..*count).map(|p| *offset + 5 + 5 * p).collect())
                    .map_err(error)?;
                let parameters = active.take_columns(vec![*offset]).map_err(error)?;
                let result = plan
                    .evaluate_batch(&shifts, &masses, &scales, &parameters, None)
                    .map_err(error)?;
                if result.statuses().len() != active.rows()
                    || result
                        .statuses()
                        .iter()
                        .zip(active.ids())
                        .any(|((id, _), expected)| id != expected)
                {
                    return Err(error("reducer returned inconsistent lane identities"));
                }
                for (id, status) in result.statuses() {
                    if status != "success" {
                        failures
                            .entry(*id)
                            .or_insert_with(|| format!("diagram {diagram}: {status}"));
                    }
                }
                let values = result.successful_values();
                active.compatible(&values).map_err(error)?;
                let expected: Vec<_> = result
                    .statuses()
                    .iter()
                    .filter_map(|(id, status)| (status == "success").then_some(*id))
                    .collect();
                if values.columns() != 3 || values.ids() != expected {
                    return Err(error("reducer returned inconsistent successful values"));
                }
                for id in values.nonfinite_rows() {
                    failures.entry(id).or_insert_with(|| {
                        format!("diagram {diagram}: nonfinite Laurent coefficient")
                    });
                }
                parts.push(values);
            }
        }
        let successful: Vec<_> = momenta
            .ids()
            .iter()
            .copied()
            .filter(|id| !failures.contains_key(id))
            .collect();
        let statuses = momenta
            .ids()
            .iter()
            .map(|id| {
                (
                    *id,
                    failures
                        .get(id)
                        .cloned()
                        .unwrap_or_else(|| "success".into()),
                )
            })
            .collect();
        if successful.is_empty() {
            return empty_result(momenta, statuses);
        }
        let parts = parts
            .iter()
            .map(|part| {
                let indices: BTreeMap<_, _> = part
                    .ids()
                    .iter()
                    .enumerate()
                    .map(|(row, id)| (*id, row))
                    .collect();
                let rows = successful
                    .iter()
                    .map(|id| {
                        indices
                            .get(id)
                            .copied()
                            .ok_or_else(|| error("successful reduction lane has no value"))
                    })
                    .collect::<RusticolResult<Vec<_>>>()?;
                part.take_rows(rows, None).map_err(error)
            })
            .collect::<RusticolResult<Vec<_>>>()?;
        macro_rules! sum {
            ($variant:ident) => {{
                let values = parts
                    .iter()
                    .map(|part| match part.data() {
                        Data::$variant(values) => Ok(values.as_slice()),
                        _ => Err(error("diagram arithmetic differs")),
                    })
                    .collect::<RusticolResult<Vec<_>>>()?;
                coherent_sum(&values, successful, momenta.precision_bits())?
            }};
        }
        let values = match momenta.data() {
            Data::Double(_) => sum!(Double),
            Data::DoubleDouble(_) => sum!(DoubleDouble),
            Data::Arbitrary(_) => sum!(Arbitrary),
        };
        let invalid: BTreeSet<_> = values.nonfinite_rows().into_iter().collect();
        if invalid.is_empty() {
            return Ok(BareScalarLoopBatch { statuses, values });
        }
        let statuses = statuses
            .into_iter()
            .map(|(id, status)| {
                (
                    id,
                    if invalid.contains(&id) {
                        "nonfinite coherent Laurent sum".into()
                    } else {
                        status
                    },
                )
            })
            .collect();
        let rows = values
            .ids()
            .iter()
            .enumerate()
            .filter_map(|(row, id)| (!invalid.contains(id)).then_some(row))
            .collect();
        Ok(BareScalarLoopBatch {
            statuses,
            values: values.take_rows(rows, None).map_err(error)?,
        })
    }
}
