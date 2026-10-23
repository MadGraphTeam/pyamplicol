// SPDX-License-Identifier: 0BSD

use super::*;
use ColorRepresentation::*;

fn leg(label: i64, representation: ColorRepresentation) -> ColorLeg {
    ColorLeg {
        label,
        representation,
    }
}
fn value(real: i64, imaginary: i64) -> ExactColorCoefficient {
    Complex::new(Rational::from(real), Rational::from(imaginary))
}
fn string(q: i64, word: &[i64], qb: i64) -> OpenColorString {
    OpenColorString {
        fundamental: q,
        adjoints: word.to_vec(),
        antifundamental: qb,
    }
}
fn connected(legs: &[ColorLeg], tensor: ColorTensor) -> ConnectedColorTensor {
    ConnectedColorTensor::new(
        legs.to_vec(),
        vec![TensorTerm {
            coefficient: value(1, 0),
            tensor,
            nc_power: 0,
        }],
        0,
    )
    .unwrap()
}
fn fixtures() -> Vec<Vec<ConnectedColorTensor>> {
    let qq = [leg(1, Fundamental), leg(2, Antifundamental)];
    let qqgg = [
        leg(1, Fundamental),
        leg(2, Antifundamental),
        leg(3, Adjoint),
        leg(4, Adjoint),
    ];
    let ggg = [leg(1, Adjoint), leg(2, Adjoint), leg(3, Adjoint)];
    let fourq = [
        leg(1, Fundamental),
        leg(2, Antifundamental),
        leg(3, Fundamental),
        leg(4, Antifundamental),
    ];
    vec![
        vec![connected(
            &qq,
            ColorTensor::new(vec![string(1, &[], 2)], vec![]),
        )],
        vec![
            connected(&qqgg, ColorTensor::new(vec![string(1, &[3, 4], 2)], vec![])),
            connected(&qqgg, ColorTensor::new(vec![string(1, &[4, 3], 2)], vec![])),
        ],
        vec![
            connected(&ggg, ColorTensor::new(vec![], vec![vec![1, 2, 3]])),
            connected(&ggg, ColorTensor::new(vec![], vec![vec![1, 3, 2]])),
        ],
        vec![
            connected(
                &fourq,
                ColorTensor::new(vec![string(1, &[], 2), string(3, &[], 4)], vec![]),
            ),
            connected(
                &fourq,
                ColorTensor::new(vec![string(1, &[], 4), string(3, &[], 2)], vec![]),
            ),
        ],
    ]
}
fn emission(input: &ConnectedColorTensor, emitter: i64, emitted: i64) -> ConnectedColorTensor {
    ColorConnection::new(
        input.legs().to_vec(),
        vec![ColorEmission::EmitGluon { emitter, emitted }],
    )
    .unwrap()
    .apply_connected(input)
    .unwrap()
}
fn conjugate(input: &ColorNcTerms) -> ColorNcTerms {
    input
        .iter()
        .map(|(&power, coefficient)| {
            (
                power,
                Complex::new(coefficient.re.clone(), -coefficient.im.clone()),
            )
        })
        .collect()
}

#[test]
fn pair_actions_match_independent_bra_ket_emissions_for_all_representations() {
    for basis in fixtures() {
        let legs = basis[0].legs();
        for left in legs {
            for right in legs {
                let action = ColorDipole::new(legs.to_vec(), left.label, right.label).unwrap();
                for bra in &basis {
                    for ket in &basis {
                        let direct = emission(bra, left.label, 99)
                            .overlap_nc_terms(&emission(ket, right.label, 99))
                            .unwrap();
                        assert_eq!(action.matrix_element_nc_terms(bra, ket).unwrap(), direct);
                        assert_eq!(
                            action.matrix_element_nc_terms(bra, ket).unwrap(),
                            conjugate(&action.matrix_element_nc_terms(ket, bra).unwrap()),
                        );
                    }
                }
            }
        }
    }
}

#[test]
fn diagonal_actions_and_color_conservation_hold_at_symbolic_nc() {
    for basis in fixtures() {
        for ket in &basis {
            for first in ket.legs() {
                let diagonal = ColorDipole::new(ket.legs().to_vec(), first.label, first.label)
                    .unwrap()
                    .matrix_element_nc_terms(ket, ket)
                    .unwrap();
                let norm = ket.overlap_nc_terms(ket).unwrap();
                let mut expected = ColorNcTerms::new();
                let shifts: &[(i64, i64, i64)] = if first.representation == Adjoint {
                    &[(1, 1, 1)]
                } else {
                    &[(1, 1, 2), (-1, -1, 2)]
                };
                for (&power, coefficient) in &norm {
                    for &(shift, numerator, denominator) in shifts {
                        add_coefficient(
                            &mut expected,
                            power + shift,
                            scale(coefficient, &Rational::from((numerator, denominator))),
                        );
                    }
                }
                expected.retain(|_, coefficient| !is_zero(coefficient));
                assert_eq!(diagonal, expected);
                // Check the sum of actions as tensors, not merely its overlap
                // with one selected bra. These fixtures span open and traced
                // invariant color networks, including adjoint charges.
                let mut terms = Vec::new();
                for second in ket.legs() {
                    let image = ColorDipole::new(ket.legs().to_vec(), first.label, second.label)
                        .unwrap()
                        .apply_connected(ket)
                        .unwrap();
                    assert_eq!(image.normalization_power(), 0);
                    terms.extend(image.terms().to_vec());
                }
                let total = ConnectedColorTensor::new(ket.legs().to_vec(), terms, 0).unwrap();
                assert!(total.terms().is_empty());
            }
        }
    }
}

#[test]
fn overlapping_products_preserve_noncommutation_and_directed_phases() {
    let basis = fixtures().pop().unwrap();
    let legs = basis[0].legs().to_vec();
    let a_then_b = ColorDipoleProduct::new(legs.clone(), vec![[1, 2], [2, 3]]).unwrap();
    let b_then_a = ColorDipoleProduct::new(legs, vec![[2, 3], [1, 2]]).unwrap();
    // Independent emitted-index contractions, with the shared leg's order
    // fixed explicitly. Their SU(3) entries are also known rational values.
    let expected = [[(0, 1), (16, 3)], [(-2, 3), (0, 1)]];
    for (i, bra) in basis.iter().enumerate() {
        for (j, ket) in basis.iter().enumerate() {
            let left = ColorConnection::new(
                bra.legs().to_vec(),
                vec![
                    ColorEmission::EmitGluon {
                        emitter: 3,
                        emitted: 91,
                    },
                    ColorEmission::EmitGluon {
                        emitter: 1,
                        emitted: 92,
                    },
                ],
            )
            .unwrap()
            .apply_connected(bra)
            .unwrap();
            let right = ColorConnection::new(
                ket.legs().to_vec(),
                vec![
                    ColorEmission::EmitGluon {
                        emitter: 2,
                        emitted: 91,
                    },
                    ColorEmission::EmitGluon {
                        emitter: 2,
                        emitted: 92,
                    },
                ],
            )
            .unwrap()
            .apply_connected(ket)
            .unwrap();
            let ab = a_then_b.matrix_element_nc_terms(bra, ket).unwrap();
            assert_eq!(ab, left.overlap_nc_terms(&right).unwrap());
            let (n, d) = expected[i][j];
            assert_eq!(
                evaluate_nc_terms(&ab, 3).unwrap(),
                Complex::new(Rational::from((n, d)), Rational::from(0))
            );
            assert_eq!(
                ab,
                conjugate(&b_then_a.matrix_element_nc_terms(ket, bra).unwrap())
            );
        }
    }
    assert_ne!(
        a_then_b
            .matrix_element_nc_terms(&basis[0], &basis[1])
            .unwrap(),
        b_then_a
            .matrix_element_nc_terms(&basis[0], &basis[1])
            .unwrap()
    );
}

#[test]
fn exact_complex_normalizations_laurent_powers_and_long_products_survive() {
    let base = fixtures().remove(0).remove(0);
    let mut terms = base.terms().to_vec();
    terms[0].coefficient = value(2, -3);
    terms[0].nc_power = -2;
    let input = ConnectedColorTensor::new(base.legs().to_vec(), terms, 5).unwrap();
    let product = ColorDipoleProduct::new(base.legs().to_vec(), vec![[1, 2]; 3]).unwrap();
    let result = product.apply_connected(&input).unwrap();
    assert_eq!(result.normalization_power(), 1);
    let got = input.overlap_nc_terms(&result).unwrap();
    // In the singlet qq space, P12=-CF. Check several Nc values, all exact,
    // while retaining the input's complex coefficient and odd root2 parity.
    for nc in [2, 3, 5, 11] {
        let norm = evaluate_nc_terms(&input.overlap_nc_terms(&input).unwrap(), nc).unwrap();
        let casimir = Rational::from((i64::from(nc * nc - 1), 2 * i64::from(nc)));
        assert_eq!(
            evaluate_nc_terms(&got, nc).unwrap(),
            scale(&norm, &-casimir.pow(3))
        );
    }
    let mut terms = base.terms().to_vec();
    terms[0].coefficient = value(3, 1);
    terms[0].nc_power = 1;
    let bra = ConnectedColorTensor::new(base.legs().to_vec(), terms, 3).unwrap();
    let phase = product.matrix_element_nc_terms(&bra, &input).unwrap();
    assert_eq!(
        evaluate_nc_terms(&phase, 3).unwrap(),
        scale(&value(3, -11), &Rational::from((-4, 27))),
    );
    let zero = ConnectedColorTensor::new(input.legs().to_vec(), vec![], 5).unwrap();
    let zero = product.apply_connected(&zero).unwrap();
    assert_eq!(zero.normalization_power(), 1);
    assert!(input.overlap_nc_terms(&zero).unwrap().is_empty());
}

#[test]
fn tripole_sign_matches_direct_structure_constant_closure() {
    use network::{UfoColorIndex, multiply, ufo_color_network};
    use symbolica::atom::Atom;
    #[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd)]
    enum Label {
        External(i64),
        Charge(i64),
    }
    let basis = fixtures().pop().unwrap();
    let legs = basis[0].legs().to_vec();
    let ab = ColorDipoleProduct::new(legs.clone(), vec![[1, 2], [2, 3]]).unwrap();
    let ba = ColorDipoleProduct::new(legs.clone(), vec![[2, 3], [1, 2]]).unwrap();
    let raw_f = ufo_color_network(
        &Atom::parse("f(1,2,3)", "UFO", Default::default()).unwrap(),
        &[Adjoint; 3],
    )
    .unwrap()
    .iter()
    .map(|term| {
        term.relabel(|label| match label {
            UfoColorIndex::Leg(n) => Label::Charge(*n as i64),
            _ => panic!("three-leg f tensor has no independent dummy"),
        })
    })
    .collect::<Vec<_>>();
    // The connection API uses literal q-to-qbar generator words. Its
    // f_abc=-i/sqrt(2) [tr(tau_a tau_b tau_c)-tr(tau_a tau_c tau_b)]
    // must be translated to the network's opposite matrix orientation just
    // like every ket word below. For this antisymmetric tensor the reversal
    // changes the sign; raw model/UFO f cannot be mixed into literal words
    // without this conversion. An independent Pauli-matrix oracle below fixes
    // the physical sign without relying on either network implementation.
    let f = raw_f
        .iter()
        .cloned()
        .map(|mut term| {
            for trace in &mut term.traces {
                trace.reverse();
            }
            term
        })
        .collect::<Vec<_>>();
    let pauli = explicit_su2_tripole();
    assert_eq!(
        pauli,
        [
            [value(0, 0), scale(&value(0, 3), &Rational::from((1, 2)))],
            [scale(&value(0, -3), &Rational::from((1, 2))), value(0, 0)]
        ]
    );
    for (ket_index, ket) in basis.iter().enumerate() {
        let mut emitted = ket.clone();
        for (emitter, label) in [(1, 91), (2, 92), (3, 93)] {
            emitted = emission(&emitted, emitter, label);
        }
        let rename = |label: i64| {
            if (91..=93).contains(&label) {
                Label::Charge(label - 90)
            } else {
                Label::External(label)
            }
        };
        let ket_network = emitted
            .terms()
            .iter()
            .map(|term| ColorProduct {
                coefficient: term.coefficient.clone(),
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
            .collect::<Vec<_>>();
        let external = legs
            .iter()
            .map(|leg| (Label::External(leg.label), leg.label))
            .collect();
        let direct = reduce_network(
            &multiply(&ket_network, &f).unwrap(),
            legs.clone(),
            &external,
        )
        .unwrap();
        let unconverted = reduce_network(
            &multiply(&ket_network, &raw_f).unwrap(),
            legs.clone(),
            &external,
        )
        .unwrap();
        for (bra_index, bra) in basis.iter().enumerate() {
            let mut commutator = ab.matrix_element_nc_terms(bra, ket).unwrap();
            for (power, coefficient) in ba.matrix_element_nc_terms(bra, ket).unwrap() {
                add_coefficient(
                    &mut commutator,
                    power,
                    scale(&coefficient, &Rational::from(-1)),
                );
            }
            commutator.retain(|_, coefficient| !is_zero(coefficient));
            for coefficient in commutator.values_mut() {
                *coefficient = Complex::new(-coefficient.im.clone(), coefficient.re.clone());
            }
            // [P12,P23] = -i f_abc T1^a T2^b T3^c.
            assert_eq!(commutator, bra.overlap_nc_terms(&direct).unwrap());
            assert_eq!(
                evaluate_nc_terms(&commutator, 2).unwrap(),
                pauli[bra_index][ket_index]
            );
            let raw = bra.overlap_nc_terms(&unconverted).unwrap();
            assert_eq!(
                commutator,
                raw.into_iter()
                    .map(|(power, coefficient)| (power, scale(&coefficient, &Rational::from(-1))))
                    .collect()
            );
        }
    }
}

// Independent finite-dimensional charge contraction: t=Pauli/2,
// anti-quark charge=-transpose(t), f_abc=epsilon_abc. No ColorConnection,
// network reduction, trace formula or dipole product enters this oracle.
fn explicit_su2_tripole() -> [[ExactColorCoefficient; 2]; 2] {
    let product = |left: &ExactColorCoefficient, right: &ExactColorCoefficient| {
        Complex::new(
            &left.re * &right.re - &left.im * &right.im,
            &left.re * &right.im + &left.im * &right.re,
        )
    };
    let t = [
        [[value(0, 0), value(1, 0)], [value(1, 0), value(0, 0)]],
        [[value(0, 0), value(0, -1)], [value(0, 1), value(0, 0)]],
        [[value(1, 0), value(0, 0)], [value(0, 0), value(-1, 0)]],
    ];
    let permutations = [
        (0, 1, 2, 1),
        (1, 2, 0, 1),
        (2, 0, 1, 1),
        (0, 2, 1, -1),
        (2, 1, 0, -1),
        (1, 0, 2, -1),
    ];
    let mut answer = [[value(0, 0), value(0, 0)], [value(0, 0), value(0, 0)]];
    let indices = |n: usize| [n & 1, (n >> 1) & 1, (n >> 2) & 1, (n >> 3) & 1];
    let basis = |v: [usize; 4]| [v[0] == v[1] && v[2] == v[3], v[0] == v[3] && v[2] == v[1]];
    for output in 0..16 {
        let out = indices(output);
        for input in 0..16 {
            let inn = indices(input);
            if out[3] != inn[3] {
                continue;
            }
            for (a, b, c, epsilon) in permutations {
                let element = scale(
                    &product(
                        &product(&t[a][out[0]][inn[0]], &t[b][inn[1]][out[1]]),
                        &t[c][out[2]][inn[2]],
                    ),
                    &Rational::from((-epsilon, 8)),
                );
                for (bra, selected_bra) in basis(out).into_iter().enumerate() {
                    for (ket, selected_ket) in basis(inn).into_iter().enumerate() {
                        if selected_bra && selected_ket {
                            answer[bra][ket].re += &element.re;
                            answer[bra][ket].im += &element.im;
                        }
                    }
                }
            }
        }
    }
    answer
}

#[test]
fn original_label_validation_and_extreme_labels_are_explicit() {
    let legs = vec![
        leg(i64::MIN, Fundamental),
        leg(i64::MAX, Antifundamental),
        leg(0, Singlet),
    ];
    let input = connected(
        &legs,
        ColorTensor::new(vec![string(i64::MIN, &[], i64::MAX)], vec![]),
    );
    let pair = ColorDipole::new(legs.clone(), i64::MIN, i64::MAX).unwrap();
    assert_eq!(
        evaluate_nc_terms(&pair.matrix_element_nc_terms(&input, &input).unwrap(), 3).unwrap(),
        value(-4, 0)
    );
    for (left, right) in [
        (0, i64::MIN),
        (i64::MIN + 1, i64::MIN),
        (i64::MIN, i64::MIN + 1),
    ] {
        assert!(ColorDipole::new(legs.clone(), left, right).is_err());
    }
    let identity = ColorDipoleProduct::new(legs.clone(), vec![]).unwrap();
    let copy = identity.apply_connected(&input).unwrap();
    assert_eq!(copy.terms(), input.terms());
    assert_eq!(copy.normalization_power(), input.normalization_power());
    let wrong = connected(
        &[leg(1, Fundamental), leg(2, Antifundamental)],
        ColorTensor::new(vec![string(1, &[], 2)], vec![]),
    );
    assert!(identity.apply_connected(&wrong).is_err());
    assert!(pair.apply_connected(&wrong).is_err());
    let overflow = ConnectedColorTensor::new(legs, input.terms().to_vec(), u32::MAX).unwrap();
    assert!(pair.apply_connected(&overflow).is_err());
}

#[test]
fn crossing_uses_conjugated_representations_without_an_extra_sign() {
    let legs = vec![
        ColorLeg::all_outgoing(-11, Fundamental, true),
        ColorLeg::all_outgoing(-12, Adjoint, true),
        ColorLeg::all_outgoing(23, Fundamental, false),
    ];
    let tensor = connected(
        &legs,
        ColorTensor::new(vec![string(23, &[-12], -11)], vec![]),
    );
    let quark_gluon = ColorDipole::new(legs.clone(), -11, -12).unwrap();
    assert_eq!(
        evaluate_nc_terms(
            &quark_gluon
                .matrix_element_nc_terms(&tensor, &tensor)
                .unwrap(),
            3
        )
        .unwrap(),
        value(-12, 0),
    );
    let crossed_quarks = ColorDipole::new(legs, -11, 23).unwrap();
    assert_eq!(
        evaluate_nc_terms(
            &crossed_quarks
                .matrix_element_nc_terms(&tensor, &tensor)
                .unwrap(),
            3
        )
        .unwrap(),
        Complex::new(Rational::from((4, 3)), Rational::from(0)),
    );
}
