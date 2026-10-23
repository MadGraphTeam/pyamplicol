// SPDX-License-Identifier: 0BSD

//! Exact bit requests use the existing coefficient executor and native state.

use rusticol_core::preparation::encode_exact_evaluator_state;
use rusticol_loop_reduction::runtime::{Arithmetic, Batch, CoefficientEvaluator, Data};
use symbolica::{
    atom::{Atom, AtomCore},
    domains::float::{Complex, DoubleFloat, Float, FloatLike},
    parse,
};

fn native_state() -> Vec<u8> {
    let input = parse!("native_bit_precision::x");
    let delta = parse!("1/1208925819614629174706176"); // 2^-80, exact.
    let expression = &input + (Atom::one() + delta) * (Atom::one() + Atom::i());
    let evaluator = Atom::evaluator_multiple(&[expression], &[input])
        .cores(1)
        .build()
        .unwrap();
    encode_exact_evaluator_state(&evaluator).unwrap()
}

#[test]
fn exact_bit_requests_preserve_nonstandard_float_precision_and_constants() {
    let state = native_state();
    for bits in [113, 137, 257] {
        let mut evaluator =
            CoefficientEvaluator::with_precision_bits(&state, Arithmetic::Arbitrary, bits).unwrap();
        assert_eq!(evaluator.precision_bits(), bits);
        // Symbolica has separate scalar and multirow execution paths.
        for rows in [1, 2] {
            let input = Batch::typed(
                (1..=rows)
                    .map(|value| {
                        let value = Float::with_val(bits, value);
                        Complex::new(value.clone(), value)
                    })
                    .collect(),
                (41..41 + rows as u64).collect(),
                1,
                bits,
            )
            .unwrap();
            let result = evaluator.evaluate_batch(&input).unwrap();
            assert_eq!(result.precision_bits(), bits);
            assert_eq!(result.ids(), input.ids());
            let Data::Arbitrary(values) = result.data() else {
                panic!("carrier changed")
            };
            for (index, value) in values.iter().enumerate() {
                let original = Float::with_val(bits, index + 1);
                // The saved coefficient 1+2^-80 cannot survive binary64
                // narrowing. Only this isolated binary power is exactly f64.
                let integer_part = original + Float::with_val(bits, 1);
                let expected = integer_part.clone() + Float::with_val(bits, 2.0_f64.powi(-80));
                assert!(expected > integer_part);
                assert_eq!(value.re.get_precision(), bits);
                assert_eq!(value.im.get_precision(), bits);
                assert_eq!(value.re, expected);
                assert_eq!(value.im, expected);
            }
        }
    }
}

#[test]
fn bit_constructor_keeps_fixed_carriers_and_legacy_precision_selection() {
    let state = native_state();
    let double = Batch::typed(vec![Complex::new(1_f64, 1_f64)], vec![4], 1, 53).unwrap();
    let double_double = Batch::typed(
        vec![Complex::new(DoubleFloat::from(1.), DoubleFloat::from(1.))],
        vec![4],
        1,
        106,
    )
    .unwrap();
    for (mode, name, bits, input) in [
        (Arithmetic::Double, "double", 53, double),
        (
            Arithmetic::DoubleDouble,
            "double-double",
            106,
            double_double,
        ),
    ] {
        let mut typed = CoefficientEvaluator::with_precision_bits(&state, mode, bits).unwrap();
        let mut legacy = CoefficientEvaluator::new(&state, name, None).unwrap();
        assert_eq!(typed.precision_bits(), bits);
        assert_eq!(legacy.precision_bits(), bits);
        assert_eq!(
            typed.evaluate_batch(&input).unwrap().to_decimal(),
            legacy.evaluate_batch(&input).unwrap().to_decimal(),
        );
    }
    let legacy = CoefficientEvaluator::new(&state, "arbitrary", Some(40)).unwrap();
    assert_eq!(
        legacy.precision_bits(),
        Float::decimal_digits_to_bits(40.).unwrap()
    );
    assert!(CoefficientEvaluator::with_precision_bits(&state, Arithmetic::Arbitrary, 2).is_ok());
}

#[test]
fn bit_constructor_rejects_incompatible_or_invalid_precision() {
    let state = native_state();
    for (mode, bits) in [
        (Arithmetic::Double, 0),
        (Arithmetic::Double, 52),
        (Arithmetic::Double, 54),
        (Arithmetic::DoubleDouble, 53),
        (Arithmetic::DoubleDouble, 105),
        (Arithmetic::DoubleDouble, 107),
        (Arithmetic::DoubleDouble, 113),
        (Arithmetic::Arbitrary, 0),
        (Arithmetic::Arbitrary, 1),
    ] {
        assert!(CoefficientEvaluator::with_precision_bits(&state, mode, bits).is_err());
    }
}
