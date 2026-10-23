// SPDX-License-Identifier: 0BSD

use std::sync::Arc;

use rusticol_core::{
    RusticolError, RusticolResult, color::ExactColorCoefficient,
    preparation::encode_exact_evaluator_state,
};
use symbolica::{
    atom::{Atom, AtomCore},
    symbol,
};

use super::{TreeColorInsertion, TreeColorProgram};
use crate::{
    Complex,
    runtime::{Arithmetic, Batch, BatchCarrier, CoefficientEvaluator, Data},
    tree_norm::hermitian_norm,
    tree_preparation::{TreeEvaluator, TreeProgram},
};

fn invalid(message: impl Into<String>) -> RusticolError {
    RusticolError::invalid_argument(message)
}

fn coordinate_symbols(prefix: &str, count: usize) -> Vec<Atom> {
    (0..count)
        .flat_map(|i| {
            ["real", "imag"]
                .map(move |part| Atom::var(symbol!(&format!("{prefix}_{part}_{i}"); Real)))
        })
        .collect()
}

/// Exact Cartesian expansion of conj(B) K A, including complex off-diagonals.
fn directed(matrix: &[Vec<ExactColorCoefficient>], bra: &[Atom], ket: &[Atom]) -> (Atom, Atom) {
    let (mut real, mut imag) = (Atom::Zero, Atom::Zero);
    for (b, row) in matrix.iter().enumerate() {
        let (x, y) = (&bra[2 * b], &bra[2 * b + 1]);
        for (c, k) in row.iter().enumerate() {
            let (u, v) = (&ket[2 * c], &ket[2 * c + 1]);
            let p = x * u + y * v;
            let q = x * v - y * u;
            real += Atom::num(k.re.clone()) * &p - Atom::num(k.im.clone()) * &q;
            imag += Atom::num(k.im.clone()) * p + Atom::num(k.re.clone()) * q;
        }
    }
    (real, imag)
}

pub(super) fn compile_states(
    matrices: &[Vec<Vec<ExactColorCoefficient>>],
) -> RusticolResult<(Vec<u8>, Vec<u8>)> {
    let n = matrices
        .first()
        .map(Vec::len)
        .filter(|&n| n > 0)
        .ok_or_else(|| invalid("color contraction requires nonempty matrices"))?;
    n.checked_mul(4)
        .ok_or_else(|| invalid("color Cartesian dimensions overflow"))?;
    matrices
        .len()
        .checked_mul(2)
        .ok_or_else(|| invalid("color output dimensions overflow"))?;
    if matrices
        .iter()
        .any(|m| m.len() != n || m.iter().any(|r| r.len() != n))
    {
        return Err(invalid(
            "color insertion matrices must have one common square dimension",
        ));
    }
    let same = coordinate_symbols("rusticol_native_tree::amplitude", n);
    let bra = coordinate_symbols("rusticol_native_color::bra", n);
    let ket = coordinate_symbols("rusticol_native_color::ket", n);
    let (mut self_outputs, mut directed_outputs) = (Vec::new(), Vec::new());
    for matrix in matrices {
        let is_hermitian = (0..n).all(|b| (0..n).all(|c| matrix[b][c] == matrix[c][b].conj()));
        let (real, imag) = if is_hermitian {
            // Establish reality algebraically before creating instructions.
            // The same kernel is used by the ordinary prepared tree norm.
            let (value, inputs) = hermitian_norm(matrix)?;
            debug_assert_eq!(inputs, same);
            (value, Atom::Zero)
        } else {
            directed(matrix, &same, &same)
        };
        self_outputs.extend([real, imag]);
        let (real, imag) = directed(matrix, &bra, &ket);
        directed_outputs.extend([real, imag]);
    }
    let encode = |outputs: &[Atom], inputs: &[Atom]| {
        let evaluator = Atom::evaluator_multiple(outputs, inputs)
            .cores(1)
            .build()
            .map_err(|e| {
                RusticolError::evaluation(format!("native color bilinear preparation: {e}"))
            })?;
        encode_exact_evaluator_state(&evaluator)
    };
    Ok((
        encode(&self_outputs, &same)?,
        encode(&directed_outputs, &[bra, ket].concat())?,
    ))
}

fn cartesian_values<T: BatchCarrier>(
    values: &[Complex<T>],
    batch: &Batch,
) -> RusticolResult<Batch> {
    let values = values
        .iter()
        .flat_map(|z| {
            [
                Complex::new(z.re.clone(), z.re.zero()),
                Complex::new(z.im.clone(), z.im.zero()),
            ]
        })
        .collect();
    let columns = batch
        .columns()
        .checked_mul(2)
        .ok_or_else(|| invalid("Cartesian dimensions overflow"))?;
    Batch::typed(
        values,
        batch.ids().to_vec(),
        columns,
        batch.precision_bits(),
    )
    .map_err(Into::into)
}

fn cartesian(batch: &Batch) -> RusticolResult<Batch> {
    match batch.data() {
        Data::Double(v) => cartesian_values(v, batch),
        Data::DoubleDouble(v) => cartesian_values(v, batch),
        Data::Arbitrary(v) => cartesian_values(v, batch),
    }
}

fn pack_values<T: BatchCarrier>(
    values: &[Complex<T>],
    batch: &Batch,
    requests: usize,
) -> RusticolResult<Batch> {
    let mut output = Vec::with_capacity(values.len() / 2);
    for (index, parts) in values.chunks_exact(2).enumerate() {
        let id = batch.ids()[index / requests];
        let request = index % requests;
        if parts.iter().any(|z| !z.re.is_finite() || !z.im.is_finite()) {
            return Err(RusticolError::nonfinite_result(format!(
                "native color bilinear produced a nonfinite value in row {id}, request {request}"
            )));
        }
        if parts.iter().any(|z| !z.im.is_fully_zero()) {
            return Err(RusticolError::integrity(format!(
                "Cartesian color expression is not real in row {id}, request {request}"
            )));
        }
        // These are separate exact real expressions, not a projection of the
        // complex contraction. Preserve each Float and its tracked precision.
        output.push(Complex::new(parts[0].re.clone(), parts[1].re.clone()));
    }
    Batch::typed(
        output,
        batch.ids().to_vec(),
        requests,
        batch.precision_bits(),
    )
    .map_err(Into::into)
}

fn pack(batch: Batch, requests: usize) -> RusticolResult<Batch> {
    if requests.checked_mul(2) != Some(batch.columns()) {
        return Err(RusticolError::integrity(
            "native color Cartesian output shape changed",
        ));
    }
    match batch.data() {
        Data::Double(v) => pack_values(v, &batch, requests),
        Data::DoubleDouble(v) => pack_values(v, &batch, requests),
        Data::Arbitrary(v) => pack_values(v, &batch, requests),
    }
}

fn add_values<T: BatchCarrier>(
    a: &[Complex<T>],
    b: &[Complex<T>],
    batch: &Batch,
) -> RusticolResult<Batch> {
    let values = a
        .iter()
        .zip(b)
        .enumerate()
        .map(|(i, (a, b))| {
            let value = a + b;
            if !value.re.is_finite() || !value.im.is_finite() {
                Err(RusticolError::nonfinite_result(format!(
                    "native color helicity sum is nonfinite in row {}, request {}",
                    batch.ids()[i / batch.columns()],
                    i % batch.columns()
                )))
            } else {
                Ok(value)
            }
        })
        .collect::<RusticolResult<Vec<_>>>()?;
    Batch::typed(
        values,
        batch.ids().to_vec(),
        batch.columns(),
        batch.precision_bits(),
    )
    .map_err(Into::into)
}

fn add(a: &Batch, b: &Batch) -> RusticolResult<Batch> {
    a.same_rows(b)?;
    if a.columns() != b.columns() {
        return Err(RusticolError::integrity("color sum columns changed"));
    }
    match (a.data(), b.data()) {
        (Data::Double(a_values), Data::Double(b_values)) => add_values(a_values, b_values, a),
        (Data::DoubleDouble(a_values), Data::DoubleDouble(b_values)) => {
            add_values(a_values, b_values, a)
        }
        (Data::Arbitrary(a_values), Data::Arbitrary(b_values)) => add_values(a_values, b_values, a),
        _ => unreachable!("same_rows checked the carrier"),
    }
}

/// Evaluates color insertions with the same owned tree and numerical carrier.
/// Each output row has one complex column per requested insertion, in order.
pub struct TreeColorEvaluator {
    program: Arc<TreeProgram>,
    requests: Vec<TreeColorInsertion>,
    tree: TreeEvaluator,
    same: CoefficientEvaluator,
    directed: CoefficientEvaluator,
}

impl TreeColorEvaluator {
    pub(super) fn new(
        program: &TreeColorProgram,
        arithmetic: Arithmetic,
        bits: u32,
    ) -> RusticolResult<Self> {
        let tree = program
            .tree
            .evaluator_with_precision_bits(arithmetic, bits)?;
        if tree.coefficient_count() != program.basis_len() {
            return Err(RusticolError::integrity(
                "tree coefficient and color basis dimensions differ",
            ));
        }
        Ok(Self {
            program: Arc::clone(&program.tree),
            requests: program.requests.clone(),
            tree,
            same: CoefficientEvaluator::with_precision_bits(&program.self_state, arithmetic, bits)?,
            directed: CoefficientEvaluator::with_precision_bits(
                &program.directed_state,
                arithmetic,
                bits,
            )?,
        })
    }

    pub fn tree(&self) -> &TreeProgram {
        &self.program
    }
    pub fn requests(&self) -> &[TreeColorInsertion] {
        &self.requests
    }
    pub fn precision_bits(&self) -> u32 {
        self.same.precision_bits()
    }

    fn self_contract(&mut self, coefficients: &Batch) -> RusticolResult<Batch> {
        let inputs = cartesian(coefficients)?;
        let output = self.same.evaluate_batch(&inputs)?;
        pack(output, self.requests.len())
    }

    /// One physical helicity assignment, with the same amplitude on both sides.
    pub fn evaluate_fixed_helicities(
        &mut self,
        momenta: &Batch,
        helicities: &[i32],
    ) -> RusticolResult<Batch> {
        self.fixed(momenta, None, helicities)
    }
    pub fn evaluate_fixed_helicities_with_parameters(
        &mut self,
        momenta: &Batch,
        parameters: &Batch,
        helicities: &[i32],
    ) -> RusticolResult<Batch> {
        self.fixed(momenta, Some(parameters), helicities)
    }
    fn fixed(
        &mut self,
        momenta: &Batch,
        parameters: Option<&Batch>,
        helicities: &[i32],
    ) -> RusticolResult<Batch> {
        let coefficients = match parameters {
            Some(p) => self
                .tree
                .evaluate_coefficients_with_parameters(momenta, p, helicities)?,
            None => self.tree.evaluate_coefficients(momenta, helicities)?,
        };
        self.self_contract(&coefficients)
    }

    /// Directed `<bra|O|ket>` for independent supplied external component blocks.
    /// Each block uses the prepared tree's four-component/adjoint convention.
    /// Even for Hermitian O, the directed result is kept complex.
    pub fn evaluate_external_components(
        &mut self,
        momenta: &Batch,
        bra: &[&Batch],
        ket: &[&Batch],
    ) -> RusticolResult<Batch> {
        self.components(momenta, None, bra, ket)
    }
    pub fn evaluate_external_components_with_parameters(
        &mut self,
        momenta: &Batch,
        parameters: &Batch,
        bra: &[&Batch],
        ket: &[&Batch],
    ) -> RusticolResult<Batch> {
        self.components(momenta, Some(parameters), bra, ket)
    }
    fn components(
        &mut self,
        momenta: &Batch,
        parameters: Option<&Batch>,
        bra: &[&Batch],
        ket: &[&Batch],
    ) -> RusticolResult<Batch> {
        let mut evaluate = |states: &[&Batch]| match parameters {
            Some(p) => self
                .tree
                .evaluate_external_components_with_parameters(momenta, p, states),
            None => self.tree.evaluate_external_components(momenta, states),
        };
        let bra = evaluate(bra)?;
        let ket = evaluate(ket)?;
        bra.same_rows(&ket)?;
        let inputs = Batch::concat_columns(&[&cartesian(&bra)?, &cartesian(&ket)?])?;
        let output = self.directed.evaluate_batch(&inputs)?;
        pack(output, self.requests.len())
    }

    /// Stream the full declared physical helicity product, without averages.
    pub fn evaluate_batch(&mut self, momenta: &Batch) -> RusticolResult<Batch> {
        self.sum(momenta, None)
    }
    pub fn evaluate_batch_with_parameters(
        &mut self,
        momenta: &Batch,
        parameters: &Batch,
    ) -> RusticolResult<Batch> {
        self.sum(momenta, Some(parameters))
    }
    fn sum(&mut self, momenta: &Batch, parameters: Option<&Batch>) -> RusticolResult<Batch> {
        let helicities: Vec<_> = self
            .tree
            .states()
            .iter()
            .map(|s| s.helicities.clone())
            .collect();
        let mut positions = vec![0; helicities.len()];
        let mut accumulated: Option<Batch> = None;
        loop {
            let assignment: Vec<_> = helicities
                .iter()
                .zip(&positions)
                .map(|(h, &p)| h[p])
                .collect();
            let value = self.fixed(momenta, parameters, &assignment)?;
            // Validate all tree metadata even for zero rows, then return a
            // correctly shaped typed empty result without enumerating spins.
            if momenta.rows() == 0 {
                return Ok(value);
            }
            accumulated = Some(match accumulated {
                None => value,
                Some(a) => add(&a, &value)?,
            });
            let mut p = positions.len();
            while p > 0 {
                p -= 1;
                positions[p] += 1;
                if positions[p] < helicities[p].len() {
                    break;
                }
                positions[p] = 0;
            }
            if p == 0 && positions.first().is_none_or(|&x| x == 0) {
                return Ok(accumulated.expect("one assignment in every declared helicity product"));
            }
        }
    }
}
