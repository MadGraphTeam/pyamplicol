// SPDX-License-Identifier: 0BSD

use super::*;
use ColorEmission::{EmitGluon, SplitGluon};
use ColorRepresentation::*;

fn coefficient(real: i64, imag: i64) -> ExactColorCoefficient {
    Complex::new(Rational::from(real), Rational::from(imag))
}
fn real(numerator: i64, denominator: i64) -> ExactColorCoefficient {
    Complex::new(Rational::from((numerator, denominator)), Rational::from(0))
}
fn leg(label: i64, representation: ColorRepresentation) -> ColorLeg {
    ColorLeg {
        label,
        representation,
    }
}
fn string(q: i64, word: &[i64], qbar: i64) -> OpenColorString {
    OpenColorString {
        fundamental: q,
        adjoints: word.to_vec(),
        antifundamental: qbar,
    }
}
fn qq() -> (Vec<ColorLeg>, ColorTensor) {
    (
        vec![leg(1, Fundamental), leg(2, Antifundamental)],
        ColorTensor::new(vec![string(1, &[], 2)], vec![]),
    )
}
fn image(
    legs: &[ColorLeg],
    tensor: &ColorTensor,
    emissions: Vec<ColorEmission>,
) -> ConnectedColorTensor {
    ColorConnection::new(legs.to_vec(), emissions)
        .unwrap()
        .apply(tensor, coefficient(1, 0))
        .unwrap()
}
fn emit(emitter: i64, emitted: i64) -> ColorEmission {
    EmitGluon { emitter, emitted }
}
fn polynomial(values: &[(i64, i64, i64)]) -> ColorNcTerms {
    values
        .iter()
        .map(|&(power, numerator, denominator)| (power, real(numerator, denominator)))
        .collect()
}

#[test]
fn exact_casimirs_and_arbitrary_order_laurent_coefficients() {
    let (legs, tensor) = qq();
    let identity = image(&legs, &tensor, vec![]);
    assert_eq!(identity.overlap(&identity).unwrap(), coefficient(3, 0));
    let quark = image(&legs, &tensor, vec![emit(1, 3)]);
    let antiquark = image(&legs, &tensor, vec![emit(2, 3)]);
    assert_eq!(
        quark.overlap_nc_terms(&quark).unwrap(),
        polynomial(&[(2, 1, 2), (0, -1, 2)])
    );
    assert_eq!(quark.overlap(&quark).unwrap(), coefficient(4, 0));
    assert_eq!(antiquark.overlap(&antiquark).unwrap(), coefficient(4, 0));
    assert_eq!(quark.overlap(&antiquark).unwrap(), coefficient(-4, 0));
    let double = image(&legs, &tensor, vec![emit(1, 3), emit(1, 4)]);
    let reversed = image(&legs, &tensor, vec![emit(1, 4), emit(1, 3)]);
    assert_eq!(
        double.overlap_nc_terms(&double).unwrap(),
        polynomial(&[(3, 1, 4), (1, -1, 2), (-1, 1, 4)])
    );
    assert_eq!(double.overlap(&double).unwrap(), real(16, 3));
    assert_eq!(double.overlap(&reversed).unwrap(), real(-2, 3));
    let triple = image(&legs, &tensor, vec![emit(1, 3), emit(1, 4), emit(1, 5)]);
    assert_eq!(
        triple.overlap_nc_terms(&triple).unwrap(),
        polynomial(&[(4, 1, 8), (2, -3, 8), (0, 3, 8), (-2, -1, 8)])
    );
    assert_eq!(
        evaluate_nc_terms(&quark.overlap_nc_terms(&quark).unwrap(), 5).unwrap(),
        coefficient(12, 0)
    );
}

#[test]
fn splitting_emitted_gluon_and_traceless_cancellation() {
    let (legs, tensor) = qq();
    let split = image(
        &legs,
        &tensor,
        vec![
            emit(1, 3),
            SplitGluon {
                parent: 3,
                quark: 4,
                antiquark: 5,
            },
        ],
    );
    assert_eq!(
        split.overlap_nc_terms(&split).unwrap(),
        polynomial(&[(2, 1, 4), (0, -1, 4)])
    );
    assert_eq!(split.overlap(&split).unwrap(), coefficient(2, 0));
    // tr(tau[a]) is zero, including after its exact Fierz splitting.
    let traced = ColorTensor::new(vec![], vec![vec![1]]);
    let zero = image(
        &[leg(1, Adjoint)],
        &traced,
        vec![SplitGluon {
            parent: 1,
            quark: 2,
            antiquark: 3,
        }],
    );
    assert!(zero.terms().is_empty());
}

#[test]
fn quark_gluon_color_conservation_and_dipole_rows() {
    let legs = vec![
        leg(1, Fundamental),
        leg(2, Antifundamental),
        leg(3, Adjoint),
    ];
    let tensor = ColorTensor::new(vec![string(1, &[3], 2)], vec![]);
    let identity = image(&legs, &tensor, vec![]);
    assert_eq!(identity.overlap(&identity).unwrap(), coefficient(8, 0));
    let images: Vec<_> = (1..=3)
        .map(|emitter| image(&legs, &tensor, vec![emit(emitter, 4)]))
        .collect();
    let combined = ConnectedColorTensor::new(
        images[0].legs().to_vec(),
        images
            .iter()
            .flat_map(|image| image.terms().to_vec())
            .collect(),
        1,
    )
    .unwrap();
    assert!(combined.terms().is_empty());
    for (i, left) in images.iter().enumerate() {
        let mut row = zero();
        for right in &images {
            add_assign(&mut row, left.overlap(right).unwrap());
        }
        assert!(is_zero(&row));
        assert_eq!(
            left.overlap(left).unwrap(),
            if i == 2 {
                coefficient(24, 0)
            } else {
                real(32, 3)
            }
        );
    }
}

#[test]
fn full_gram_and_noncommuting_shared_leg_double_correlations() {
    let legs = vec![
        leg(1, Fundamental),
        leg(2, Antifundamental),
        leg(3, Fundamental),
        leg(4, Antifundamental),
    ];
    let direct = ColorTensor::new(vec![string(1, &[], 2), string(3, &[], 4)], vec![]);
    let crossed = ColorTensor::new(vec![string(1, &[], 4), string(3, &[], 2)], vec![]);
    let basis = [&direct, &crossed];
    let identity: Vec<_> = basis
        .iter()
        .map(|tensor| image(&legs, tensor, vec![]))
        .collect();
    assert_eq!(
        identity[0].overlap(&identity[0]).unwrap(),
        coefficient(9, 0)
    );
    assert_eq!(
        identity[0].overlap(&identity[1]).unwrap(),
        coefficient(3, 0)
    );
    let bra: Vec<_> = basis
        .iter()
        .map(|tensor| image(&legs, tensor, vec![emit(3, -1), emit(1, -2)]))
        .collect();
    let ket_ab: Vec<_> = basis
        .iter()
        .map(|tensor| image(&legs, tensor, vec![emit(2, -2), emit(2, -1)]))
        .collect();
    let ket_ba: Vec<_> = basis
        .iter()
        .map(|tensor| image(&legs, tensor, vec![emit(2, -1), emit(2, -2)]))
        .collect();
    let ab = [[real(0, 1), real(-2, 3)], [real(16, 3), real(0, 1)]];
    for i in 0..2 {
        for j in 0..2 {
            assert_eq!(bra[i].overlap(&ket_ab[j]).unwrap(), ab[i][j]);
            assert_eq!(bra[i].overlap(&ket_ba[j]).unwrap(), ab[j][i]);
        }
    }
    let mut anticommutator = bra[0].overlap(&ket_ab[1]).unwrap();
    add_assign(&mut anticommutator, bra[0].overlap(&ket_ba[1]).unwrap());
    assert_eq!(anticommutator, real(14, 3));
}

#[test]
fn trace_orientation_and_complex_sesquilinearity() {
    let legs = vec![leg(1, Adjoint), leg(2, Adjoint), leg(3, Adjoint)];
    let tensor = ColorTensor::new(vec![], vec![vec![1, 2, 3]]);
    let cyclic = ColorTensor::new(vec![], vec![vec![3, 1, 2]]);
    let reflected = ColorTensor::new(vec![], vec![vec![1, 3, 2]]);
    assert_eq!(tensor, cyclic);
    assert_ne!(tensor, reflected);
    let left = image(&legs, &tensor, vec![]);
    let right = image(&legs, &reflected, vec![]);
    assert_eq!(left.overlap(&left).unwrap(), real(56, 3));
    assert_eq!(left.overlap(&right).unwrap(), real(-16, 3));
    // Trace splitting contracts the same adjoint with t^a: T_R = 1/2.
    let split = image(
        &legs,
        &tensor,
        vec![SplitGluon {
            parent: 2,
            quark: 4,
            antiquark: 5,
        }],
    );
    assert_eq!(split.overlap(&split).unwrap(), real(28, 3));
    let (legs, tensor) = qq();
    let connection = ColorConnection::new(legs, vec![]).unwrap();
    let left = connection.apply(&tensor, coefficient(1, 2)).unwrap();
    let right = connection.apply(&tensor, coefficient(3, -1)).unwrap();
    assert_eq!(left.overlap(&right).unwrap(), coefficient(3, -21));
    assert_eq!(right.overlap(&left).unwrap(), coefficient(3, 21));
}

#[test]
fn invalid_connections_and_mismatched_domains_are_errors() {
    let (legs, tensor) = qq();
    for emissions in [
        vec![emit(9, 3)],
        vec![emit(1, 2)],
        vec![SplitGluon {
            parent: 1,
            quark: 3,
            antiquark: 4,
        }],
        vec![
            emit(1, 3),
            SplitGluon {
                parent: 3,
                quark: 4,
                antiquark: 4,
            },
        ],
        vec![
            emit(1, 3),
            SplitGluon {
                parent: 3,
                quark: 4,
                antiquark: 5,
            },
            emit(3, 6),
        ],
        vec![
            emit(1, 3),
            SplitGluon {
                parent: 3,
                quark: 4,
                antiquark: 5,
            },
            emit(4, 3),
        ],
    ] {
        assert!(ColorConnection::new(legs.clone(), emissions).is_err());
    }
    assert!(ColorConnection::new(vec![legs[0], legs[0]], vec![]).is_err());
    let singlet = ColorConnection::new(vec![leg(1, Singlet)], vec![emit(1, 2)]);
    assert!(singlet.is_err());
    assert!(
        ColorConnection::new(legs.clone(), vec![])
            .unwrap()
            .apply(&ColorTensor::new(vec![], vec![]), coefficient(1, 0))
            .is_err()
    );
    let identity = image(&legs, &tensor, vec![]);
    let emitted = image(&legs, &tensor, vec![emit(1, 3)]);
    assert!(identity.overlap(&emitted).is_err());
    let odd = ConnectedColorTensor::new(legs.clone(), identity.terms().to_vec(), 1).unwrap();
    assert!(identity.overlap(&odd).is_err());
    let overflow = ConnectedColorTensor::new(
        legs,
        vec![TensorTerm {
            coefficient: coefficient(1, 0),
            tensor,
            nc_power: i64::MAX,
        }],
        0,
    )
    .unwrap();
    assert!(overflow.overlap(&overflow).is_err());
    assert!(evaluate_nc_terms(&ColorNcTerms::new(), 1).is_err());
    assert_eq!(
        ColorLeg::all_outgoing(1, Fundamental, true).representation,
        Antifundamental
    );
    assert_eq!(
        ColorLeg::all_outgoing(1, Adjoint, true).representation,
        Adjoint
    );
}

fn ufo_qqg(value: &str) -> ConnectedColorTensor {
    use network::{UfoColorIndex, reduce_network, ufo_color_network};
    let expression = symbolica::atom::Atom::parse(value, "UFO", Default::default()).unwrap();
    reduce_network(
        &ufo_color_network(&expression, &[Antifundamental, Fundamental, Adjoint]).unwrap(),
        vec![
            leg(1, Fundamental),
            leg(2, Antifundamental),
            leg(3, Adjoint),
        ],
        &BTreeMap::from([
            (UfoColorIndex::Leg(1), 1),
            (UfoColorIndex::Leg(2), 2),
            (UfoColorIndex::Leg(3), 3),
        ]),
    )
    .unwrap()
}

#[test]
fn splitting_color_matches_direct_symmetric_ufo_network() {
    // This oracle inserts d^{AcB} and t^c directly, independently of the
    // splitting connections. The physical-t basis has norm (Nc²-1)/2.
    let base = ufo_qqg("T(3,2,1)");
    let direct_d = ufo_qqg("d(3,-1,-2)*T(-1,2,-3)*T(-2,-3,1)");
    let pair = GluonSplittingColorPair::new(base.legs().to_vec(), 3, 1, 4, 5, 6).unwrap();
    let raw = pair.raw_daughter_nc_terms(&base, &base).unwrap();
    assert_eq!(raw.quark, polynomial(&[(1, -1, 4), (-1, 1, 4)]));
    assert_eq!(
        raw.antiquark,
        polynomial(&[(3, -1, 8), (1, 3, 8), (-1, -1, 4)])
    );
    let result = pair.symmetric_adjoint_nc_terms(&base, &base).unwrap();
    assert_eq!(result, base.overlap_nc_terms(&direct_d).unwrap());
    assert_eq!(result, polynomial(&[(3, 1, 4), (1, -5, 4), (-1, 1, 1)]));
    assert_eq!(evaluate_nc_terms(&result, 3).unwrap(), real(10, 3));
    assert_eq!(evaluate_nc_terms(&result, 2).unwrap(), real(0, 1));
    let anti_pair = GluonSplittingColorPair::new(base.legs().to_vec(), 3, 2, 4, 5, 6).unwrap();
    assert_eq!(
        evaluate_nc_terms(
            &anti_pair.symmetric_adjoint_nc_terms(&base, &base).unwrap(),
            3
        )
        .unwrap(),
        real(-10, 3)
    );
}

#[test]
fn splitting_color_normalized_daughter_sum_is_parent_dipole() {
    let legs = vec![
        leg(1, Fundamental),
        leg(2, Antifundamental),
        leg(3, Adjoint),
        leg(4, Adjoint),
    ];
    let forward = ColorTensor::new(vec![string(1, &[3, 4], 2)], vec![]);
    let reverse = ColorTensor::new(vec![string(1, &[4, 3], 2)], vec![]);
    let bra = ConnectedColorTensor::new(
        legs.clone(),
        vec![
            TensorTerm {
                coefficient: coefficient(1, 2),
                tensor: forward.clone(),
                nc_power: 2,
            },
            TensorTerm {
                coefficient: coefficient(2, -1),
                tensor: reverse.clone(),
                nc_power: -1,
            },
        ],
        3,
    )
    .unwrap();
    let ket = ConnectedColorTensor::new(
        legs.clone(),
        vec![
            TensorTerm {
                coefficient: coefficient(3, -1),
                tensor: reverse,
                nc_power: -3,
            },
            TensorTerm {
                coefficient: coefficient(-1, 3),
                tensor: forward,
                nc_power: 1,
            },
        ],
        1,
    )
    .unwrap();
    for spectator in [1, 2, 4] {
        let pair = GluonSplittingColorPair::new(legs.clone(), 3, spectator, 5, 6, 7).unwrap();
        let raw = pair.raw_daughter_nc_terms(&bra, &ket).unwrap();
        let mut normalized_sum = ColorNcTerms::new();
        for terms in [&raw.quark, &raw.antiquark] {
            for (&power, value) in terms {
                add_coefficient(&mut normalized_sum, power, scale(value, &Rational::from(2)));
            }
        }
        normalized_sum.retain(|_, value| !is_zero(value));
        let parent = ColorConnection::new(legs.clone(), vec![emit(3, 7)]).unwrap();
        let spectator = ColorConnection::new(legs.clone(), vec![emit(spectator, 7)]).unwrap();
        assert_eq!(
            normalized_sum,
            parent
                .apply_connected(&bra)
                .unwrap()
                .overlap_nc_terms(&spectator.apply_connected(&ket).unwrap())
                .unwrap()
        );
    }
}

#[test]
fn splitting_color_preserves_directed_phases_laurent_powers_and_normalizations() {
    let base = ufo_qqg("T(3,2,1)");
    let input = |value, nc_power| {
        ConnectedColorTensor::new(
            base.legs().to_vec(),
            vec![TensorTerm {
                coefficient: value,
                tensor: base.terms()[0].tensor.clone(),
                nc_power,
            }],
            base.normalization_power() + 2,
        )
        .unwrap()
    };
    let bra = input(coefficient(1, 2), 2);
    let ket = input(coefficient(3, -1), -1);
    let pair = GluonSplittingColorPair::new(base.legs().to_vec(), 3, 1, -1, -2, -3).unwrap();
    let result = pair.symmetric_adjoint_nc_terms(&bra, &ket).unwrap();
    // conj(1+2i)*(3-i)=1-7i, Laurent shift 2-1=1, and four extra
    // inverse-sqrt(2) powers give a factor 1/4 relative to physical t.
    let expected: ColorNcTerms = [(4, 1, 16), (2, -5, 16), (0, 1, 4)]
        .into_iter()
        .map(|(power, numerator, denominator)| {
            (
                power,
                Complex::new(
                    Rational::from((numerator, denominator)),
                    Rational::from((-7 * numerator, denominator)),
                ),
            )
        })
        .collect();
    assert_eq!(result, expected);
    assert_eq!(
        evaluate_nc_terms(&result, 3).unwrap(),
        Complex::new(Rational::from((5, 2)), Rational::from((-35, 2)),)
    );
    let reversed = pair.symmetric_adjoint_nc_terms(&ket, &bra).unwrap();
    for (&power, value) in &result {
        assert_eq!(
            reversed.get(&power).unwrap(),
            &Complex::new(value.re.clone(), -value.im.clone())
        );
    }
}

#[test]
fn splitting_color_rejects_invalid_domains_and_normalizations() {
    let base = ufo_qqg("T(3,2,1)");
    let legs = base.legs().to_vec();
    for (parent, spectator, q, qbar, emitted) in [
        (1, 2, 4, 5, 6), // parent is fundamental
        (3, 3, 4, 5, 6), // coincident parent and spectator
        (3, 9, 4, 5, 6), // absent spectator
        (3, 1, 3, 5, 6), // a retired label is not fresh
        (3, 1, 4, 4, 6), // daughters coincide
        (3, 1, 4, 5, 4), // emission reuses a daughter
    ] {
        assert!(
            GluonSplittingColorPair::new(legs.clone(), parent, spectator, q, qbar, emitted)
                .is_err()
        );
    }
    let mut singlet_legs = legs.clone();
    singlet_legs.push(leg(9, Singlet));
    assert!(GluonSplittingColorPair::new(singlet_legs, 3, 9, 4, 5, 6).is_err());
    let pair = GluonSplittingColorPair::new(legs.clone(), 3, 1, 4, 5, 6).unwrap();
    let odd = ConnectedColorTensor::new(legs.clone(), base.terms().to_vec(), 0).unwrap();
    assert!(pair.symmetric_adjoint_nc_terms(&base, &odd).is_err());
    let overflow =
        ConnectedColorTensor::new(legs.clone(), base.terms().to_vec(), u32::MAX).unwrap();
    assert!(pair.symmetric_adjoint_nc_terms(&overflow, &base).is_err());
    let (other_legs, other_tensor) = qq();
    let other = image(&other_legs, &other_tensor, vec![]);
    assert!(pair.symmetric_adjoint_nc_terms(&base, &other).is_err());
    assert!(
        ColorConnection::new(other_legs, vec![])
            .unwrap()
            .apply_connected(&base)
            .is_err()
    );
}
