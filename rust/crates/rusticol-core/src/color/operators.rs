// SPDX-License-Identifier: 0BSD

//! Exact operator actions on color tensors, before any bra/ket contraction.
//!
//! Physical all-outgoing charges use `tr(t^a t^b)=delta^{ab}/2`, as in the
//! existing ordered-emission API. A dipole `P_ij=T_i.T_j` emits two adjoint
//! indices on its ket and contracts those indices with the existing network
//! reducer. This is an operator action, not a Gram entry or an inverse-Gram
//! reconstruction. Products retain their order even when dipoles share legs.

use super::*;
use network::{ColorProduct, ColorString, reduce_network};

/// A physical charge pair acting on a fixed typed external color space.
///
/// Both labels must be colored legs. Equal labels are allowed and implement
/// the quadratic Casimir through the same exact algebra. Fundamental,
/// antifundamental and adjoint representations are supported at symbolic Nc;
/// other representations require an extension of the common emission/reducer
/// interfaces. Singlet insertions are rejected rather than treated as a
/// missing or silently zero color correlation.
/// Input representations must already be all-outgoing: callers can use
/// [`ColorLeg::all_outgoing`]. No additional incoming-leg sign is applied.
#[derive(Clone, Debug)]
pub struct ColorDipole {
    legs: Vec<ColorLeg>,
    pair: [i64; 2],
    emitted: [i64; 2],
    connection: ColorConnection,
}

impl ColorDipole {
    pub fn new(legs: Vec<ColorLeg>, left: i64, right: i64) -> RusticolResult<Self> {
        let legs = canonical_legs(legs)?;
        for label in [left, right] {
            if !legs
                .iter()
                .any(|leg| leg.label == label && leg.representation != ColorRepresentation::Singlet)
            {
                return Err(invalid(
                    "dipole insertions must act on original colored legs",
                ));
            }
        }
        let emitted = fresh_labels(&legs)?;
        // On a ket the rightmost charge acts first. Different original legs
        // commute, and equal labels give sum_a T_i^a T_i^a after closure.
        let connection = ColorConnection::new(
            legs.clone(),
            vec![
                ColorEmission::EmitGluon {
                    emitter: right,
                    emitted: emitted[0],
                },
                ColorEmission::EmitGluon {
                    emitter: left,
                    emitted: emitted[1],
                },
            ],
        )?;
        Ok(Self {
            legs,
            pair: [left, right],
            emitted,
            connection,
        })
    }

    pub fn legs(&self) -> &[ColorLeg] {
        &self.legs
    }

    pub fn pair(&self) -> [i64; 2] {
        self.pair
    }

    /// Apply `T_left.T_right`, retaining exact complex coefficients, Laurent
    /// powers and inverse-sqrt(2) normalization. The reducer may transfer even
    /// powers of sqrt(2) into the rational coefficients; no approximation or
    /// color averaging is performed.
    pub fn apply_connected(
        &self,
        input: &ConnectedColorTensor,
    ) -> RusticolResult<ConnectedColorTensor> {
        let emitted = self.connection.apply_connected(input)?;
        let rename = |label: i64| {
            if self.emitted.contains(&label) {
                ActionIndex::Contracted
            } else {
                ActionIndex::External(label)
            }
        };
        let network: Vec<_> = emitted
            .terms()
            .iter()
            .map(|term| ColorProduct {
                coefficient: term.coefficient.clone(),
                // This is the inverse of network::decode: network matrices
                // run upper-row(antiquark) to lower-column(quark), whereas
                // literal strings run quark to antiquark. Trace orientation
                // is reversed as well, not reflected after reduction.
                strings: term
                    .tensor
                    .open_strings()
                    .iter()
                    .map(|string| ColorString {
                        row: rename(string.antifundamental),
                        word: string.adjoints.iter().rev().copied().map(rename).collect(),
                        col: rename(string.fundamental),
                    })
                    .collect(),
                traces: term
                    .tensor
                    .traces()
                    .iter()
                    .map(|trace| trace.iter().rev().copied().map(rename).collect())
                    .collect(),
                nc_power: term.nc_power,
                root2_power: i64::from(emitted.normalization_power()),
            })
            .collect();
        let external = self
            .legs
            .iter()
            .map(|leg| (ActionIndex::External(leg.label), leg.label))
            .collect();
        let result = reduce_network(&network, self.legs.clone(), &external)?;
        if result.terms().is_empty() {
            // A zero network has no term from which the reducer can infer
            // normalization parity. Keep the input parity so an odd-normalized
            // exact zero remains contractible with the same original space.
            ConnectedColorTensor::new(self.legs.clone(), vec![], input.normalization_power() % 2)
        } else {
            Ok(result)
        }
    }

    /// Directed Laurent matrix element `<bra|T_left.T_right|ket>`. As in
    /// [`ConnectedColorTensor::overlap_nc_terms`], an odd combined bra/ket
    /// inverse-sqrt(2) power is outside the rational coefficient domain.
    pub fn matrix_element_nc_terms(
        &self,
        bra: &ConnectedColorTensor,
        ket: &ConnectedColorTensor,
    ) -> RusticolResult<ColorNcTerms> {
        bra.overlap_nc_terms(&self.apply_connected(ket)?)
    }
}

/// Ordered product of physical dipoles in mathematical left-to-right order.
///
/// For `[P_ij, P_jk]`, application computes `P_ij(P_jk ket)`. Shared legs are
/// never sorted, commuted or replaced by products of scalar correlations.
/// The empty product is the identity on the declared typed color space.
#[derive(Clone, Debug)]
pub struct ColorDipoleProduct {
    legs: Vec<ColorLeg>,
    factors: Vec<ColorDipole>,
}

impl ColorDipoleProduct {
    pub fn new(legs: Vec<ColorLeg>, pairs: Vec<[i64; 2]>) -> RusticolResult<Self> {
        let legs = canonical_legs(legs)?;
        let factors = pairs
            .into_iter()
            .map(|[left, right]| ColorDipole::new(legs.clone(), left, right))
            .collect::<RusticolResult<_>>()?;
        Ok(Self { legs, factors })
    }

    pub fn legs(&self) -> &[ColorLeg] {
        &self.legs
    }

    pub fn factors(&self) -> &[ColorDipole] {
        &self.factors
    }

    pub fn apply_connected(
        &self,
        input: &ConnectedColorTensor,
    ) -> RusticolResult<ConnectedColorTensor> {
        if input.legs() != self.legs {
            return Err(invalid(
                "dipole product input must have identical typed color legs",
            ));
        }
        let mut result = input.clone();
        for factor in self.factors.iter().rev() {
            result = factor.apply_connected(&result)?;
        }
        Ok(result)
    }

    /// Directed Laurent matrix element with no real projection, averaging or
    /// implicit reversal of the requested product. An odd combined bra/ket
    /// inverse-sqrt(2) power is rejected by the common overlap contract.
    pub fn matrix_element_nc_terms(
        &self,
        bra: &ConnectedColorTensor,
        ket: &ConnectedColorTensor,
    ) -> RusticolResult<ColorNcTerms> {
        bra.overlap_nc_terms(&self.apply_connected(ket)?)
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd)]
enum ActionIndex {
    External(i64),
    Contracted,
}

fn fresh_labels(legs: &[ColorLeg]) -> RusticolResult<[i64; 2]> {
    let used: BTreeSet<_> = legs.iter().map(|leg| leg.label).collect();
    let mut next = i64::MIN;
    let mut labels = [0; 2];
    for label in &mut labels {
        while used.contains(&next) {
            next = next
                .checked_add(1)
                .ok_or_else(|| invalid("no fresh adjoint color label"))?;
        }
        *label = next;
        next = next
            .checked_add(1)
            .ok_or_else(|| invalid("no fresh adjoint color label"))?;
    }
    Ok(labels)
}

#[cfg(test)]
mod tests;
