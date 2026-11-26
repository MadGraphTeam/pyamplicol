// SPDX-License-Identifier: 0BSD

//! HISTORIES of one reducer do not depend on the worker count: sequences of
//! rejected calls, refused rows, panicking refinement callbacks, setter
//! changes and good calls give the same values, statuses, reasons, counters
//! and retained state (`tests/reducer_history/harness.rs`) step by step at 1,
//! 2, 8 and 16 workers as serially, in every placement of the calls; and the
//! standalone public `MasterCache` retries a failed row at the next ordinary
//! `evaluate`, as on main. By default the pools have 1, 2 and 8 workers
//! (16 for two histories) and two placements; `REDUCER_HISTORY_SCALE=k`
//! (k > 1) multiplies the random histories (4 binary64, 2 with point labels,
//! 1 per generic carrier) by `k`, adds 16 workers and the third placement.
#[path = "reducer_history/api.rs"]
mod api;
#[path = "reducer_history/harness.rs"]
mod harness;

use harness::*;
use ninjars::fast::{C64, FastMaster, FastMasters};
use rusticol_loop_reduction::runtime::MasterCache;

fn scale(default: usize) -> usize {
    default * factor()
}

fn report(failures: Vec<String>) {
    assert!(
        failures.is_empty(),
        "{} histories differ:\n\n{}",
        failures.len(),
        failures.join("\n\n")
    );
}

/// A rejected call (which builds a template on two workers) followed by
/// checked calls with a vanishing reason and two targets.
#[test]
fn the_rejected_then_checked_history_is_the_same_at_every_worker_count() {
    let _unlock = pyamplicol::unlock();
    report(
        check(
            "rejected-then-checked",
            FAST,
            &rejected_then_checked_history(),
            &WORKERS,
        )
        .err()
        .into_iter()
        .collect(),
    );
}

#[test]
fn random_binary64_histories_are_the_same_at_every_worker_count() {
    let _unlock = pyamplicol::unlock();
    let mut failures = vec![];
    for seed in 1..=scale(4) as u64 {
        let steps = random_history(&mut Rng(0x9e37_79b9_7f4a_7c15 ^ seed), FAST, 10, false);
        failures.extend(check(&format!("fast-{seed}"), FAST, &steps, pools()).err());
    }
    report(failures);
}

#[test]
fn random_generic_histories_are_the_same_at_every_worker_count() {
    let _unlock = pyamplicol::unlock();
    let mut failures = vec![];
    for (tag, c) in [("generic64", GENERIC64), ("dd", DD), ("mp", MP)] {
        for seed in 1..=scale(1) as u64 {
            let steps = random_history(&mut Rng(0x51_7cc1_b727_220a ^ seed), c, 8, false);
            let pools: &[usize] = if factor() > 1 { &[1, 2, 8] } else { &[1, 2] };
            failures.extend(check(&format!("{tag}-{seed}"), c, &steps, pools).err());
        }
    }
    report(failures);
}

/// Degenerate slicings: one lane, one group, more workers than lanes,
/// thousands of one-lane groups, each with refused rows and setters between.
#[test]
fn degenerate_slicings_are_the_same_at_every_worker_count() {
    let _unlock = pyamplicol::unlock();
    let checked = |fixture| Step::Call {
        fixture,
        source: Source::None,
        check: true,
        split: true,
        labels: Labels::None,
    };
    let steps = vec![
        call(Fixture::Heavy(1)),
        checked(Fixture::Light(1)),
        call(Fixture::Failing(1)),
        call(Fixture::Light(3)),
        Step::SetUnchecked(true),
        checked(Fixture::Mixed(2)),
        call(Fixture::ManyGroups(500)),
        Step::SetUnchecked(false),
        Step::SetTarget(1e-25),
        checked(Fixture::ManyGroups(500)),
        Step::ClearMasters,
        call(Fixture::Mixed(1)),
        call(Fixture::RejectedMany(17, 16)),
        call(Fixture::Heavy(1)),
    ];
    let mut failures: Vec<String> = check("degenerate-fast", FAST, &steps, pools())
        .err()
        .into_iter()
        .collect();
    let generic: Vec<Step> = steps
        .iter()
        .copied()
        .filter(|s| {
            !matches!(
                s,
                Step::Call {
                    fixture: Fixture::ManyGroups(_) | Fixture::Failing(_),
                    ..
                }
            )
        })
        .chain([call(Fixture::ManyGroups(64))])
        .collect();
    failures.extend(check("degenerate-dd", DD, &generic, &[1, 16]).err());
    report(failures);
}

/// Caught unwinds: a refinement callback that panics (always, or once)
/// during a call, then setters and good calls on the same reducer.
#[test]
fn caught_unwinds_leave_the_same_reducer_at_every_worker_count() {
    let _unlock = pyamplicol::unlock();
    let rescued = |source, check| Step::Call {
        fixture: Fixture::Rescued,
        source,
        check,
        split: false,
        labels: Labels::None,
    };
    let steps = vec![
        call(Fixture::Light(3)),
        rescued(Source::Panics, false),
        Step::SetTarget(1e-28),
        call(Fixture::Light(1)),
        rescued(Source::PanicsOnce, true),
        rescued(Source::Zero, true),
        Step::SetVanishing(Some("test: after an unwind")),
        call(Fixture::Bubble(1e-12, 1.0, 0.)),
        call(Fixture::Mixed(40)),
        rescued(Source::Panics, true),
        Step::SetUnchecked(true),
        call(Fixture::Rejected),
        Step::SetUnchecked(false),
        call(Fixture::Bubble(1e-12, 1.0, 0.)),
        rescued(Source::None, false),
    ];
    report(
        check("unwinds", FAST, &steps, pools())
            .err()
            .into_iter()
            .collect(),
    );
}

/// Extreme point labels (`usize::MAX` and counted down from it) in random
/// histories (builds whose API takes point labels).
#[test]
fn histories_with_extreme_point_labels_are_the_same_at_every_worker_count() {
    if !api::LABELS {
        return;
    }
    let _unlock = pyamplicol::unlock();
    let mut failures = vec![];
    for seed in 1..=scale(2) as u64 {
        let steps = random_history(&mut Rng(0x2545_f491_4f6c_dd1d ^ seed), FAST, 10, true);
        failures.extend(check(&format!("labels-{seed}"), FAST, &steps, pools()).err());
    }
    report(failures);
}

/// A scripted master provider: invocation `k` does `script[k]` (the last
/// entry repeats): `'o'` serves 17 + k, `'f'` reports the row failed, `'p'`
/// panics.
struct Scripted {
    script: &'static [u8],
    calls: usize,
}

impl FastMasters for Scripted {
    fn evaluate(
        &mut self,
        _: FastMaster,
        _: &[C64],
        out: &mut [[C64; 3]],
        ok: &mut [bool],
    ) -> ninjars::Result<()> {
        let k = self.calls;
        self.calls += 1;
        let action = self.script[k.min(self.script.len() - 1)];
        if action == b'p' {
            panic!("a master provider panics");
        }
        for (o, v) in ok.iter_mut().zip(out.iter_mut()) {
            *o = action == b'o';
            *v = [C64::real(17. + k as f64); 3];
        }
        Ok(())
    }
}

/// The standalone public `MasterCache` (no grouped call): histories of
/// ordinary `evaluate` calls with a provider that fails or panics once.
/// Main retries a failed row at the next ordinary call (its own unit test);
/// the records are dumped with `REDUCER_HISTORY_DUMP`.
#[test]
fn the_standalone_master_cache_retries_a_failed_row_as_main() {
    let mut records = String::new();
    let mut failures = vec![];
    for script in [&b"fo"[..], b"po", b"ffo", b"ofo", b"fpo", b"o"] {
        for enabled in [true, false] {
            let mut cache = MasterCache::new(Scripted { script, calls: 0 }, enabled);
            let mut oks = vec![];
            for (attempt, (name, master)) in [
                ("C0", FastMaster::C0),
                ("C0", FastMaster::C0),
                ("A0", FastMaster::A0),
                ("C0", FastMaster::C0),
                ("C0", FastMaster::C0),
            ]
            .into_iter()
            .enumerate()
            {
                let args = vec![C64::real(if name == "A0" { 2. } else { 1. }); master.arity()];
                let mut out = [[C64::ZERO; 3]];
                let mut ok = [false];
                let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    cache.evaluate(master, &args, &mut out, &mut ok)
                }));
                let s = cache.statistics();
                records += &format!(
                    "script {} enabled {enabled} attempt {attempt} {name}: {} ok {} value {} len {} requests {:?} evaluated {:?} hits {:?}\n",
                    String::from_utf8_lossy(script),
                    match &r {
                        Ok(Ok(())) => "returned".to_string(),
                        Ok(Err(e)) => format!("error {e:?}"),
                        Err(_) => "panicked".to_string(),
                    },
                    ok[0],
                    out[0][0].re,
                    cache.len(),
                    s.requests,
                    s.evaluated,
                    s.hits
                );
                oks.push(r.is_ok() && ok[0]);
            }
            // Main's rule: a row that failed (or whose provider panicked)
            // is asked again at the next ordinary call, which then serves it.
            if script != b"o" && script[1] == b'o' && !(!oks[0] && oks[1]) {
                failures.push(format!(
                    "script {} enabled {enabled}: attempts 1 and 2 ok {:?}, main gives [false, true]",
                    String::from_utf8_lossy(script),
                    &oks[..2]
                ));
            }
        }
    }
    if let Ok(dir) = std::env::var("REDUCER_HISTORY_DUMP") {
        let _ = std::fs::create_dir_all(&dir);
        std::fs::write(format!("{dir}/master-cache.txt"), &records).unwrap();
    }
    assert!(failures.is_empty(), "{}\n{records}", failures.join("\n"));
}

/// An invalid input and a panicking refinement callback in one call: the
/// outcome is the serial one (main's: the input error) at every worker count.
#[test]
fn an_invalid_input_and_a_panicking_callback_give_the_serial_outcome() {
    let _unlock = pyamplicol::unlock();
    let steps = vec![
        Step::SetTarget(1e-25),
        Step::Call {
            fixture: Fixture::RejectedMany(48, 31),
            source: Source::Panics,
            check: false,
            split: false,
            labels: Labels::None,
        },
        Step::SetTarget(1e-12),
        call(Fixture::Mixed(40)),
    ];
    report(
        check("error-vs-panic", FAST, &steps, &WORKERS)
            .err()
            .into_iter()
            .collect(),
    );
}
