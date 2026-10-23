// SPDX-License-Identifier: 0BSD

//! Exact daughter-charge insertions through an all-outgoing gluon splitting.

use super::*;

/// Raw daughter-spectator insertions, including the splitting norm `T_R=1/2`.
///
/// Each entry is `<S bra | T_daughter . T_spectator | S ket>`, with
/// `S_ij,B=t^B_ij`. The entries retain directed complex phases and all input
/// normalizations. Dividing either entry by `T_R` multiplies it by two.
#[derive(Clone, Debug, PartialEq)]
pub struct SplitDaughterColorTerms {
    pub quark: ColorNcTerms,
    pub antiquark: ColorNcTerms,
}

impl SplitDaughterColorTerms {
    /// `<bra | D_parent . T_spectator | ket>`, where
    /// `(D^c)_AB=d^{AcB}` has no factor of `i`.
    ///
    /// The splitting identities are `S† T_q^c S / T_R=(T_adj^c+D^c)/2`
    /// and `S† T_qbar^c S / T_R=(T_adj^c-D^c)/2`. Consequently this is
    /// exactly `2*(quark-antiquark)`, with no additional `T_R` factor.
    pub fn symmetric_adjoint_nc_terms(&self) -> ColorNcTerms {
        let mut terms = ColorNcTerms::new();
        for (source, factor) in [(&self.quark, 2), (&self.antiquark, -2)] {
            for (&power, coefficient) in source {
                add_coefficient(
                    &mut terms,
                    power,
                    scale(coefficient, &Rational::from(factor)),
                );
            }
        }
        terms.retain(|_, coefficient| !is_zero(coefficient));
        terms
    }
}

/// A typed symmetric-adjoint pair obtained from exact splitting connections.
///
/// The parent is adjoint; the spectator is a distinct colored external leg.
/// Daughter and emitted-adjoint labels must be distinct and fresh relative to
/// every input leg. All legs and charges use the all-outgoing convention.
/// This object supplies only color matrix elements: mixed spin densities and
/// their kinematic splitting kernels remain the caller's responsibility.
#[derive(Clone, Debug)]
pub struct GluonSplittingColorPair {
    quark: ColorConnection,
    antiquark: ColorConnection,
    spectator: ColorConnection,
}

impl GluonSplittingColorPair {
    pub fn new(
        initial_legs: Vec<ColorLeg>,
        parent: i64,
        spectator: i64,
        quark: i64,
        antiquark: i64,
        emitted: i64,
    ) -> RusticolResult<Self> {
        if parent == spectator {
            return Err(invalid("splitting parent and spectator must be distinct"));
        }
        if !initial_legs
            .iter()
            .any(|leg| leg.label == spectator && leg.representation != ColorRepresentation::Singlet)
        {
            return Err(invalid("splitting spectator must be an input colored leg"));
        }
        let connection = |emitter| {
            ColorConnection::new(
                initial_legs.clone(),
                vec![
                    ColorEmission::SplitGluon {
                        parent,
                        quark,
                        antiquark,
                    },
                    ColorEmission::EmitGluon { emitter, emitted },
                ],
            )
        };
        Ok(Self {
            quark: connection(quark)?,
            antiquark: connection(antiquark)?,
            spectator: connection(spectator)?,
        })
    }

    /// Raw overlaps before division by `T_R`, for arbitrary complex input
    /// tensors with matching typed legs. An odd combined inverse-sqrt(2)
    /// input normalization cannot be represented by rational Laurent terms and
    /// is rejected by the common overlap implementation.
    pub fn raw_daughter_nc_terms(
        &self,
        bra: &ConnectedColorTensor,
        ket: &ConnectedColorTensor,
    ) -> RusticolResult<SplitDaughterColorTerms> {
        let spectator = self.spectator.apply_connected(ket)?;
        Ok(SplitDaughterColorTerms {
            quark: self
                .quark
                .apply_connected(bra)?
                .overlap_nc_terms(&spectator)?,
            antiquark: self
                .antiquark
                .apply_connected(bra)?
                .overlap_nc_terms(&spectator)?,
        })
    }

    /// Full complex Laurent matrix element of `D_parent . T_spectator`.
    /// No color averaging, real projection, or extra `T_R` factor is applied.
    pub fn symmetric_adjoint_nc_terms(
        &self,
        bra: &ConnectedColorTensor,
        ket: &ConnectedColorTensor,
    ) -> RusticolResult<ColorNcTerms> {
        Ok(self
            .raw_daughter_nc_terms(bra, ket)?
            .symmetric_adjoint_nc_terms())
    }
}
