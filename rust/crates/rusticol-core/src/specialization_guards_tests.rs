// SPDX-License-Identifier: 0BSD

use std::collections::BTreeMap;

use serde_json::json;

use super::*;

/// A guard file with one guard holding `MT` (real) and `CKM` (complex) at
/// their generation values, recorded for every process or for `process_ids`.
fn guard_file(process_ids: Option<Vec<&str>>) -> Vec<u8> {
    let mut guard = json!({
        "kind": "vanishing",
        "subject": "coupling GC_X removed by restriction simplification",
        "producer": "restriction-simplification",
        "parameters": ["CKM", "MT"],
        "generation_values": {"CKM": [0.97, 0.25], "MT": [173.0, 0.0]},
        "generation_exact": {"CKM": ["0.97", "0.25"], "MT": ["173.0", "0.0"]},
        "expression": "(MT-173)^6*CKM",
        "message": "generate the artifact at the new values",
    });
    if let Some(ids) = process_ids {
        guard["process_ids"] = json!(ids);
    }
    serde_json::to_vec(&json!({
        "kind": GUARD_FILE_KIND,
        "schema_version": GUARD_FILE_SCHEMA_VERSION,
        "guards": [guard],
    }))
    .unwrap()
}

fn binding(entries: &[(&str, f64, f64)]) -> BTreeMap<String, (f64, f64)> {
    entries
        .iter()
        .map(|(name, re, im)| ((*name).to_string(), (*re, *im)))
        .collect()
}

#[test]
fn any_change_of_a_guarded_parameter_is_refused_naming_it() {
    let guards = SpecializationGuards::parse(&guard_file(None), "p").unwrap();
    // (MT - 173)^6 is exactly 1 at 174: no tolerance can accept it.
    let error = guards
        .check_binding(&binding(&[("MT", 174.0, 0.0)]))
        .unwrap_err();
    assert_eq!(error.kind(), crate::RusticolErrorKind::ModelParameter);
    let message = error.message();
    assert!(message.starts_with("specialisation-guard: binding MT invalidates a vanishing"));
    assert!(message.contains("MT = 174.0 (generated at 173.0)"));
    assert!(message.contains("recorded by restriction-simplification"));
    // The smallest change is refused too.
    let next = f64::from_bits(173.0_f64.to_bits() + 1);
    assert!(
        guards
            .check_binding(&binding(&[("MT", next, 0.0)]))
            .is_err()
    );
}

#[test]
fn exactly_the_generation_value_is_accepted() {
    let guards = SpecializationGuards::parse(&guard_file(None), "p").unwrap();
    guards
        .check_binding(&binding(&[("MT", 173.0, 0.0)]))
        .unwrap();
    guards
        .check_binding(&binding(&[("CKM", 0.97, 0.25), ("MT", 173.0, -0.0)]))
        .unwrap();
    // Unguarded parameters are free.
    guards
        .check_binding(&binding(&[("MZ", 91.0, 0.0)]))
        .unwrap();
}

#[test]
fn both_components_of_a_complex_parameter_are_held() {
    let guards = SpecializationGuards::parse(&guard_file(None), "p").unwrap();
    assert!(
        guards
            .check_binding(&binding(&[("CKM", 0.97, 0.0)]))
            .is_err()
    );
    assert!(
        guards
            .check_binding(&binding(&[("CKM", 0.97, 0.26)]))
            .is_err()
    );
    assert!(
        guards
            .check_binding(&binding(&[("CKM", 0.98, 0.25)]))
            .is_err()
    );
}

#[test]
fn a_guard_scoped_to_other_processes_does_not_apply() {
    let guards = SpecializationGuards::parse(&guard_file(Some(vec!["other"])), "p").unwrap();
    assert!(guards.is_empty());
    guards
        .check_binding(&binding(&[("MT", 174.0, 0.0)]))
        .unwrap();
    let guards = SpecializationGuards::parse(&guard_file(Some(vec!["p"])), "p").unwrap();
    assert_eq!(guards.len(), 1);
}

#[test]
fn a_custom_comparison_decides_in_the_binding_precision() {
    let guards = SpecializationGuards::parse(&guard_file(None), "p").unwrap();
    // A binding that is exact elsewhere (the one-loop runtime's rationals)
    // says itself whether it equals the recorded binary64.
    guards
        .check_with(|parameter| match parameter.name {
            "MT" => {
                assert_eq!(parameter.exact[0], "173.0");
                (Bound::Unchanged, String::new())
            }
            _ => (Bound::Untouched, String::new()),
        })
        .unwrap();
    let error = guards
        .check_with(|parameter| match parameter.name {
            "MT" => (Bound::Changed, "173.00000000000000001".to_string()),
            _ => (Bound::Untouched, String::new()),
        })
        .unwrap_err();
    assert!(error.message().contains("MT = 173.00000000000000001"));
}

#[test]
fn the_producers_exact_text_is_kept_and_checked_against_the_binary64() {
    // 173 + 2^-15: Python's repr writes 173.00003051757812, Rust's Debug
    // 173.00003051757813; both round to the same binary64. The reader keeps
    // the producer's text and never formats the float.
    let value = 173.0 + 2.0_f64.powi(-15);
    let file = |exact: &str| {
        serde_json::to_vec(&json!({
            "kind": GUARD_FILE_KIND,
            "schema_version": GUARD_FILE_SCHEMA_VERSION,
            "guards": [{
                "kind": "vanishing", "subject": "s", "producer": "p",
                "parameters": ["MT"],
                "generation_values": {"MT": [value, 0.0]},
                "generation_exact": {"MT": [exact, "0.0"]},
                "expression": "", "message": "m",
            }],
        }))
        .unwrap()
    };
    let guards = SpecializationGuards::parse(&file("173.00003051757812"), "p").unwrap();
    let (exact, generation) = {
        let parameter = guards.guards()[0].guarded().next().unwrap();
        (parameter.exact[0].clone(), parameter.generation.re)
    };
    assert_eq!(exact, "173.00003051757812");
    assert_eq!(generation, value);
    assert_ne!(format!("{value:?}"), exact);
    // Text that does not round to the binary64 is refused.
    assert!(SpecializationGuards::parse(&file("173.0001"), "p").is_err());
}

#[test]
fn malformed_records_are_refused() {
    for bad in [
        json!({"kind": "vanishing", "subject": "s", "producer": "p", "parameters": [],
               "generation_values": {}, "expression": "", "message": "m"}),
        json!({"kind": "vanishing", "subject": "s", "producer": "p", "parameters": ["b", "a"],
               "generation_values": {"a": [1.0, 0.0], "b": [1.0, 0.0]}, "expression": "", "message": "m"}),
        json!({"kind": "vanishing", "subject": "s", "producer": "p", "parameters": ["a"],
               "generation_values": {"b": [1.0, 0.0]}, "expression": "", "message": "m"}),
        json!({"kind": "vanishing", "subject": "s", "producer": "p", "parameters": ["a"],
               "generation_values": {"a": [1.0, 0.0]}, "expression": "", "message": "m",
               "program": []}),
        json!({"kind": "other", "subject": "s", "producer": "p", "parameters": ["a"],
               "generation_values": {"a": [1.0, 0.0]}, "expression": "", "message": "m"}),
    ] {
        let bytes = serde_json::to_vec(&json!({
            "kind": GUARD_FILE_KIND,
            "schema_version": GUARD_FILE_SCHEMA_VERSION,
            "guards": [bad],
        }))
        .unwrap();
        assert!(SpecializationGuards::parse(&bytes, "p").is_err());
    }
}
