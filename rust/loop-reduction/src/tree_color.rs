// SPDX-License-Identifier: 0BSD

//! Exact color sectors of a checked coherent amplitude, before its square.
//! Idenso owns collection and the spin interfaces; Rusticol owns color algebra.

use std::collections::{BTreeMap, BTreeSet};

use idenso::{
    representations::{ColorAdjoint, ColorFundamental, ColorSextet},
    tensor::SymbolicTensor,
};
use rusticol_core::{
    RusticolError, RusticolResult,
    color::{
        ColorLeg, ColorRepresentation, ConnectedColorTensor,
        network::{reduce_network, spenso_color_network},
    },
};
use spenso::{
    shadowing::TensorCollectFilter,
    structure::{
        dimension::Dimension,
        partial::{PartialIndex, PartialStructure, PartialStructureExt},
        representation::{LibraryRep, RepName},
        slot::{IsAbstractSlot, ParseableAind},
    },
};
use symbolica::atom::{Atom, AtomCore, AtomView};

fn error(message: impl std::fmt::Display) -> RusticolError {
    RusticolError::invalid_argument(format!("native tree color separation: {message}"))
}

fn color_representations() -> [LibraryRep; 3] {
    [
        ColorFundamental {}.into(),
        ColorAdjoint {}.into(),
        // Select exotic color explicitly so the existing importer rejects it;
        // it must not escape as an apparently colorless spin coefficient.
        ColorSextet {}.into(),
    ]
}

pub(crate) fn index_label(index: Atom) -> String {
    match index.as_view() {
        AtomView::Var(variable) => variable.get_symbol().get_name().to_owned(),
        _ => index.to_canonical_string(),
    }
}

/// Factor an amplitude into exact color tensors and checked spin coefficients.
///
/// `external` uses the encoded slot labels consumed by `spenso_color_network`.
/// The caller supplies literal all-outgoing color representations: upper `cof`
/// slots are antifundamental endpoints and lower `dind(cof)` slots fundamental.
/// No color basis reduction, normalization division or spin sum is performed.
/// A redundant basis is retained, including full complex scalar coefficients.
/// Supported color syntax is exactly the existing SU(3) network importer's
/// domain; unsupported representations and nonlinear color functions fail there.
pub(crate) fn factor_tree_color(
    source: &SymbolicTensor<PartialStructure>,
    legs: &[ColorLeg],
    external: &BTreeMap<String, i64>,
) -> RusticolResult<Vec<(ConnectedColorTensor, SymbolicTensor<PartialStructure>)>> {
    let representations = color_representations();
    let slots = source.structure().logical_slots();
    let mut declared = BTreeSet::new();
    let mut mapped = BTreeSet::new();
    for slot in &slots {
        let representation = slot.rep().rep;
        if !representations.contains(&representation.base()) {
            continue;
        }
        let (literal, dimension) = if representation.base() == (ColorAdjoint {}).into() {
            (ColorRepresentation::Adjoint, 8)
        } else if representation.base() == (ColorFundamental {}).into() {
            (
                if representation.is_base() {
                    ColorRepresentation::Antifundamental
                } else {
                    ColorRepresentation::Fundamental
                },
                3,
            )
        } else {
            return Err(error("unsupported external color representation"));
        };
        if slot.rep().dim != Dimension::Concrete(dimension) {
            return Err(error(
                "external color ports require concrete SU(3) dimensions",
            ));
        }
        let PartialIndex::Explicit(index) = slot.aind else {
            return Err(error("external color ports require explicit slot labels"));
        };
        let key = index_label(index.to_atom());
        let label = *external
            .get(&key)
            .ok_or_else(|| error("external color slot has no physical leg mapping"))?;
        if !declared.insert(key)
            || !mapped.insert(ColorLeg {
                label,
                representation: literal,
            })
        {
            return Err(error(
                "external color slots must map to distinct physical legs",
            ));
        }
    }
    let colored: BTreeSet<_> = legs
        .iter()
        .copied()
        .filter(|leg| leg.representation != ColorRepresentation::Singlet)
        .collect();
    if declared.len() != external.len() || mapped != colored {
        return Err(error(
            "external color map differs from the declared amplitude ports",
        ));
    }
    let spin_structure = PartialStructure::from_logical_slots(
        slots
            .into_iter()
            .filter(|slot| !representations.contains(&slot.rep().rep.base())),
    );
    // An established exact zero retains its physical ports. No identity color
    // tensor exists for arbitrary colored ports, so publish the exact empty sum.
    if source.expression().is_zero() && !colored.is_empty() {
        let color = reduce_network::<String>(&[], legs.to_vec(), external)?;
        let spin =
            SymbolicTensor::from_declared_parts(Atom::Zero, spin_structure).map_err(error)?;
        return Ok(vec![(color, spin)]);
    }
    let filter = TensorCollectFilter::Reps(representations);
    source
        .coefficient_list(filter)
        .map_err(error)?
        .into_iter()
        .map(|(color, coefficient)| {
            let mut unresolved = false;
            coefficient.expression().visitor(&mut |value| {
                unresolved |= filter.matches(value);
                !unresolved
            });
            if unresolved {
                return Err(error(
                    "spin coefficient retains an unresolved color expression",
                ));
            }
            let spin = SymbolicTensor::from_declared_parts(
                coefficient.expression().clone(),
                spin_structure.clone(),
            )
            .map_err(error)?;
            let network = spenso_color_network(color.expression())?;
            let color = reduce_network(&network, legs.to_vec(), external)?;
            Ok((color, spin))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use idenso::color::CS;
    use spenso::structure::representation::Minkowski;
    use symbolica::{
        domains::{float::Complex, rational::Rational},
        symbol,
    };

    fn tensor(expression: &str) -> SymbolicTensor<PartialStructure> {
        let _ = CS.t;
        SymbolicTensor::infer(Atom::parse(expression, "spenso", Default::default()).unwrap())
            .unwrap()
    }

    fn generator_legs() -> (Vec<ColorLeg>, BTreeMap<String, i64>) {
        (
            vec![
                ColorLeg {
                    label: 1,
                    representation: ColorRepresentation::Fundamental,
                },
                ColorLeg {
                    label: 2,
                    representation: ColorRepresentation::Antifundamental,
                },
                ColorLeg {
                    label: 3,
                    representation: ColorRepresentation::Adjoint,
                },
            ],
            BTreeMap::from([("e::j".into(), 1), ("e::i".into(), 2), ("e::a".into(), 3)]),
        )
    }

    #[test]
    fn color_separation_preserves_factored_spin_coefficients_and_generator_normalization() {
        let color = tensor("t(coad(8,e::a),cof(3,e::i),dind(cof(3,e::j)))");
        let vector = Atom::var(spenso::vector_symbol!("native_tree_color_test::spin"));
        let spin = SymbolicTensor::infer(
            Minkowski {}
                .new_rep(4)
                .vector(vector.as_view(), [Atom::num(17)]),
        )
        .unwrap();
        let x = Atom::var(symbol!("native_tree_color_test::x"));
        let y = Atom::var(symbol!("native_tree_color_test::y"));
        let weight = (Atom::one() + Atom::i()) * (&x + &y).pow(8);
        let source = color
            .multiply(&spin)
            .unwrap()
            .multiply(&SymbolicTensor::infer(weight.clone()).unwrap())
            .unwrap();
        let (legs, external) = generator_legs();
        let rows = factor_tree_color(&source, &legs, &external).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].0.normalization_power(), 1);
        assert_eq!(
            rows[0].0.overlap(&rows[0].0).unwrap(),
            Complex::new(Rational::from(4), Rational::from(0))
        );
        assert_eq!(rows[0].1.expression(), &(&weight * spin.expression()));
        assert_eq!(
            rows[0].1.structure().logical_slots(),
            spin.structure().logical_slots()
        );
    }

    #[test]
    fn coherent_color_sum_keeps_the_interference_basis_and_exact_weights() {
        let direct = tensor("g(cof(3,e::i),dind(cof(3,e::j)))*g(cof(3,e::k),dind(cof(3,e::l)))");
        let exchanged = tensor("g(cof(3,e::i),dind(cof(3,e::l)))*g(cof(3,e::k),dind(cof(3,e::j)))");
        let x = Atom::var(symbol!("native_tree_color_test::sum_x"));
        let y = Atom::var(symbol!("native_tree_color_test::sum_y"));
        let first = (Atom::one() + Atom::i()) * (&x + &y).pow(8);
        let second = (Atom::num(2) - Atom::i()) * (&x - &y).pow(7);
        let source =
            SymbolicTensor::infer(&first * direct.expression() + &second * exchanged.expression())
                .unwrap();
        let legs = [
            (1, ColorRepresentation::Fundamental),
            (2, ColorRepresentation::Antifundamental),
            (3, ColorRepresentation::Fundamental),
            (4, ColorRepresentation::Antifundamental),
        ]
        .map(|(label, representation)| ColorLeg {
            label,
            representation,
        });
        let external = BTreeMap::from([
            ("e::j".into(), 1),
            ("e::i".into(), 2),
            ("e::l".into(), 3),
            ("e::k".into(), 4),
        ]);
        let rows = factor_tree_color(&source, &legs, &external).unwrap();
        assert_eq!(rows.len(), 2);
        assert!(rows.iter().any(|(_, spin)| spin.expression() == &first));
        assert!(rows.iter().any(|(_, spin)| spin.expression() == &second));
        for (color, _) in &rows {
            assert_eq!(
                color.overlap(color).unwrap(),
                Complex::new(Rational::from(9), Rational::from(0))
            );
        }
        assert_eq!(
            rows[0].0.overlap(&rows[1].0).unwrap(),
            Complex::new(Rational::from(3), Rational::from(0))
        );
    }

    #[test]
    fn colorless_and_exact_zero_amplitudes_retain_their_coefficients_and_ports() {
        let source = tensor("(native_tree_color_test::x+1)^9");
        let rows = factor_tree_color(&source, &[], &BTreeMap::new()).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].1, source);
        assert_eq!(
            rows[0].0.overlap(&rows[0].0).unwrap(),
            Complex::new(Rational::from(1), Rational::from(0))
        );

        let original = tensor("t(coad(8,e::a),cof(3,e::i),dind(cof(3,e::j)))");
        let zero = original.with_checked_expression(Atom::Zero).unwrap();
        let (legs, external) = generator_legs();
        let rows = factor_tree_color(&zero, &legs, &external).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].0.legs(), legs);
        assert!(rows[0].0.terms().is_empty());
        assert!(rows[0].1.expression().is_zero());
        assert!(factor_tree_color(&zero, &legs, &BTreeMap::new()).is_err());

        let other_dimension = tensor("t(coad(9,e::a),cof(3,e::i),dind(cof(3,e::j)))")
            .with_checked_expression(Atom::Zero)
            .unwrap();
        assert!(factor_tree_color(&other_dimension, &legs, &external).is_err());
    }

    #[test]
    fn nonlinear_closed_color_and_incorrect_external_maps_fail() {
        let source = tensor(
            "(1+t(coad(8,e::a),cof(3,e::i),dind(cof(3,e::j)))*t(coad(8,e::a),cof(3,e::j),dind(cof(3,e::i))))^(-1)",
        );
        assert!(factor_tree_color(&source, &[], &BTreeMap::new()).is_err());

        let closed = tensor(
            "t(coad(8,e::a),cof(3,e::i),dind(cof(3,e::j)))*t(coad(8,e::a),cof(3,e::j),dind(cof(3,e::i)))",
        );
        let hidden = SymbolicTensor::infer(symbolica::function!(
            spenso::network::tags::SPENSO_TAG.pure_scalar,
            closed.expression()
        ))
        .unwrap();
        assert!(factor_tree_color(&hidden, &[], &BTreeMap::new()).is_err());

        let source = tensor("t(coad(8,e::a),cof(3,e::i),dind(cof(3,e::j)))");
        let (mut legs, external) = generator_legs();
        legs[0].representation = ColorRepresentation::Antifundamental;
        assert!(factor_tree_color(&source, &legs, &external).is_err());
    }
}
