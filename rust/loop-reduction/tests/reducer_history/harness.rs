// SPDX-License-Identifier: 0BSD

//! Call HISTORIES of one `V2Reducer` compared across worker counts.
//!
//! A history is a sequence of steps on one reducer: reduction calls (good,
//! refused rows, rejected inputs, panicking refinement callbacks), setter
//! changes (checked / unchecked, vanishing reason, target, best-effort pass)
//! and master clears. After EVERY step the harness records every figure the
//! public API exposes: the call's values (exact decimals), statuses, rescued,
//! uncertified and bounded lanes, its error text or panic message, the
//! master statistics and exact / rescued lane counts, and the retained state
//! (target, checked mode, precision, tracked precision, refinement carrier,
//! cached masters and, through `api::retained`, the built templates). The
//! same history is replayed serially (the reference) and with its calls on
//! pools of 1, 2, 8 and 16 workers in three placements (every call in the
//! pool; only the exceptional calls in the pool, the good ones serial, as
//! a reported reproduction; alternating): every record must be the
//! reference's, step by step.
use super::api;
use rusticol_loop_reduction::runtime::{
    Batch, FamilyGroup, GroupRefinementSource, Poles, ReduceOptions, ReductionFrame, V2Output,
    V2Reducer,
};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::atomic::{AtomicBool, Ordering};

pub const WORKERS: [usize; 4] = [1, 2, 8, 16];

/// The reducer's carrier: `(arithmetic, digits, engine)`.
#[derive(Clone, Copy, Debug)]
pub struct Carrier(pub &'static str, pub Option<u32>, pub &'static str);

pub const FAST: Carrier = Carrier("double", None, "fast");
pub const GENERIC64: Carrier = Carrier("double", None, "generic");
pub const DD: Carrier = Carrier("double-double", None, "generic");
pub const MP: Carrier = Carrier("arbitrary", Some(40), "generic");

/// The inputs of a call.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Fixture {
    /// `rows` tadpoles of squared mass `1e-12` (routed to the fast engine's
    /// exact engine: lazily built templates).
    Light(usize),
    /// `rows` tadpoles of squared mass 4.
    Heavy(usize),
    /// `rows` tadpoles of squared mass `4 + i`: the binary64 masters fail
    /// every lane (`MasterFailed`), refused rows of a call that returns.
    Failing(usize),
    /// One group of `rows` lanes cycling light, heavy and failing tadpoles,
    /// each lane its own point.
    Mixed(usize),
    /// An equal-mass bubble: squared mass, shift, imaginary part
    /// of the constant numerator coefficient (numerator `s² + 2 s q0`).
    Bubble(f64, f64, f64),
    /// A bubble whose numerator is `2^60 (1 + 2 q0)`: the fast engine's
    /// cancellation rescue flags it (the refinement source is asked).
    Rescued,
    /// A rejected input: a light tadpole and one with a complex
    /// shift (fast engine: "requires real shifts"); on the generic engines a
    /// batch whose masses have the wrong row count.
    Rejected,
    /// `rows` tadpoles, every third light, lane `bad` with a complex shift.
    RejectedMany(usize, usize),
    /// `groups` groups of one lane each (light, heavy, failing in turn).
    ManyGroups(usize),
}

/// The refinement source of a call (`reduce_refined`).
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Source {
    None,
    /// Exact rescue kinematics: every low part zero.
    Zero,
    /// A callback that panics at every lane asked.
    Panics,
    /// A callback that panics at the first lane asked, then serves zeros.
    PanicsOnce,
}

/// Point labels of a call (`api::reduce`; serial ones without labels on
/// builds whose API has none).
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Labels {
    None,
    /// Every lane its own point, labels counted down from `usize::MAX`.
    Extreme,
    /// Every lane labelled `usize::MAX`.
    AllMax,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Step {
    Call {
        fixture: Fixture,
        source: Source,
        check: bool,
        split: bool,
        labels: Labels,
    },
    SetUnchecked(bool),
    SetVanishing(Option<&'static str>),
    SetTarget(f64),
    SetBestEffort(bool),
    ClearMasters,
}

pub fn call(fixture: Fixture) -> Step {
    Step::Call {
        fixture,
        source: Source::None,
        check: false,
        split: false,
        labels: Labels::None,
    }
}

impl Step {
    /// A call expected to fail, panic or refuse rows: the steps the
    /// `Exceptional` placement runs on the pool.
    fn exceptional(&self) -> bool {
        matches!(
            self,
            Step::Call {
                fixture: Fixture::Rejected
                    | Fixture::RejectedMany(..)
                    | Fixture::Failing(_)
                    | Fixture::Mixed(_)
                    | Fixture::ManyGroups(_),
                ..
            } | Step::Call {
                source: Source::Panics | Source::PanicsOnce,
                ..
            }
        )
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Placement {
    All,
    Exceptional,
    Alternate,
}

pub const PLACEMENTS: [Placement; 3] =
    [Placement::All, Placement::Exceptional, Placement::Alternate];

/// `REDUCER_HISTORY_SCALE` (default 1): above 1, more random histories, 16
/// workers and the alternating placement too.
pub fn factor() -> usize {
    std::env::var("REDUCER_HISTORY_SCALE")
        .ok()
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(1)
        .max(1)
}

/// The placements compared (`factor() > 1`: all three).
pub fn placements() -> &'static [Placement] {
    if factor() > 1 {
        &PLACEMENTS
    } else {
        &PLACEMENTS[..2]
    }
}

/// The pools of the histories (`factor() > 1`: 16 workers too).
pub fn pools() -> &'static [usize] {
    if factor() > 1 {
        &WORKERS
    } else {
        &WORKERS[..3]
    }
}

struct Inputs {
    batches: Vec<[Batch; 5]>,
    propagators: Vec<usize>,
    lanes: usize,
}

fn decimal(z: [f64; 2]) -> [String; 2] {
    [format!("{:e}", z[0]), format!("{:e}", z[1])]
}

/// One group's five batches from complex values (row-major), in the
/// carrier's arithmetic, with `mass_rows` rows in the masses (a mismatch is
/// the generic engines' rejected input).
fn group_batches(
    c: Carrier,
    rows: usize,
    n: usize,
    shifts: &[[f64; 2]],
    masses: &[[f64; 2]],
    mass_rows: usize,
    scales: &[[f64; 2]],
    matrix: &[[f64; 2]],
    coefficients: &[[f64; 2]],
    width: usize,
) -> [Batch; 5] {
    let make = |values: &[[f64; 2]], rows: usize, columns: usize| {
        let ids: Vec<u64> = (0..rows as u64).collect();
        Batch::from_decimal(
            values.iter().copied().map(decimal).collect(),
            rows,
            columns,
            c.0,
            c.1,
            Some(ids),
        )
        .unwrap()
    };
    [
        make(shifts, rows, 4 * n),
        make(masses, mass_rows, n),
        make(scales, rows, 1),
        make(matrix, rows, n * n),
        make(coefficients, rows, width),
    ]
}

/// Tadpoles `∫ 1 / (q² - m²)` at `μ² = 16`, lane `r` of squared mass
/// `mass(r)` and shift time component `shift(r)`.
fn tadpole_group(
    c: Carrier,
    rows: usize,
    mass: impl Fn(usize) -> [f64; 2],
    shift: impl Fn(usize) -> [f64; 2],
    mass_rows: usize,
) -> [Batch; 5] {
    let shifts: Vec<[f64; 2]> = (0..rows)
        .flat_map(|r| [shift(r), [0., 0.], [0., 0.], [0., 0.]])
        .collect();
    let masses: Vec<[f64; 2]> = (0..mass_rows).map(&mass).collect();
    group_batches(
        c,
        rows,
        1,
        &shifts,
        &masses,
        mass_rows,
        &vec![[16., 0.]; rows],
        &vec![[0., 0.]; rows],
        &vec![[1., 0.]; rows],
        1,
    )
}

fn cycle(r: usize) -> [f64; 2] {
    match r % 3 {
        0 => [1e-12, 0.],
        1 => [4., 0.],
        _ => [4., 1.],
    }
}

fn inputs(c: Carrier, fixture: Fixture) -> Inputs {
    let fast = c.2 == "fast";
    let real = |_| [0., 0.];
    let one = |batches: [Batch; 5], n: usize, lanes: usize| Inputs {
        batches: vec![batches],
        propagators: vec![n],
        lanes,
    };
    match fixture {
        Fixture::Light(rows) => one(tadpole_group(c, rows, |_| [1e-12, 0.], real, rows), 1, rows),
        Fixture::Heavy(rows) => one(tadpole_group(c, rows, |_| [4., 0.], real, rows), 1, rows),
        Fixture::Failing(rows) => one(tadpole_group(c, rows, |_| [4., 1.], real, rows), 1, rows),
        Fixture::Mixed(rows) => one(tadpole_group(c, rows, cycle, real, rows), 1, rows),
        Fixture::Rejected => {
            let masses = |r| if r == 0 { [1e-12, 0.] } else { [4., 0.] };
            if fast {
                let shift = |r| if r == 1 { [0., 1.] } else { [0., 0.] };
                one(tadpole_group(c, 2, masses, shift, 2), 1, 2)
            } else {
                one(tadpole_group(c, 2, masses, real, 3), 1, 2)
            }
        }
        Fixture::RejectedMany(rows, bad) => {
            let masses = |r: usize| if r % 3 == 0 { [1e-12, 0.] } else { [4., 0.] };
            if fast {
                let shift = move |r| if r == bad { [0., 1.] } else { [0., 0.] };
                one(tadpole_group(c, rows, masses, shift, rows), 1, rows)
            } else {
                one(tadpole_group(c, rows, masses, real, rows + 1), 1, rows)
            }
        }
        Fixture::ManyGroups(groups) => Inputs {
            batches: (0..groups)
                .map(|g| tadpole_group(c, 1, |_| cycle(g), real, 1))
                .collect(),
            propagators: vec![1; groups],
            lanes: groups,
        },
        Fixture::Bubble(mass, shift, imag) => {
            let (p, s, m) = ([shift, 0.], [shift * shift, 0.], [mass, 0.]);
            let z = [0., 0.];
            one(
                group_batches(
                    c,
                    1,
                    2,
                    &[z, z, z, z, p, z, z, z],
                    &[m, m],
                    1,
                    &[[1., 0.]],
                    &[z, s, s, z],
                    &[[shift * shift, imag], [2. * shift, 0.], z, z, z],
                    5,
                ),
                2,
                1,
            )
        }
        Fixture::Rescued => {
            let n = 2f64.powi(60);
            let z = [0., 0.];
            let r = |x: f64| [x, 0.];
            one(
                group_batches(
                    c,
                    2,
                    2,
                    &[z, z, z, z, r(1.), z, z, z, z, z, z, z, r(1.), z, z, z],
                    &[r(4.), r(4.), r(4.), r(4.)],
                    2,
                    &[r(1.), r(1.)],
                    &[z, r(1.), r(1.), z, z, r(1.), r(1.), z],
                    &[r(n), r(2. * n), z, z, z, r(n), r(2. * n), z, z, z],
                    5,
                ),
                2,
                2,
            )
        }
    }
}

struct Refinement {
    panics: bool,
    once: AtomicBool,
}

impl GroupRefinementSource for Refinement {
    fn lane(
        &self,
        _: usize,
        _: usize,
        _: &mut [[f64; 4]],
        _: &mut [f64],
        _: &mut [rusticol_loop_reduction::C64],
    ) -> bool {
        if self.panics || self.once.swap(false, Ordering::SeqCst) {
            panic!("a refinement callback panics");
        }
        true
    }
}

/// Everything a call returns, as exact text.
fn output_text(output: &V2Output) -> String {
    let mut text = String::new();
    for (frame, batches) in std::iter::once(&output.direct)
        .chain(output.check.as_ref())
        .enumerate()
    {
        for (g, batch) in batches.iter().enumerate() {
            text += &format!(
                "  frame {frame} group {g} ids {:?} values {:?} statuses {:?}\n",
                batch.successful_values().ids(),
                batch.successful_values().to_decimal(),
                batch.statuses()
            );
        }
    }
    text += &format!(
        "  rescued {:?}\n  uncertified {:?}\n  bounds {:?}\n",
        output.rescued, output.uncertified, output.uncertified_bounds
    );
    text
}

fn panic_text(payload: Box<dyn std::any::Any + Send>) -> String {
    payload
        .downcast_ref::<&str>()
        .map(|s| s.to_string())
        .or_else(|| payload.downcast_ref::<String>().cloned())
        .unwrap_or_else(|| "a panic".into())
}

/// The retained state after a step (the serial reducer's API, then `api::retained`).
fn state(reducer: &mut V2Reducer, after_call: bool) -> String {
    let mut text = format!(
        "  state target {:e} unchecked {} bits {} tracked {:?} carrier {:?} cached masters {}\n",
        reducer.target(),
        reducer.unchecked(),
        reducer.precision_bits(),
        reducer.tracked_precision().map(|t| format!("{t:?}")),
        reducer.refinement_carrier().map(|t| format!("{t:?}")),
        reducer.cached_masters(),
    );
    text += &api::retained(reducer);
    if after_call {
        if let Some(s) = reducer.take_master_statistics() {
            text += &format!(
                "  masters requests {:?} evaluated {:?} hits {:?}\n",
                s.requests, s.evaluated, s.hits
            );
        }
        text += &format!(
            "  exact lanes {} rescued lanes {}\n",
            reducer.take_exact_lanes(),
            reducer.take_rescued_lanes()
        );
    }
    text
}

/// One step on `reducer`, its calls on a pool of `workers` (`None`: serial).
fn apply(reducer: &mut V2Reducer, c: Carrier, step: &Step, workers: Option<usize>) -> String {
    match *step {
        Step::SetUnchecked(on) => reducer.set_unchecked(on),
        Step::SetVanishing(reason) => reducer.set_vanishing(reason),
        Step::SetTarget(target) => reducer.set_target(target),
        Step::SetBestEffort(on) => reducer.set_best_effort_pass(on),
        Step::ClearMasters => reducer.clear_masters(),
        Step::Call {
            fixture,
            source,
            check,
            split,
            labels,
        } => {
            let input = inputs(c, fixture);
            let groups: Vec<FamilyGroup<'_>> = input
                .batches
                .iter()
                .zip(&input.propagators)
                .map(|(b, &n)| FamilyGroup {
                    propagators: n,
                    shifts: &b[0],
                    masses_squared: &b[1],
                    scales_squared: &b[2],
                    s_matrix: &b[3],
                    coefficients: &b[4],
                })
                .collect();
            let label = |k: usize| match labels {
                Labels::None => k,
                Labels::Extreme => usize::MAX - k,
                Labels::AllMax => usize::MAX,
            };
            let mut next = 0;
            let points: Vec<Vec<usize>> = input
                .batches
                .iter()
                .map(|b| {
                    (0..b[0].rows())
                        .map(|_| {
                            next += 1;
                            label(next - 1)
                        })
                        .collect()
                })
                .collect();
            let views: Vec<&[usize]> = points.iter().map(|p| p.as_slice()).collect();
            let refinement = Refinement {
                panics: source == Source::Panics,
                once: AtomicBool::new(source == Source::PanicsOnce),
            };
            let source: Option<&dyn GroupRefinementSource> = match source {
                Source::None => None,
                _ => Some(&refinement),
            };
            let options = ReduceOptions {
                poles: if split { Poles::Split } else { Poles::All },
                check: check.then_some(ReductionFrame::REVERSED),
                ..ReduceOptions::default()
            };
            let with_labels = (labels != Labels::None).then_some(views.as_slice());
            let caught = catch_unwind(AssertUnwindSafe(|| {
                api::run(workers, || {
                    api::reduce(reducer, &groups, with_labels, source, options)
                })
            }));
            let mut text = format!("call {step:?} ({} lanes)\n", input.lanes);
            text += &match caught {
                Ok(Ok(output)) => output_text(&output),
                Ok(Err(error)) => format!("  error {error}\n"),
                Err(payload) => format!("  panic {}\n", panic_text(payload)),
            };
            return text + state(reducer, true).as_str();
        }
    }
    format!("{step:?}\n") + state(reducer, false).as_str()
}

fn placement_of(p: Placement, k: usize, step: &Step, workers: usize) -> Option<usize> {
    match p {
        Placement::All => Some(workers),
        Placement::Exceptional => step.exceptional().then_some(workers),
        Placement::Alternate => (k % 2 == 0).then_some(workers),
    }
}

/// The records of one history: serially (`None`) or on `workers` in
/// placement `p`.
pub fn replay(c: Carrier, steps: &[Step], at: Option<(usize, Placement)>) -> Vec<String> {
    let mut reducer = V2Reducer::new(c.0, c.1, c.2, true).unwrap();
    steps
        .iter()
        .enumerate()
        .map(|(k, step)| {
            let workers = at.and_then(|(w, p)| placement_of(p, k, step, w));
            apply(&mut reducer, c, step, workers)
        })
        .collect()
}

/// Compare one history across worker counts and placements against its
/// serial replay; returns the first difference (step, records) if any.
/// With `REDUCER_HISTORY_DUMP=<dir>`, the serial records are written to
/// `<dir>/<name>.txt` (to compare the serial records of two builds).
pub fn check(name: &str, c: Carrier, steps: &[Step], workers: &[usize]) -> Result<(), String> {
    let serial = replay(c, steps, None);
    if let Ok(dir) = std::env::var("REDUCER_HISTORY_DUMP") {
        let _ = std::fs::create_dir_all(&dir);
        std::fs::write(
            format!("{dir}/{name}.txt"),
            serial
                .iter()
                .enumerate()
                .map(|(k, r)| format!("step {k}: {r}"))
                .collect::<String>(),
        )
        .unwrap();
    }
    for &w in workers {
        for &p in placements() {
            let got = replay(c, steps, Some((w, p)));
            for (k, (a, b)) in serial.iter().zip(&got).enumerate() {
                if a != b {
                    return Err(format!(
                        "HISTORY {name} ({c:?}): {w} workers, placement {p:?}: first difference \
                         at step {k}\nserial:\n{a}\nwith workers:\n{b}\nhistory: {steps:#?}"
                    ));
                }
            }
        }
    }
    Ok(())
}

/// A small deterministic generator (xorshift64*).
pub struct Rng(pub u64);
impl Rng {
    pub fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545_f491_4f6c_dd1d)
    }
    pub fn pick<T: Copy>(&mut self, items: &[T]) -> T {
        items[(self.next() % items.len() as u64) as usize]
    }
}

pub const REASONS: [Option<&str>; 3] = [
    None,
    Some("test: a symmetry proof"),
    Some("test: another reason"),
];

/// A random history of `length` steps mixing rejected calls, refused rows,
/// setter changes and good calls (`labels`: the API takes point labels).
pub fn random_history(rng: &mut Rng, c: Carrier, length: usize, labels: bool) -> Vec<Step> {
    let fast = c.2 == "fast";
    let mut fixtures = vec![
        Fixture::Light(3),
        Fixture::Heavy(1),
        Fixture::Heavy(24),
        Fixture::Mixed(40),
        Fixture::Rejected,
        Fixture::RejectedMany(48, 31),
        Fixture::Bubble(1e-12, 1.0, 0.),
        Fixture::Bubble(4.0, 1e-5, 1e-30),
        Fixture::Bubble(1e-12, 1e-5, 0.),
    ];
    if fast {
        fixtures.extend([
            Fixture::Failing(20),
            Fixture::Rescued,
            Fixture::ManyGroups(300),
        ]);
    }
    let sources = if fast {
        vec![
            Source::None,
            Source::None,
            Source::Zero,
            Source::Panics,
            Source::PanicsOnce,
        ]
    } else {
        vec![Source::None]
    };
    (0..length)
        .map(|_| match rng.next() % 10 {
            0 => Step::SetUnchecked(rng.next() % 2 == 0),
            1 => Step::SetVanishing(rng.pick(&REASONS)),
            2 => Step::SetTarget(rng.pick(&[1e-8, 1e-12, 1e-15, 1e-25, 1e-28])),
            3 => Step::SetBestEffort(rng.next() % 2 == 0),
            4 => Step::ClearMasters,
            _ => {
                let fixture = rng.pick(&fixtures);
                Step::Call {
                    fixture,
                    source: rng.pick(&sources),
                    check: rng.next() % 3 == 0,
                    split: rng.next() % 4 == 0,
                    labels: if labels && rng.next() % 3 == 0 {
                        rng.pick(&[Labels::Extreme, Labels::AllMax])
                    } else {
                        Labels::None
                    },
                }
            }
        })
        .collect()
}

/// A fresh unchecked binary64 fast reducer, a call rejected on an invalid
/// shift beside a light tadpole, then checking on, a vanishing reason and
/// target `1e-8`, then equal-mass bubbles at three masses / shifts, two
/// targets and three imaginary parts.
pub fn rejected_then_checked_history() -> Vec<Step> {
    let mut steps = vec![
        Step::SetUnchecked(true),
        call(Fixture::Rejected),
        Step::SetUnchecked(false),
        Step::SetVanishing(Some("test: a vanishing reason")),
    ];
    for (mass, shift) in [(1e-12, 1.0), (4.0, 1e-5), (1e-12, 1e-5)] {
        for target in [1e-8, 1e-25] {
            steps.push(Step::SetTarget(target));
            for imag in [0., 1e-30, 1e-300] {
                steps.push(call(Fixture::Bubble(mass, shift, imag)));
            }
        }
    }
    steps
}
