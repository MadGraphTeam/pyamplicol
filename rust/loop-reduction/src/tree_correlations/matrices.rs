// SPDX-License-Identifier: 0BSD

//! Directed exact insertion matrices, built from full ket tensor actions.
//!
//! Rows are bras and columns are kets in the caller's retained basis order.
//! The basis need not be orthogonal or linearly independent. In particular,
//! overlap matrices are never multiplied or inverted to represent products.

use rusticol_core::{
    RusticolError, RusticolResult,
    color::{
        ColorDipole, ColorDipoleProduct, ColorNcTerms, ConnectedColorTensor, ExactColorCoefficient,
        evaluate_nc_terms,
    },
};
use symbolica::domains::{float::Complex, rational::Rational};

use super::TreeColorInsertion;

/// Preserve request order and multiplicity, including repeated factors.
pub(super) fn prepare_matrices(
    basis: &[ConnectedColorTensor],
    requests: &[TreeColorInsertion],
) -> RusticolResult<Vec<Vec<Vec<ColorNcTerms>>>> {
    let Some(first) = basis.first() else {
        return Err(RusticolError::invalid_argument(
            "tree color insertion matrices require a nonempty basis",
        ));
    };
    if basis.iter().any(|tensor| tensor.legs() != first.legs()) {
        return Err(RusticolError::invalid_argument(
            "tree color basis tensors must have identical typed legs",
        ));
    }
    if requests.is_empty() {
        return Err(RusticolError::invalid_argument(
            "tree color insertion requests must not be empty",
        ));
    }
    let legs = first.legs();
    requests
        .iter()
        .map(|request| match request {
            TreeColorInsertion::Identity => basis
                .iter()
                .map(|bra| basis.iter().map(|ket| bra.overlap_nc_terms(ket)).collect())
                .collect(),
            TreeColorInsertion::Pair { left, right } => {
                let action = ColorDipole::new(legs.to_vec(), *left, *right)?;
                from_action(basis, |ket| action.apply_connected(ket))
            }
            TreeColorInsertion::OrderedProduct(pairs) => {
                if pairs.is_empty() {
                    return Err(RusticolError::invalid_argument(
                        "an ordered tree color product must contain at least one pair; use Identity for the empty product",
                    ));
                }
                let action = ColorDipoleProduct::new(legs.to_vec(), pairs.clone())?;
                from_action(basis, |ket| action.apply_connected(ket))
            }
            TreeColorInsertion::Anticommutator { first, second } => {
                let ab = ColorDipoleProduct::new(legs.to_vec(), vec![*first, *second])?;
                let ba = ColorDipoleProduct::new(legs.to_vec(), vec![*second, *first])?;
                let mut matrix = from_action(basis, |ket| ab.apply_connected(ket))?;
                let reverse = from_action(basis, |ket| ba.apply_connected(ket))?;
                combine(&mut matrix, reverse, false);
                Ok(matrix)
            }
            TreeColorInsertion::StructureConstantTripole { first, second, third } => {
                if first == second || first == third || second == third {
                    return Err(RusticolError::invalid_argument(
                        "a structure-constant tree color tripole requires three distinct colored legs",
                    ));
                }
                // The core validates that every label is an original colored
                // leg and applies mathematical products right-to-left on the
                // ket. Its independently checked physical convention gives
                // [P_ij,P_jk] = -i f_abc T_i^a T_j^b T_k^c.
                let ab = ColorDipoleProduct::new(
                    legs.to_vec(),
                    vec![[*first, *second], [*second, *third]],
                )?;
                let ba = ColorDipoleProduct::new(
                    legs.to_vec(),
                    vec![[*second, *third], [*first, *second]],
                )?;
                let mut matrix = from_action(basis, |ket| ab.apply_connected(ket))?;
                let reverse = from_action(basis, |ket| ba.apply_connected(ket))?;
                combine(&mut matrix, reverse, true);
                for terms in matrix.iter_mut().flatten() {
                    for coefficient in terms.values_mut() {
                        *coefficient =
                            Complex::new(-coefficient.im.clone(), coefficient.re.clone());
                    }
                }
                Ok(matrix)
            }
        })
        .collect()
}

/// Apply the complete action once per ket, then overlap every bra with it.
fn from_action(
    basis: &[ConnectedColorTensor],
    mut action: impl FnMut(&ConnectedColorTensor) -> RusticolResult<ConnectedColorTensor>,
) -> RusticolResult<Vec<Vec<ColorNcTerms>>> {
    let mut matrix = vec![vec![ColorNcTerms::new(); basis.len()]; basis.len()];
    for (column, ket) in basis.iter().enumerate() {
        let image = action(ket)?;
        for (row, bra) in basis.iter().enumerate() {
            matrix[row][column] = bra.overlap_nc_terms(&image)?;
        }
    }
    Ok(matrix)
}

/// Entrywise exact addition/subtraction; both matrices were constructed from
/// the same basis. This is not multiplication of operator overlap matrices.
fn combine(left: &mut [Vec<ColorNcTerms>], right: Vec<Vec<ColorNcTerms>>, subtract: bool) {
    for (left_row, right_row) in left.iter_mut().zip(right) {
        for (left_terms, right_terms) in left_row.iter_mut().zip(right_row) {
            for (power, coefficient) in right_terms {
                let entry = left_terms
                    .entry(power)
                    .or_insert_with(|| Complex::new(Rational::from(0), Rational::from(0)));
                if subtract {
                    entry.re -= coefficient.re;
                    entry.im -= coefficient.im;
                } else {
                    entry.re += coefficient.re;
                    entry.im += coefficient.im;
                }
            }
            left_terms.retain(|_, coefficient| {
                coefficient.re != Rational::from(0) || coefficient.im != Rational::from(0)
            });
        }
    }
}

/// The retained TreeProgram amplitude domain is Nc=3. Keep the conversion
/// exact, including complex phases and negative Laurent powers.
pub(super) fn at_nc3(
    matrix: &[Vec<ColorNcTerms>],
) -> RusticolResult<Vec<Vec<ExactColorCoefficient>>> {
    if matrix.is_empty() || matrix.iter().any(|row| row.len() != matrix.len()) {
        return Err(RusticolError::invalid_argument(
            "a tree color insertion matrix must be nonempty and square",
        ));
    }
    matrix
        .iter()
        .map(|row| {
            row.iter()
                .map(|terms| evaluate_nc_terms(terms, 3))
                .collect()
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use ColorRepresentation::{Antifundamental, Fundamental, Singlet};
    use TreeColorInsertion::{
        Anticommutator, Identity, OrderedProduct, Pair, StructureConstantTripole,
    };
    use rusticol_core::{
        RusticolErrorKind,
        color::{ColorLeg, ColorRepresentation, ColorTensor, OpenColorString, TensorTerm},
    };

    fn value(re: i64, im: i64) -> ExactColorCoefficient {
        Complex::new(Rational::from(re), Rational::from(im))
    }

    fn polynomial(terms: &[(i64, i64, i64, i64)]) -> ColorNcTerms {
        terms
            .iter()
            .map(|&(power, re, im, denominator)| {
                (
                    power,
                    Complex::new(
                        Rational::from((re, denominator)),
                        Rational::from((im, denominator)),
                    ),
                )
            })
            .collect()
    }

    fn tensor(legs: &[ColorLeg], pairs: &[[i64; 2]]) -> ConnectedColorTensor {
        ConnectedColorTensor::new(
            legs.to_vec(),
            vec![TensorTerm {
                coefficient: value(1, 0),
                tensor: ColorTensor::new(
                    pairs
                        .iter()
                        .map(|&[fundamental, antifundamental]| OpenColorString {
                            fundamental,
                            adjoints: vec![],
                            antifundamental,
                        })
                        .collect(),
                    vec![],
                ),
                nc_power: 0,
            }],
            0,
        )
        .unwrap()
    }

    fn singlet(q: i64, qb: i64) -> ConnectedColorTensor {
        tensor(
            &[
                ColorLeg {
                    label: q,
                    representation: Fundamental,
                },
                ColorLeg {
                    label: qb,
                    representation: Antifundamental,
                },
            ],
            &[[q, qb]],
        )
    }

    fn four_quarks() -> Vec<ConnectedColorTensor> {
        let legs = [
            ColorLeg {
                label: 1,
                representation: Fundamental,
            },
            ColorLeg {
                label: 2,
                representation: Antifundamental,
            },
            ColorLeg {
                label: 3,
                representation: Fundamental,
            },
            ColorLeg {
                label: 4,
                representation: Antifundamental,
            },
        ];
        vec![
            tensor(&legs, &[[1, 2], [3, 4]]),
            tensor(&legs, &[[1, 4], [3, 2]]),
        ]
    }

    #[test]
    fn singlet_casimirs_and_request_multiplicity_are_exact() {
        let basis = [singlet(-13, 29)];
        let pair = Pair {
            left: -13,
            right: 29,
        };
        let matrices = prepare_matrices(
            &basis,
            &[
                Identity,
                Pair {
                    left: -13,
                    right: -13,
                },
                pair.clone(),
                pair,
            ],
        )
        .unwrap();
        assert_eq!(matrices[0][0][0], polynomial(&[(1, 1, 0, 1)]));
        // <delta|T_q^2|delta> = Nc*CF = (Nc^2-1)/2.
        assert_eq!(
            matrices[1][0][0],
            polynomial(&[(2, 1, 0, 2), (0, -1, 0, 2)])
        );
        assert_eq!(
            matrices[2][0][0],
            polynomial(&[(2, -1, 0, 2), (0, 1, 0, 2)])
        );
        assert_eq!(matrices[2], matrices[3]);
        assert_eq!(at_nc3(&matrices[1]).unwrap(), vec![vec![value(4, 0)]]);
        assert_eq!(at_nc3(&matrices[2]).unwrap(), vec![vec![value(-4, 0)]]);
    }

    #[test]
    fn four_quark_products_and_tripole_retain_directed_complex_signs() {
        let basis = four_quarks();
        let matrices = prepare_matrices(
            &basis,
            &[
                OrderedProduct(vec![[1, 2], [2, 3]]),
                OrderedProduct(vec![[2, 3], [1, 2]]),
                StructureConstantTripole {
                    first: 1,
                    second: 2,
                    third: 3,
                },
                StructureConstantTripole {
                    first: 2,
                    second: 3,
                    third: 1,
                },
                StructureConstantTripole {
                    first: 2,
                    second: 1,
                    third: 3,
                },
            ],
        )
        .unwrap();
        // Independent direct/crossed delta-basis formulas, with tr(t^a t^b)
        // = delta_ab/2. AB is not BA; the product acts on the ket.
        let ab = vec![
            vec![
                ColorNcTerms::new(),
                polynomial(&[(3, 1, 0, 4), (1, -2, 0, 4), (-1, 1, 0, 4)]),
            ],
            vec![
                polynomial(&[(1, -1, 0, 4), (-1, 1, 0, 4)]),
                ColorNcTerms::new(),
            ],
        ];
        assert_eq!(matrices[0], ab);
        for row in 0..2 {
            for column in 0..2 {
                assert_eq!(matrices[1][row][column], ab[column][row]);
            }
        }
        // F_123 has off-diagonal values +/-i*Nc*(Nc^2-1)/4.
        let tripole = vec![
            vec![
                ColorNcTerms::new(),
                polynomial(&[(3, 0, 1, 4), (1, 0, -1, 4)]),
            ],
            vec![
                polynomial(&[(3, 0, -1, 4), (1, 0, 1, 4)]),
                ColorNcTerms::new(),
            ],
        ];
        assert_eq!(matrices[2], tripole);
        assert_eq!(matrices[3], tripole);
        for row in 0..2 {
            for column in 0..2 {
                let reversed: ColorNcTerms = tripole[row][column]
                    .iter()
                    .map(|(&power, coefficient)| (power, -coefficient.clone()))
                    .collect();
                assert_eq!(matrices[4][row][column], reversed);
            }
        }
        assert_eq!(
            at_nc3(&matrices[2]).unwrap(),
            vec![
                vec![value(0, 0), value(0, 6)],
                vec![value(0, -6), value(0, 0)]
            ],
        );
    }

    #[test]
    fn repeated_factors_and_anticommutators_have_no_implicit_half() {
        let basis = [singlet(1, 2)];
        let matrices = prepare_matrices(
            &basis,
            &[
                OrderedProduct(vec![[1, 2], [1, 2]]),
                Anticommutator {
                    first: [1, 2],
                    second: [1, 2],
                },
                OrderedProduct(vec![[1, 2]; 3]),
            ],
        )
        .unwrap();
        assert_eq!(
            matrices[0][0][0],
            polynomial(&[(3, 1, 0, 4), (1, -2, 0, 4), (-1, 1, 0, 4)])
        );
        assert_eq!(
            matrices[1][0][0],
            polynomial(&[(3, 1, 0, 2), (1, -2, 0, 2), (-1, 1, 0, 2)])
        );
        assert_eq!(
            matrices[2][0][0],
            polynomial(&[(4, -1, 0, 8), (2, 3, 0, 8), (0, -3, 0, 8), (-2, 1, 0, 8)])
        );

        let matrices = prepare_matrices(
            &four_quarks(),
            &[Anticommutator {
                first: [1, 2],
                second: [2, 3],
            }],
        )
        .unwrap();
        let off_diagonal = polynomial(&[(3, 1, 0, 4), (1, -3, 0, 4), (-1, 2, 0, 4)]);
        assert_eq!(
            matrices[0],
            vec![
                vec![ColorNcTerms::new(), off_diagonal.clone()],
                vec![off_diagonal, ColorNcTerms::new()],
            ]
        );
    }

    #[test]
    fn redundant_complex_basis_keeps_phases_and_exact_normalizations() {
        let original = four_quarks();
        let mut terms = vec![];
        for (source, coefficient) in original.iter().zip([value(2, 1), value(-1, 2)]) {
            let mut term = source.terms()[0].clone();
            term.coefficient = coefficient;
            term.nc_power = -1;
            terms.push(term);
        }
        // The third vector equals [(2+i) C0+(-1+2i) C1]/(2 Nc).
        // This basis is rank deficient, with nontrivial complex overlaps.
        let redundant = ConnectedColorTensor::new(original[0].legs().to_vec(), terms, 2).unwrap();
        let mut basis = original.clone();
        basis.push(redundant);
        let requests = [
            Identity,
            Pair { left: 1, right: 3 },
            OrderedProduct(vec![[1, 2], [2, 3]]),
            StructureConstantTripole {
                first: 1,
                second: 2,
                third: 3,
            },
        ];
        let base = prepare_matrices(&original, &requests).unwrap();
        let actual = prepare_matrices(&basis, &requests).unwrap();
        for nc in [2, 3, 5] {
            let denominator = Rational::from(2 * i64::from(nc));
            let weights = [
                [
                    value(1, 0),
                    value(0, 0),
                    Complex::new(
                        Rational::from(2) / &denominator,
                        Rational::from(1) / &denominator,
                    ),
                ],
                [
                    value(0, 0),
                    value(1, 0),
                    Complex::new(
                        Rational::from(-1) / &denominator,
                        Rational::from(2) / &denominator,
                    ),
                ],
            ];
            for (small, large) in base.iter().zip(&actual) {
                for row in 0..3 {
                    for column in 0..3 {
                        let mut expected = value(0, 0);
                        for a in 0..2 {
                            for b in 0..2 {
                                expected += weights[a][row].conj()
                                    * evaluate_nc_terms(&small[a][b], nc).unwrap()
                                    * &weights[b][column];
                            }
                        }
                        assert_eq!(
                            evaluate_nc_terms(&large[row][column], nc).unwrap(),
                            expected
                        );
                    }
                }
            }
        }
        assert_ne!(at_nc3(&actual[0]).unwrap()[0][2].im, Rational::from(0));
    }

    #[test]
    fn zero_overlap_does_not_remove_a_nonzero_insertion() {
        let basis = four_quarks();
        // C1-C0/Nc is orthogonal to C0, while T1.T3 couples them.
        let mut terms = basis[1].terms().to_vec();
        let mut subtraction = basis[0].terms()[0].clone();
        subtraction.coefficient = value(-1, 0);
        subtraction.nc_power = -1;
        terms.push(subtraction);
        let orthogonal = ConnectedColorTensor::new(basis[0].legs().to_vec(), terms, 0).unwrap();
        let matrices = prepare_matrices(
            &[basis[0].clone(), orthogonal],
            &[Identity, Pair { left: 1, right: 3 }],
        )
        .unwrap();
        assert!(matrices[0][0][1].is_empty());
        assert!(matrices[0][1][0].is_empty());
        let off_diagonal = polynomial(&[(2, 1, 0, 2), (0, -1, 0, 2)]);
        assert_eq!(matrices[1][0][1], off_diagonal);
        assert_eq!(matrices[1][1][0], off_diagonal);
    }

    #[test]
    fn malformed_basis_and_unsupported_insertions_fail_explicitly() {
        let basis = [singlet(1, 2)];
        for requests in [
            vec![],
            vec![OrderedProduct(vec![])],
            vec![Pair { left: 1, right: 9 }],
            vec![StructureConstantTripole {
                first: 1,
                second: 1,
                third: 2,
            }],
            vec![StructureConstantTripole {
                first: 1,
                second: 2,
                third: 9,
            }],
        ] {
            assert_eq!(
                prepare_matrices(&basis, &requests).unwrap_err().kind(),
                RusticolErrorKind::InvalidArgument
            );
        }
        assert!(prepare_matrices(&[], &[Identity]).is_err());
        assert!(prepare_matrices(&[basis[0].clone(), singlet(3, 4)], &[Identity]).is_err());
        let mut legs = basis[0].legs().to_vec();
        legs.push(ColorLeg {
            label: 3,
            representation: Singlet,
        });
        let with_singlet = ConnectedColorTensor::new(legs, basis[0].terms().to_vec(), 0).unwrap();
        assert!(prepare_matrices(&[with_singlet.clone()], &[Pair { left: 1, right: 3 }]).is_err());
        assert!(
            prepare_matrices(
                &[with_singlet],
                &[StructureConstantTripole {
                    first: 1,
                    second: 2,
                    third: 3
                }]
            )
            .is_err()
        );
        let odd = ConnectedColorTensor::new(basis[0].legs().to_vec(), basis[0].terms().to_vec(), 1)
            .unwrap();
        assert!(prepare_matrices(&[basis[0].clone(), odd], &[Identity]).is_err());
        assert!(at_nc3(&[]).is_err());
        assert!(at_nc3(&[vec![]]).is_err());
    }
}
