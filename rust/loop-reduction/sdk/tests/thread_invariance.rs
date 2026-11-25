// SPDX-License-Identifier: 0BSD
//! Results do not depend on the number of native threads, driven through
//! the safe Rust SDK without Python. For every artifact of the feed, the
//! same calls (both reductions; unchecked and checked with one rotation and
//! the rescaled reduction-direction check; binary64 and double-double;
//! batches 1, 5, 16 and 17; ordinary, resolved and selected-helicity) are
//! made at 1, 2, 4, 8 and 16 threads (`Runtime::set_threads`), and every
//! returned buffer is compared bit for bit: statuses, successful point IDs,
//! the Born and virtual values and the uncertainties as IEEE bit patterns,
//! the axis IDs, the decimal values and the diagnostics JSON (rescue and
//! uncertified records, estimates). Each call is repeated at 8 threads.
//!
//! It needs generated artifacts, so it is ignored by default:
//! `PYAMPLICOL_THREAD_INVARIANCE_FEED=<feed.json> cargo test --release -p
//! rusticol-loop-sdk --test thread_invariance -- --ignored --nocapture`.
//! The feed is a list of `{"artifact", "process", "points"}`, each point
//! its momenta (4 per leg) and then mu_R², as IEEE bit patterns.
use rusticol_loop_sdk::{Arithmetic, Evaluation, Runtime, Selection, StabilityChecks};
use std::fmt::Write;

#[derive(serde::Deserialize)]
struct Case {
    artifact: String,
    process: String,
    points: Vec<Vec<u64>>,
}

const THREADS: [usize; 5] = [1, 2, 4, 8, 16];
const REPEATS: usize = 3;

/// Every buffer of an evaluation, doubles as bit patterns.
fn fingerprint(result: &Result<Evaluation, String>) -> String {
    let evaluation = match result {
        Ok(evaluation) => evaluation,
        Err(error) => return format!("error: {error}"),
    };
    let bits = |values: &[f64]| {
        values
            .iter()
            .map(|v| format!("{:016x}", v.to_bits()))
            .collect::<Vec<_>>()
            .join(",")
    };
    let mut out = String::new();
    writeln!(out, "requested {:?}", evaluation.requested_point_ids).unwrap();
    writeln!(out, "successful {:?}", evaluation.successful_point_ids).unwrap();
    writeln!(out, "statuses {:?}", evaluation.statuses).unwrap();
    writeln!(
        out,
        "shape {:?} resolved {}",
        evaluation.shape, evaluation.resolved
    )
    .unwrap();
    writeln!(out, "born {}", bits(&evaluation.born)).unwrap();
    writeln!(out, "virtual {}", bits(&evaluation.virtual_values)).unwrap();
    writeln!(out, "uncertainties {}", bits(&evaluation.uncertainties)).unwrap();
    writeln!(out, "helicity_ids {:?}", evaluation.helicity_ids).unwrap();
    writeln!(out, "color_ids {:?}", evaluation.color_ids).unwrap();
    writeln!(out, "decimal {:?}", evaluation.decimal).unwrap();
    writeln!(out, "diagnostics {}", evaluation.diagnostics_json).unwrap();
    out
}

fn first_difference(a: &str, b: &str) -> String {
    for (la, lb) in a.lines().zip(b.lines()) {
        if la != lb {
            let at = la
                .chars()
                .zip(lb.chars())
                .position(|(x, y)| x != y)
                .unwrap_or(la.len().min(lb.len()));
            let from = at.saturating_sub(60);
            return format!(
                "first differing line {:?}...: {:?} vs {:?}",
                la.split(' ').next().unwrap_or(""),
                la.get(from..(at + 80).min(la.len())).unwrap_or(""),
                lb.get(from..(at + 80).min(lb.len())).unwrap_or("")
            );
        }
    }
    format!("{} vs {} lines", a.lines().count(), b.lines().count())
}

struct Call {
    name: String,
    reduction: &'static str,
    checked: bool,
    arithmetic: Arithmetic,
    batch: usize,
    resolved: bool,
    selection: Option<Selection>,
}

fn calls(points: usize, helicities: &[String]) -> Vec<Call> {
    let mut out = Vec::new();
    for reduction in ["ninjars", "tirust"] {
        let mut add = |name: &str, checked, arithmetic, batch: usize, resolved, selection| {
            out.push(Call {
                name: format!("{reduction} {name}"),
                reduction,
                checked,
                arithmetic,
                batch: batch.min(points),
                resolved,
                selection,
            })
        };
        for batch in [1, 5, 16, 17] {
            add(
                &format!("unchecked b{batch}"),
                false,
                Arithmetic::Double,
                batch,
                false,
                None,
            );
            add(
                &format!("checked b{batch}"),
                true,
                Arithmetic::Double,
                batch,
                false,
                None,
            );
        }
        add(
            "unchecked resolved b5",
            false,
            Arithmetic::Double,
            5,
            true,
            None,
        );
        add(
            "unchecked selected b5",
            false,
            Arithmetic::Double,
            5,
            false,
            Some(Selection {
                helicities: Some(helicities.iter().take(2).cloned().collect()),
                ..Selection::default()
            }),
        );
        add(
            "unchecked double-double b2",
            false,
            Arithmetic::DoubleDouble,
            2,
            false,
            None,
        );
    }
    out
}

fn run(runtime: &mut Runtime, case: &Case, call: &Call) -> Result<Evaluation, String> {
    runtime
        .set_reduction(call.reduction)
        .map_err(|e| e.to_string())?;
    runtime.set_reduction_unchecked(!call.checked);
    runtime.set_stability_checks(if call.checked {
        StabilityChecks::with_default_rotations(1, true, true, false).unwrap()
    } else {
        StabilityChecks::with_default_rotations(0, false, false, false).unwrap()
    });
    runtime
        .set_arithmetic(call.arithmetic)
        .map_err(|e| e.to_string())?;
    let points = &case.points[..call.batch];
    let momenta: Vec<f64> = points
        .iter()
        .flat_map(|p| p[..p.len() - 1].iter().map(|&b| f64::from_bits(b)))
        .collect();
    let scales: Vec<f64> = points
        .iter()
        .map(|p| f64::from_bits(p[p.len() - 1]))
        .collect();
    let ids: Vec<u64> = (0..points.len() as u64).collect();
    match &call.selection {
        None => runtime.evaluate(&momenta, &ids, &scales, call.resolved, None),
        Some(selection) => {
            runtime.evaluate_selected(&momenta, &ids, &scales, call.resolved, None, selection)
        }
    }
    .map_err(|e| e.to_string())
}

#[test]
#[ignore = "needs PYAMPLICOL_THREAD_INVARIANCE_FEED; run with --ignored"]
fn results_do_not_depend_on_the_thread_count() {
    let feed: Vec<Case> = serde_json::from_str(
        &std::fs::read_to_string(
            std::env::var("PYAMPLICOL_THREAD_INVARIANCE_FEED")
                .expect("set PYAMPLICOL_THREAD_INVARIANCE_FEED"),
        )
        .unwrap(),
    )
    .unwrap();
    let mut differences = Vec::new();
    for case in &feed {
        let mut runtime = Runtime::open(&case.artifact, Some(&case.process), None, "auto").unwrap();
        let shape = runtime.shape();
        let helicities: Vec<String> = (0..shape.helicities).map(|i| format!("h{i}")).collect();
        let calls = calls(case.points.len(), &helicities);
        let mut reference: Vec<String> = Vec::new();
        for threads in THREADS {
            runtime.set_threads(Some(threads)).unwrap();
            for (index, call) in calls.iter().enumerate() {
                let found = fingerprint(&run(&mut runtime, case, call));
                if threads == 1 {
                    reference.push(found);
                    continue;
                }
                if found != reference[index] {
                    differences.push(format!(
                        "{} '{}' 1 vs {threads} threads (effective {:?}): {}",
                        case.artifact,
                        call.name,
                        runtime.threads(),
                        first_difference(&reference[index], &found)
                    ));
                }
                if threads == 8 {
                    for repeat in 1..REPEATS {
                        let again = fingerprint(&run(&mut runtime, case, call));
                        if again != found {
                            differences.push(format!(
                                "{} '{}' repeat {repeat} at 8 threads: {}",
                                case.artifact,
                                call.name,
                                first_difference(&found, &again)
                            ));
                        }
                    }
                }
            }
        }
        println!(
            "{}: {} calls x {} thread counts compared",
            case.artifact,
            calls.len(),
            THREADS.len()
        );
    }
    assert!(
        differences.is_empty(),
        "{}",
        differences[..differences.len().min(20)].join("\n")
    );
}
