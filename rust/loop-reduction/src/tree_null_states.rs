// SPDX-License-Identifier: 0BSD

//! Program-bound constructive massless external states.
//!
//! Admission uses the exact external masses retained by native preparation.
//! The immutable FeynKit owners supply both coefficient momenta and external
//! wavefunctions. This association does not certify event conservation, source
//! precision, gauge completeness or numerical accuracy. Rebuild owners from the
//! original spatial sources when changing working precision.

use std::{any::TypeId, collections::BTreeSet, sync::Arc};

use feynkit_generator::Process;
use feynkit_graph::ExternalState;
use feynkit_kinematics::{FutureNullMomentum, Helicity, KinematicScalar, WavefunctionKind};
use feynkit_model::{Model, ParticleId};
use rusticol_core::{RusticolError, RusticolResult};
use symbolica::{
    atom::AtomCore,
    domains::float::{DoubleFloat, Float},
};

use crate::{
    Complex,
    runtime::{
        Arithmetic, Batch, BatchCarrier, shape, validate_working_precision, wavefunction_error,
    },
    tree_preparation::TreeProgram,
    tree_runtime::{ExternalTreeState, TreeEvaluator, TreeStateSource},
};

#[cfg(test)]
mod tests;

fn error(message: impl std::fmt::Display) -> RusticolError {
    RusticolError::invalid_argument(format!("future-null tree states: {message}"))
}

fn carrier_arithmetic<T: BatchCarrier>() -> RusticolResult<Arithmetic> {
    let actual = TypeId::of::<T>();
    if actual == TypeId::of::<f64>() {
        Ok(Arithmetic::Double)
    } else if actual == TypeId::of::<DoubleFloat>() {
        Ok(Arithmetic::DoubleDouble)
    } else if actual == TypeId::of::<Float>() {
        Ok(Arithmetic::Arbitrary)
    } else {
        Err(RusticolError::unsupported_precision(
            "future-null tree states require a native f64, DoubleFloat or Float batch carrier",
        ))
    }
}

/// The complete labelled external domain of one immutable prepared program.
///
/// Every external mass must specialize identically to exact zero, including
/// scalar spectators. Runtime-dependent or unresolved masses are rejected even
/// when a numerical default is zero. Internal supported masses are unrestricted.
/// Massive external particles require a future mixed-leg owner; the existing
/// raw tree evaluator remains available for its declared domain.
#[derive(Clone)]
pub struct FutureNullTreeDomain {
    program: Arc<TreeProgram>,
}

impl FutureNullTreeDomain {
    pub(crate) fn new(program: Arc<TreeProgram>) -> RusticolResult<Self> {
        let legs = &program.external_domain.legs;
        if legs.len() != program.momentum_legs().len()
            || legs
                .iter()
                .zip(program.momentum_legs())
                .any(|(leg, label)| leg.label != *label)
            || legs
                .iter()
                .map(|leg| leg.label)
                .collect::<BTreeSet<_>>()
                .len()
                != legs.len()
        {
            return Err(error(
                "prepared external occurrence inventory is inconsistent",
            ));
        }
        for leg in legs {
            if !leg.resolved_mass.is_zero() {
                return Err(RusticolError::unsupported_runtime_capability(
                    "native-tree-future-null",
                    format!(
                        "external occurrence {} has nonzero or unresolved specialized mass {}; all external masses must be identically zero",
                        leg.label, leg.resolved_mass
                    ),
                ));
            }
        }
        Ok(Self { program })
    }

    /// Native external labels in coefficient-column order, including scalars.
    pub fn momentum_legs(&self) -> &[usize] {
        self.program.momentum_legs()
    }

    /// Prepared model namespace for the retained native particle identities.
    pub fn model(&self) -> &Model {
        &self.program.external_domain.model
    }

    /// Original process supplied to this program's native preparation.
    pub fn process(&self) -> &Process {
        &self.program.external_domain.process
    }

    /// Immutable native occurrence, particle and physical crossing role.
    pub fn external_legs(&self) -> impl Iterator<Item = (usize, ParticleId, ExternalState)> + '_ {
        self.program
            .external_domain
            .legs
            .iter()
            .map(|leg| (leg.label, leg.particle, leg.direction))
    }

    /// Bind complete rows of constructive owners to this particular program.
    ///
    /// Every row supplies each external label exactly once, in any order. Row
    /// identities must be unique. The canonical momentum batch is derived from
    /// these same consumed owners, never from an independently supplied vector.
    /// Working bits are attempt metadata; tracked Float precision may be lower
    /// after arithmetic and is neither padded nor treated as an accuracy proof.
    pub fn bind<T: BatchCarrier + KinematicScalar>(
        &self,
        row_ids: Vec<u64>,
        keyed_legs: Vec<Vec<(usize, FutureNullMomentum<T>)>>,
        working_bits: u32,
    ) -> RusticolResult<FutureNullTreeBatch<T>> {
        validate_working_precision(carrier_arithmetic::<T>()?, working_bits)
            .map_err(RusticolError::from)?;
        if row_ids.len() != keyed_legs.len() {
            return Err(error("row identities and external-state rows differ"));
        }
        if row_ids.iter().copied().collect::<BTreeSet<_>>().len() != row_ids.len() {
            return Err(error("row identities must be unique"));
        }
        let labels = self.momentum_legs();
        let expected = labels.iter().copied().collect::<BTreeSet<_>>();
        let columns = labels
            .len()
            .checked_mul(4)
            .ok_or_else(|| error("momentum column dimensions overflow"))?;
        let size = shape(row_ids.len(), columns).map_err(RusticolError::from)?;
        // Validate every complete label inventory before canonicalizing any row.
        for (row, entries) in keyed_legs.iter().enumerate() {
            let actual = entries
                .iter()
                .map(|(label, _)| *label)
                .collect::<BTreeSet<_>>();
            if entries.len() != labels.len() || actual != expected {
                return Err(error(format!(
                    "lane {} (row {row}) requires a complete bijection of prepared external labels",
                    row_ids[row]
                )));
            }
        }
        let mut values = Vec::new();
        values
            .try_reserve_exact(size)
            .map_err(|e| error(format!("momentum allocation failed: {e}")))?;
        let mut legs = Vec::new();
        legs.try_reserve_exact(row_ids.len())
            .map_err(|e| error(format!("external-state row allocation failed: {e}")))?;
        for entries in keyed_legs {
            let mut keyed = entries
                .into_iter()
                .collect::<std::collections::BTreeMap<_, _>>();
            let mut row = Vec::new();
            row.try_reserve_exact(labels.len())
                .map_err(|e| error(format!("external-state leg allocation failed: {e}")))?;
            for label in labels {
                let owner = keyed
                    .remove(label)
                    .expect("complete label bijection was checked");
                values.extend(
                    owner
                        .as_momentum()
                        .into_iter()
                        .map(|value| Complex::new(value.clone(), value.zero())),
                );
                row.push(owner);
            }
            legs.push(row);
        }
        let momenta =
            Batch::typed(values, row_ids, columns, working_bits).map_err(RusticolError::from)?;
        Ok(FutureNullTreeBatch {
            program: Arc::clone(&self.program),
            legs,
            momenta,
        })
    }

    /// Reuse the prepared coefficient and norm instructions at any supported
    /// working precision. No state-specific source compilation is performed.
    pub fn evaluator_with_precision_bits(
        &self,
        arithmetic: Arithmetic,
        bits: u32,
    ) -> RusticolResult<FutureNullTreeEvaluator> {
        Ok(FutureNullTreeEvaluator {
            inner: self
                .program
                .evaluator_with_precision_bits(arithmetic, bits)?,
            program: Arc::clone(&self.program),
        })
    }
}

/// Immutable rows whose owners and coefficient momenta share one program.
///
/// Shared views cannot replace components or retain this association after a
/// scalar conversion. Cloning the raw [`Batch`] returned by [`Self::momenta`]
/// does not create another program-bound source.
///
/// ```compile_fail
/// use rusticol_loop_reduction::tree_null_states::FutureNullTreeBatch;
/// fn change(batch: &mut FutureNullTreeBatch<f64>) {
///     batch.leg(0, 1).unwrap().as_momentum().temporal.value = 7.0;
/// }
/// ```
pub struct FutureNullTreeBatch<T: BatchCarrier + KinematicScalar> {
    program: Arc<TreeProgram>,
    legs: Vec<Vec<FutureNullMomentum<T>>>,
    momenta: Batch,
}

impl<T: BatchCarrier + KinematicScalar> FutureNullTreeBatch<T> {
    pub fn momenta(&self) -> &Batch {
        &self.momenta
    }

    /// Shared owner for a row index and native external occurrence label.
    pub fn leg(&self, row: usize, label: usize) -> Option<&FutureNullMomentum<T>> {
        let column = self
            .program
            .momentum_legs()
            .iter()
            .position(|value| *value == label)?;
        self.legs.get(row)?.get(column)
    }

    /// Identity is deliberately stronger than equal process/shape metadata.
    /// Independent preparations cannot exchange admitted sources, including
    /// empty batches. Domain clones from the same program are interchangeable.
    pub(crate) fn validate_program(&self, program: &Arc<TreeProgram>) -> RusticolResult<()> {
        if !Arc::ptr_eq(&self.program, program) {
            return Err(error(
                "source belongs to a different prepared program instance",
            ));
        }
        Ok(())
    }
}

impl<T: BatchCarrier + KinematicScalar> TreeStateSource for FutureNullTreeBatch<T> {
    fn momenta(&self) -> &Batch {
        &self.momenta
    }

    fn components(&self, state: &ExternalTreeState, helicity: i32) -> RusticolResult<Batch> {
        // Match all four columns and the immutable prepared role/domain. A raw
        // evaluator may use noncanonical tuples; its first column is no proof
        // that the remaining columns describe the same physical occurrence.
        let (position, leg, prepared) = self
            .program
            .external_domain
            .legs
            .iter()
            .enumerate()
            .filter_map(|(position, leg)| {
                let prepared = self.program.external_states().get(leg.state_index?)?;
                Some((position, leg, prepared))
            })
            .find(|(position, _, prepared)| {
                let columns = std::array::from_fn(|component| position * 4 + component);
                state.momentum_columns == columns
                    && prepared.momentum_columns == columns
                    && state.kind == prepared.kind
                    && state.helicities == prepared.helicities
            })
            .ok_or_else(|| {
                error("external-state tuple or role differs from its prepared occurrence")
            })?;
        if !prepared.helicities.contains(&helicity) {
            return Err(error(
                "helicity differs from the prepared external-state domain",
            ));
        }
        let kind = prepared.kind.parse::<WavefunctionKind>().map_err(error)?;
        let helicity = Helicity::try_from(i8::try_from(helicity).map_err(error)?).map_err(error)?;
        let columns = kind.component_count();
        let size = shape(self.momenta.rows(), columns).map_err(RusticolError::from)?;
        let mut values = Vec::new();
        values
            .try_reserve_exact(size)
            .map_err(|e| error(format!("external-component allocation failed: {e}")))?;
        for (row, owners) in self.legs.iter().enumerate() {
            let components = owners[position]
                .wavefunction(kind, helicity)
                .map_err(|failure| {
                    let failure = wavefunction_error(failure, self.momenta.precision_bits());
                    let message = format!(
                        "future-null external state lane {} (row {row}), occurrence {}: {failure}",
                        self.momenta.ids()[row],
                        leg.label
                    );
                    RusticolError::from(failure.context(message))
                })?;
            values.extend(components.into_components());
        }
        Batch::typed(
            values,
            self.momenta.ids().to_vec(),
            columns,
            self.momenta.precision_bits(),
        )
        .map_err(RusticolError::from)
    }
}

/// Prepared tree evaluator accepting only sources bound to its program.
/// Existing coefficient contraction and helicity-sum algorithms are reused.
pub struct FutureNullTreeEvaluator {
    program: Arc<TreeProgram>,
    inner: TreeEvaluator,
}

impl FutureNullTreeEvaluator {
    pub fn evaluate_coefficients<T: BatchCarrier + KinematicScalar>(
        &mut self,
        source: &FutureNullTreeBatch<T>,
        parameters: Option<&Batch>,
        helicities: &[i32],
    ) -> RusticolResult<Batch> {
        source.validate_program(&self.program)?;
        self.inner
            .evaluate_coefficients_from_source(source, parameters, helicities)
    }

    /// Return the unaveraged, unsymmetrized color norm summed over the prepared
    /// physical helicities. Result values retain the selected numerical carrier.
    pub fn evaluate_batch<T: BatchCarrier + KinematicScalar>(
        &mut self,
        source: &FutureNullTreeBatch<T>,
        parameters: Option<&Batch>,
    ) -> RusticolResult<Batch> {
        source.validate_program(&self.program)?;
        self.inner.evaluate_batch_from_source(source, parameters)
    }
}
