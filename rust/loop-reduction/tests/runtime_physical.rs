// SPDX-License-Identifier: 0BSD
//! Explicit generated-fixture integration: the complete coordinator has no
//! Python dependency, including during execution or precision rebinding.
use rusticol_core::loop_execution::{LoopExecutor, LoopInputs};
use rusticol_core::loop_runtime::{LoadedLoopRuntime, ModelBinding, load_loop_runtime_pacbin};
use rusticol_core::preparation::decode_exact_evaluator_state;
use rusticol_loop_reduction::runtime::physical::PhysicalBackend;
use std::sync::Arc;

#[test]
#[ignore = "requires PYAMPLICOL_NATIVE_UUDD_PACBIN from the portable fixture"]
fn standalone_complete_uudd_three_carriers() {
    let loaded = Arc::new(
        load_loop_runtime_pacbin(
            std::env::var("PYAMPLICOL_NATIVE_UUDD_PACBIN").expect("generated uudd PACBIN"),
        )
        .unwrap(),
    );
    // This fixture supplies physical instructions; the second construction
    // exercises the native producer boundary without writing an artifact.
    let native = Arc::new(
        LoadedLoopRuntime::from_evaluators(
            loaded.plan().clone(),
            loaded
                .evaluator_states()
                .map(|(name, bytes)| {
                    (
                        name.to_owned(),
                        decode_exact_evaluator_state(bytes).unwrap(),
                    )
                })
                .collect(),
        )
        .unwrap(),
    );
    assert_eq!(
        native.metadata_json().unwrap(),
        loaded.metadata_json().unwrap()
    );
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("../../../tools/loop_reference/uudd_qcd.json")).unwrap();
    let momenta = fixture["points"][0]
        .as_array()
        .unwrap()
        .iter()
        .flat_map(|leg| {
            leg.as_array()
                .unwrap()
                .iter()
                .map(|x| x.as_i64().unwrap().to_string())
        })
        .collect::<Vec<_>>();
    eprintln!(
        "native workspace bytes: reducer={}, scalar={}, schedule={}",
        std::mem::size_of::<rusticol_loop_reduction::runtime::PolynomialPlan>(),
        std::mem::size_of::<rusticol_loop_reduction::runtime::CoefficientEvaluator>(),
        std::mem::size_of::<rusticol_loop_reduction::runtime::CoefficientPlan>()
    );
    let mut reference: Option<Vec<f64>> = None;
    for (arithmetic, precision, engine) in [
        ("double", None, "fast"),
        ("double-double", None, "generic"),
        ("arbitrary", Some(70), "generic"),
    ] {
        let mut saved_values = None;
        for runtime in [&loaded, &native] {
            let backend =
                PhysicalBackend::new(arithmetic, precision, "interpreted", engine).unwrap();
            eprintln!("binding {arithmetic}");
            let mut program = LoopExecutor::new(runtime.clone(), backend).unwrap();
            eprintln!("evaluating {arithmetic}");
            let output = program
                .evaluate(LoopInputs {
                    spin_sources: Default::default(),
                    momenta: momenta.clone(),
                    scales_squared: vec!["1000000".into()],
                    model_values: match runtime.plan().model_binding {
                        ModelBinding::Legacy => vec!["0.118".into(), "173".into()],
                        ModelBinding::Source { .. } => vec![],
                    },
                    point_ids: vec![73],
                })
                .unwrap();
            assert_eq!(output.r2_strategy, "model");
            assert_eq!(output.point_ids, [73]);
            assert_eq!(output.born.ids(), [0]);
            assert!(
                output.statuses[0]
                    .iter()
                    .all(|(id, status)| *id == 0 && status == "success")
            );
            // A source model can retain zero or interference-only order
            // columns; positivity applies to their physical Born sum.
            assert!(
                output
                    .born
                    .to_decimal()
                    .iter()
                    .map(|value| value[0].parse::<f64>().unwrap())
                    .sum::<f64>()
                    > 0.
            );
            let mut all = vec![output.born];
            all.extend(output.components);
            all.push(output.totals);
            let decimals = all
                .iter()
                .flat_map(|batch| batch.to_decimal())
                .collect::<Vec<_>>();
            if let Some(saved) = &saved_values {
                assert_eq!(&decimals, saved, "native preparation changed {arithmetic}");
            } else {
                saved_values = Some(decimals.clone());
            }
            let numbers = decimals
                .into_iter()
                .flat_map(|value| value.map(|x| x.parse::<f64>().unwrap()))
                .collect::<Vec<_>>();
            assert!(numbers.iter().all(|x| x.is_finite()));
            if let Some(old) = &reference {
                for (a, b) in numbers.iter().zip(old) {
                    assert!((a - b).abs() < 1e-11 * (1. + a.abs()));
                }
            } else {
                reference = Some(numbers);
            }
        }
    }
}

#[test]
#[ignore = "requires PYAMPLICOL_NATIVE_UUDD_PACBIN from the portable fixture"]
fn native_runtime_rejects_incomplete_or_incompatible_instructions() {
    let loaded = load_loop_runtime_pacbin(
        std::env::var("PYAMPLICOL_NATIVE_UUDD_PACBIN").expect("generated uudd PACBIN"),
    )
    .unwrap();
    let evaluators = || {
        loaded
            .evaluator_states()
            .map(|(name, bytes)| {
                (
                    name.to_owned(),
                    decode_exact_evaluator_state(bytes).unwrap(),
                )
            })
            .collect::<std::collections::BTreeMap<_, _>>()
    };
    let mut missing = evaluators();
    missing.pop_first();
    assert!(LoadedLoopRuntime::from_evaluators(loaded.plan().clone(), missing).is_err());
    let mut plan = loaded.plan().clone();
    plan.schema = 4;
    assert!(LoadedLoopRuntime::from_evaluators(plan, evaluators()).is_err());
    let mut plan = loaded.plan().clone();
    plan.dimensional_numerators = !plan.dimensional_numerators;
    assert!(LoadedLoopRuntime::from_evaluators(plan, evaluators()).is_err());
}

#[test]
#[ignore = "requires PYAMPLICOL_NATIVE_UUDD_PACBIN; isolates existing reducer stack"]
fn standalone_existing_reducer_constructor() {
    use rusticol_loop_reduction::runtime::PolynomialPlan;
    let loaded = load_loop_runtime_pacbin(
        std::env::var("PYAMPLICOL_NATIVE_UUDD_PACBIN").expect("generated uudd PACBIN"),
    )
    .unwrap();
    for family in &loaded.plan().families {
        eprintln!("existing primitive family {}", family.index);
        let reducer = PolynomialPlan::new(
            family.propagators,
            family.numerators.clone(),
            (0..family.powers.len()).map(|i| format!("c{i}")).collect(),
            "double-double",
            None,
            "generic",
        )
        .unwrap();
        assert_eq!(reducer.precision_bits(), 106);
    }
}
