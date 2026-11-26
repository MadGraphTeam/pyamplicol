// SPDX-License-Identifier: 0BSD

use std::collections::BTreeMap;

use serde_json::json;

use super::*;

/// A guard file with one guard: `(MT - 173) * c` vanishes (`c` stands for the
/// coupling's other factors), recorded for every process.
fn vanishing_file(kind: &str, process_ids: Option<Vec<&str>>) -> Vec<u8> {
    let mut guard = json!({
        "kind": kind,
        "subject": "coupling GC_X removed by restriction simplification",
        "producer": "restriction-simplification",
        "parameters": ["MT", "aEWM1"],
        "generation_values": {"MT": [173.0, 0.0], "aEWM1": [132.5, 0.0]},
        // (MT + -173) * aEWM1 * i
        "program": [
            ["p", 0], ["c", -173.0, 0.0], ["add", 2],
            ["p", 1], ["c", 0.0, 1.0], ["mul", 3],
        ],
        "expression": "(MT-173)*aEWM1*i",
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

fn binding(entries: &[(&str, f64)]) -> BTreeMap<String, (f64, f64)> {
    entries
        .iter()
        .map(|(name, value)| ((*name).to_string(), (*value, 0.0)))
        .collect()
}

#[test]
fn a_binding_that_revives_a_removed_coupling_is_refused_naming_it() {
    let guards = SpecializationGuards::parse(&vanishing_file("vanishing", None), "p").unwrap();
    let error = guards
        .check_binding(&binding(&[("MT", 174.0)]), |_| None)
        .unwrap_err();
    assert_eq!(error.kind(), crate::RusticolErrorKind::ModelParameter);
    let message = error.message();
    assert!(message.starts_with("specialisation-guard: binding MT invalidates a vanishing"));
    assert!(message.contains("coupling GC_X removed by restriction simplification"));
    assert!(message.contains("recorded by restriction-simplification"));
}

#[test]
fn a_binding_that_keeps_the_condition_is_accepted() {
    let guards = SpecializationGuards::parse(&vanishing_file("vanishing", None), "p").unwrap();
    // The removed coupling stays zero when only the other factor changes,
    // when MT keeps its value and when an unrelated parameter is bound.
    for entries in [
        &[("aEWM1", 130.0)][..],
        &[("MT", 173.0)][..],
        &[("MZ", 91.0)][..],
    ] {
        guards.check_binding(&binding(entries), |_| None).unwrap();
    }
}

#[test]
fn rounding_level_departures_hold_and_larger_ones_fail() {
    let guards = SpecializationGuards::parse(&vanishing_file("vanishing", None), "p").unwrap();
    // The bound of (MT - 173) is MT + 173, so a departure of a few units in
    // the last place of MT is rounding: TOLERANCE * 346 is about 2.5e-12.
    let ulp = 173.0_f64.next_up() - 173.0;
    guards
        .check_binding(&binding(&[("MT", 173.0 + 8.0 * ulp)]), |_| None)
        .unwrap();
    guards
        .check_binding(&binding(&[("MT", 173.0 + 1e-9)]), |_| None)
        .unwrap_err();
}

#[test]
fn the_current_values_complete_the_binding() {
    let guards = SpecializationGuards::parse(&vanishing_file("vanishing", None), "p").unwrap();
    // A runtime that already moved MT away refuses a later aEWM1 binding.
    let current = |name: &str| (name == "MT").then_some((174.0, 0.0));
    guards
        .check_binding(&binding(&[("aEWM1", 130.0)]), current)
        .unwrap_err();
}

#[test]
fn a_real_guard_tests_the_imaginary_part() {
    // "real" of (MT - 173) * aEWM1 * i: real iff MT = 173 (up to rounding).
    let guards = SpecializationGuards::parse(&vanishing_file("real", None), "p").unwrap();
    guards
        .check_binding(&binding(&[("MT", 173.0)]), |_| None)
        .unwrap();
    let error = guards
        .check_binding(&binding(&[("MT", 174.0)]), |_| None)
        .unwrap_err();
    assert!(error.message().contains("not real"));
}

#[test]
fn process_scoped_guards_apply_to_their_processes_only() {
    let file = vanishing_file("vanishing", Some(vec!["a"]));
    assert_eq!(SpecializationGuards::parse(&file, "a").unwrap().len(), 1);
    assert!(SpecializationGuards::parse(&file, "b").unwrap().is_empty());
}

#[test]
fn a_guard_without_a_program_holds_only_at_its_generation_values() {
    let mut file: serde_json::Value =
        serde_json::from_slice(&vanishing_file("vanishing", None)).unwrap();
    file["guards"][0]["program"] = serde_json::Value::Null;
    let guards = SpecializationGuards::parse(&serde_json::to_vec(&file).unwrap(), "p").unwrap();
    guards
        .check_binding(&binding(&[("MT", 173.0)]), |_| None)
        .unwrap();
    guards
        .check_binding(&binding(&[("aEWM1", 130.0)]), |_| None)
        .unwrap_err();
}

#[test]
fn malformed_programs_are_refused_at_load() {
    for program in [
        json!([["add", 2]]),
        json!([["p", 5]]),
        json!([["p", 0], ["p", 1]]),
        json!([["fn", "gamma"]]),
        json!([["p", 0], ["fn", "sqrt", 1]]),
    ] {
        let mut file: serde_json::Value =
            serde_json::from_slice(&vanishing_file("vanishing", None)).unwrap();
        file["guards"][0]["program"] = program;
        SpecializationGuards::parse(&serde_json::to_vec(&file).unwrap(), "p").unwrap_err();
    }
}

#[test]
fn functions_and_powers_follow_the_python_twin() {
    // sqrt(MT)^2 - MT vanishes up to rounding at every MT; exp(log(MT)) - MT too.
    let program = |body: Vec<serde_json::Value>| {
        let mut file: serde_json::Value =
            serde_json::from_slice(&vanishing_file("vanishing", None)).unwrap();
        file["guards"][0]["program"] = json!(body);
        SpecializationGuards::parse(&serde_json::to_vec(&file).unwrap(), "p").unwrap()
    };
    let squared = program(vec![
        json!(["p", 0]),
        json!(["fn", "sqrt"]),
        json!(["c", 2.0, 0.0]),
        json!(["pow"]),
        json!(["c", -1.0, 0.0]),
        json!(["p", 0]),
        json!(["mul", 2]),
        json!(["add", 2]),
    ]);
    let logarithm = program(vec![
        json!(["p", 0]),
        json!(["fn", "log"]),
        json!(["fn", "exp"]),
        json!(["c", -1.0, 0.0]),
        json!(["p", 0]),
        json!(["mul", 2]),
        json!(["add", 2]),
    ]);
    for value in [2.0, 174.0, 1e6] {
        squared
            .check_binding(&binding(&[("MT", value)]), |_| None)
            .unwrap();
        logarithm
            .check_binding(&binding(&[("MT", value)]), |_| None)
            .unwrap();
    }
}
