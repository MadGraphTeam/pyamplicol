// SPDX-License-Identifier: 0BSD

//! Native preparation primitives for the shared numerical runtime.
//!
//! Exact Symbolica evaluators can be constructed in Rust and passed to
//! [`crate::loop_runtime::LoadedLoopRuntime::from_evaluators`]. This uses the
//! same execution plans and precision-generic backend as saved artifacts, without
//! a Python producer, temporary artifact, or process-specific source compilation.
//! These primitives do not generate a physical process or infer its UV/R2 rules.

use crate::{RusticolError, RusticolResult};
use symbolica::domains::float::Complex;
use symbolica::domains::rational::Rational;
use symbolica::evaluate::{ExpressionEvaluator, JITCompilationSettings, JITCompiledEvaluator};

/// Instructions with exact complex rational constants, before choosing arithmetic.
pub type ExactEvaluator = ExpressionEvaluator<Complex<Rational>>;

/// Encode native instructions in the existing Symbolica evaluator-state format.
///
/// The payload contains exact coefficients and no compiled machine code. It is
/// accepted by the existing numerical backends in binary64, double-double and
/// arbitrary precision. External scalar functions must be registered before
/// decoding, just as for any other saved Symbolica evaluator.
pub fn encode_exact_evaluator_state(evaluator: &ExactEvaluator) -> RusticolResult<Vec<u8>> {
    bincode::encode_to_vec(
        &(
            false,
            JITCompilationSettings::default(),
            evaluator,
            None::<JITCompiledEvaluator<f64>>,
            None::<JITCompiledEvaluator<Complex<f64>>>,
        ),
        bincode::config::standard(),
    )
    .map_err(|error| RusticolError::serialization(error.to_string()))
}

/// Decode exact instructions through the production evaluator-state decoder.
///
/// This also rejects trailing bytes and registers the runtime's scalar primitives.
pub fn decode_exact_evaluator_state(bytes: &[u8]) -> RusticolResult<ExactEvaluator> {
    crate::engine::decode_exact_evaluator_state(bytes)
}
