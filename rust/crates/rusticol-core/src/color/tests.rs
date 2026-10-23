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
