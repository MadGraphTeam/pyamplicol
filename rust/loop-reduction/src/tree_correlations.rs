// SPDX-License-Identifier: 0BSD

//! Exact color insertions on the retained coherent tree basis.
//!
//! Matrices are directed overlaps of complete operator-transformed tensors,
//! never products of Gram matrices. Numerical amplitudes use the prepared
//! model's SU(3), `TR=1/2` domain; formal Nc matrices are diagnostic algebra.
//! Results include no initial averages, flux or final-state symmetry factors.
//! This module supplies color bilinears, not an open-index spin tensor API.

use std::sync::Arc;

use rusticol_core::{RusticolError, RusticolResult, color::ColorNcTerms};

use crate::{runtime::Arithmetic, tree_preparation::TreeProgram};

mod matrices;
mod runtime;
#[cfg(test)]
mod tests;

pub use runtime::TreeColorEvaluator;

/// All labels refer to original, typed all-outgoing color legs in the tree.
/// Crossing is already encoded by the prepared tree; no extra sign is added.
#[derive(Clone, Debug, PartialEq, Eq)]
#[non_exhaustive]
pub enum TreeColorInsertion {
    Identity,
    /// `T_left.T_right`; coincident labels give the quadratic Casimir.
    Pair {
        left: i64,
        right: i64,
    },
    /// Mathematical left-to-right order, applied rightmost first on the ket.
    /// Empty products are rejected; request `Identity` explicitly instead.
    OrderedProduct(Vec<[i64; 2]>),
    /// `AB+BA`, with no factor one half and no repeated-factor deduplication.
    Anticommutator {
        first: [i64; 2],
        second: [i64; 2],
    },
    /// `f_abc T_first^a T_second^b T_third^c` for three distinct colored legs.
    /// The exact action is `i[P_first,second,P_second,third]`, without an
    /// additional factor of i in the definition of the returned operator.
    StructureConstantTripole {
        first: i64,
        second: i64,
        third: i64,
    },
}

/// Immutable basis identity, exact insertion matrices and bilinear programs.
/// Owning the tree prevents coefficients from an unrelated equal-size basis
/// from being used accidentally. Request order and multiplicity are retained.
pub struct TreeColorProgram {
    tree: Arc<TreeProgram>,
    requests: Vec<TreeColorInsertion>,
    matrices: Vec<Vec<Vec<ColorNcTerms>>>,
    self_state: Vec<u8>,
    directed_state: Vec<u8>,
}

impl TreeColorProgram {
    pub fn prepare(
        tree: Arc<TreeProgram>,
        requests: Vec<TreeColorInsertion>,
    ) -> RusticolResult<Self> {
        let matrices = matrices::prepare_matrices(tree.color_tensors(), &requests)?;
        let numerical = matrices
            .iter()
            .map(|matrix| matrices::at_nc3(matrix))
            .collect::<RusticolResult<Vec<_>>>()?;
        let (self_state, directed_state) = runtime::compile_states(&numerical)?;
        Ok(Self {
            tree,
            requests,
            matrices,
            self_state,
            directed_state,
        })
    }

    pub fn tree(&self) -> &TreeProgram {
        &self.tree
    }
    pub fn requests(&self) -> &[TreeColorInsertion] {
        &self.requests
    }
    pub fn basis_len(&self) -> usize {
        self.tree.color_tensors().len()
    }

    /// Directed `<C_b|O|C_c>` entries as exact rational complex Laurent terms.
    /// Formal Nc dependence does not extend the numerical model beyond SU(3).
    pub fn matrix_nc_terms(&self, request: usize) -> RusticolResult<&[Vec<ColorNcTerms>]> {
        self.matrices
            .get(request)
            .map(Vec::as_slice)
            .ok_or_else(|| {
                RusticolError::invalid_argument(
                    "native tree color matrix request index is out of range",
                )
            })
    }

    /// Rebuild numerical coefficients from exact instructions at the requested
    /// working bits. `Arbitrary,113` is the multiprecision 113-bit tier;
    /// `DoubleDouble,106` remains the distinct compatibility carrier.
    pub fn evaluator_with_precision_bits(
        &self,
        arithmetic: Arithmetic,
        bits: u32,
    ) -> RusticolResult<TreeColorEvaluator> {
        TreeColorEvaluator::new(self, arithmetic, bits)
    }
}
