// SPDX-License-Identifier: 0BSD

use super::*;
use symbolica::{
    atom::{Atom, AtomCore, AtomView},
    coefficient::Coefficient,
};

fn function(atom: AtomView<'_>) -> RusticolResult<(String, Vec<AtomView<'_>>)> {
    let AtomView::Fun(function) = atom else {
        return Err(invalid("expected a Spenso color function"));
    };
    Ok((
        function
            .get_symbol()
            .get_name()
            .rsplit("::")
            .next()
            .unwrap_or("")
            .to_owned(),
        function.iter().collect(),
    ))
}

#[derive(Clone, Copy, Eq, PartialEq)]
enum Slot {
    Adjoint,
    Upper,
    Lower,
}

fn slot(atom: AtomView<'_>) -> RusticolResult<(Slot, String)> {
    let (head, args) = function(atom)?;
    if head == "dind" && args.len() == 1 {
        let (kind, name) = slot(args[0])?;
        if kind != Slot::Upper {
            return Err(invalid("unsupported dual color slot"));
        }
        return Ok((Slot::Lower, name));
    }
    let kind = match head.as_str() {
        "coad" => Slot::Adjoint,
        "cof" => Slot::Upper,
        _ => return Err(invalid("unsupported color slot representation")),
    };
    if args.len() != 2 || args[0] != Atom::num(if kind == Slot::Adjoint { 8 } else { 3 }) {
        return Err(invalid(
            "color slot must have the SU(3) dimension and one label",
        ));
    }
    let name = if let AtomView::Var(var) = args[1] {
        var.get_symbol().get_name().to_owned()
    } else {
        args[1].to_canonical_string()
    };
    Ok((kind, name))
}

fn adjoint(atom: AtomView<'_>) -> RusticolResult<String> {
    let (kind, name) = slot(atom)?;
    if kind != Slot::Adjoint {
        return Err(invalid("expected an adjoint color slot"));
    }
    Ok(name)
}

fn ends(upper: AtomView<'_>, lower: AtomView<'_>) -> RusticolResult<(String, String)> {
    let (first, row) = slot(upper)?;
    let (second, col) = slot(lower)?;
    if first != Slot::Upper || second != Slot::Lower {
        return Err(invalid("expected upper and lower fundamental color slots"));
    }
    Ok((row, col))
}

fn matrix_adjoint(atom: AtomView<'_>) -> RusticolResult<String> {
    let (head, args) = function(atom)?;
    if head != "t" || args.len() != 3 {
        return Err(invalid("unsupported color chain or trace matrix"));
    }
    // Chain/trace matrix endpoints are formal placeholders; the enclosing
    // object supplies their contractions, as in the existing Python lowering.
    adjoint(args[0])
}

fn factor(atom: AtomView<'_>) -> RusticolResult<ColorNetwork<String>> {
    if let AtomView::Num(number) = atom {
        let Coefficient::Complex(coefficient) = number.get_coeff_view().to_owned() else {
            return Err(invalid(
                "color coefficients must have exact rational real and imaginary parts",
            ));
        };
        return Ok(vec![ColorProduct {
            coefficient,
            ..Default::default()
        }]);
    }
    let (head, args) = function(atom)?;
    match head.as_str() {
        "f" if args.len() == 3 => {
            let (a, b, c) = (adjoint(args[0])?, adjoint(args[1])?, adjoint(args[2])?);
            // f^abc = -i/sqrt(2) (tr(tau^a tau^b tau^c)-tr(tau^a tau^c tau^b)).
            Ok(vec![
                ColorProduct {
                    coefficient: Complex::new(Rational::from(0), Rational::from(-1)),
                    traces: vec![vec![a.clone(), b.clone(), c.clone()]],
                    root2_power: 1,
                    ..Default::default()
                },
                ColorProduct {
                    coefficient: Complex::new(Rational::from(0), Rational::from(1)),
                    traces: vec![vec![a, c, b]],
                    root2_power: 1,
                    ..Default::default()
                },
            ])
        }
        "t" if args.len() == 3 => {
            let a = adjoint(args[0])?;
            let (row, col) = ends(args[1], args[2])?;
            Ok(vec![ColorProduct {
                strings: vec![ColorString {
                    row,
                    word: vec![a],
                    col,
                }],
                root2_power: 1,
                ..Default::default()
            }])
        }
        "chain" if args.len() >= 2 => {
            let (row, col) = ends(args[0], args[1])?;
            let word = args[2..]
                .iter()
                .map(|&arg| matrix_adjoint(arg))
                .collect::<RusticolResult<Vec<_>>>()?;
            let root2_power =
                i64::try_from(word.len()).map_err(|_| invalid("color chain length overflows"))?;
            Ok(vec![ColorProduct {
                strings: vec![ColorString { row, word, col }],
                root2_power,
                ..Default::default()
            }])
        }
        "trace" if args.len() == 2 => {
            let (representation, dimensions) = function(args[0])?;
            let (cyclic, matrices) = function(args[1])?;
            if representation != "cof"
                || dimensions != [Atom::num(3).as_view()]
                || cyclic != "cyclic"
            {
                return Err(invalid(
                    "unsupported color trace representation or cyclic container",
                ));
            }
            let word = matrices
                .into_iter()
                .map(matrix_adjoint)
                .collect::<RusticolResult<Vec<_>>>()?;
            let root2_power =
                i64::try_from(word.len()).map_err(|_| invalid("color trace length overflows"))?;
            Ok(vec![ColorProduct {
                traces: vec![word],
                root2_power,
                ..Default::default()
            }])
        }
        "g" | "id" if args.len() == 2 => {
            let (left_kind, left) = slot(args[0])?;
            let (right_kind, right) = slot(args[1])?;
            if left_kind == Slot::Adjoint && right_kind == Slot::Adjoint {
                Ok(vec![ColorProduct {
                    traces: vec![vec![left, right]],
                    ..Default::default()
                }])
            } else {
                let (row, col) = match (left_kind, right_kind) {
                    (Slot::Upper, Slot::Lower) => (left, right),
                    (Slot::Lower, Slot::Upper) => (right, left),
                    _ => return Err(invalid("unsupported color metric slots")),
                };
                Ok(vec![ColorProduct {
                    strings: vec![ColorString {
                        row,
                        word: vec![],
                        col,
                    }],
                    ..Default::default()
                }])
            }
        }
        _ => Err(invalid(
            "color expression does not lower to supported SU(3) strings and traces",
        )),
    }
}

/// Lower an exact Spenso SU(3) expression to tau strings and traces.
/// Supports sums/products of numbers, `f`, `t`, `chain`, `trace`, and `g`/`id`.
/// Namespace-qualified function names are accepted; slot labels preserve their
/// namespaces. Unsupported representations and symbolic coefficients fail
/// explicitly. This consumes model color expressions after Spenso translation.
pub fn spenso_color_network(expression: &Atom) -> RusticolResult<ColorNetwork<String>> {
    let expanded = expression.expand();
    let summands = if let AtomView::Add(sum) = expanded.as_view() {
        sum.iter().collect()
    } else {
        vec![expanded.as_view()]
    };
    let mut result = Vec::new();
    for summand in summands {
        let factors = if let AtomView::Mul(product) = summand {
            product.iter().collect()
        } else {
            vec![summand]
        };
        let mut terms = vec![ColorProduct::default()];
        for atom in factors {
            terms = multiply(&terms, &factor(atom)?)?;
        }
        result.extend(terms);
    }
    Ok(result)
}
