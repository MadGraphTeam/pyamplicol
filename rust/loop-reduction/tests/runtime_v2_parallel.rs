// SPDX-License-Identifier: 0BSD

//! The parallel NinjaRS reduction (`lane_slices`): every value, status,
//! rescued and uncertified lane and every count of a reduction call is the
//! same bit for bit on pools of 1, 2, 4, 8 and 16 threads as the serial
//! reduction's, in binary64 (fast engine, checked and unchecked, with and
//! without the check's frame and the lanes' points), double-double and
//! arbitrary precision, over several calls of one reducer.
use rusticol_loop_reduction::runtime::{
    Batch, Data, FamilyGroup, GroupRefinementSource, LaneViews, Poles, ReduceOptions,
    ReductionFrame, V2Output, V2Reducer, tensor_monomials,
};

const TOP: f64 = 90000.0;

struct Family {
    legs: Vec<Vec<usize>>,
    masses: Vec<f64>,
    rank: usize,
}

fn families() -> Vec<Family> {
    vec![
        Family {
            legs: vec![vec![0], vec![1], vec![2], vec![3]],
            masses: vec![0., 0., TOP, 0.],
            rank: 3,
        },
        Family {
            legs: vec![vec![0], vec![1], vec![2], vec![3]],
            masses: vec![0., 0., 0., 0.],
            rank: 4,
        },
        Family {
            legs: vec![vec![2], vec![0, 1, 3]],
            masses: vec![TOP, 0.],
            rank: 2,
        },
        Family {
            legs: vec![vec![0, 1], vec![2], vec![3]],
            masses: vec![0., TOP, 0.],
            rank: 2,
        },
        Family {
            legs: vec![vec![0, 1], vec![2, 3]],
            masses: vec![TOP, TOP],
            rank: 2,
        },
    ]
}

/// A triangle with a light squared mass: its binary64 lanes reach the fast
/// engine's absolute threshold and are routed to the exact engine.
fn light() -> Family {
    Family {
        legs: vec![vec![0, 1], vec![2], vec![3]],
        masses: vec![1e-12, TOP, 0.],
        rank: 2,
    }
}

/// Massless incoming and massive outgoing momenta of a 2 -> 2 point at
/// scattering angles (`theta`, `phi`).
fn momenta(theta: f64, phi: f64) -> [[f64; 4]; 4] {
    let (x, y, z) = (
        400. * theta.sin() * phi.cos(),
        400. * theta.sin() * phi.sin(),
        400. * theta.cos(),
    );
    [
        [500., 0., 0., 500.],
        [500., 0., 0., -500.],
        [500., x, y, z],
        [500., -x, -y, -z],
    ]
}

struct Lanes {
    n: usize,
    shifts: Batch,
    masses: Batch,
    scales: Batch,
    matrix: Batch,
    coefficients: Batch,
    points: Vec<usize>,
}

fn decimal(values: &[f64]) -> Vec<[String; 2]> {
    values
        .iter()
        .map(|x| [format!("{x:e}"), "0".into()])
        .collect()
}

/// A family's lanes: `columns` lanes per point, point-major (as the
/// executor lays them out).
fn lanes(
    family: &Family,
    points: &[[[f64; 4]; 4]],
    columns: usize,
    arithmetic: &str,
    digits: Option<u32>,
) -> Lanes {
    let n = family.legs.len();
    let width = tensor_monomials(family.rank).len();
    let (mut shifts, mut matrix, mut coefficients, mut owner) = (vec![], vec![], vec![], vec![]);
    for (point, p) in points.iter().enumerate() {
        let mut v = [0.0_f64; 4];
        let mut vectors = vec![];
        for legs in &family.legs {
            for &leg in legs {
                let sign = if leg < 2 { 1. } else { -1. };
                for mu in 0..4 {
                    v[mu] += sign * p[leg][mu];
                }
            }
            vectors.push(v);
        }
        vectors.rotate_right(1);
        vectors[0] = [0.; 4];
        for column in 0..columns {
            owner.push(point);
            for vector in &vectors {
                shifts.extend_from_slice(vector);
            }
            for a in &vectors {
                for b in &vectors {
                    let d: Vec<_> = (0..4).map(|mu| a[mu] - b[mu]).collect();
                    matrix.push(d[0] * d[0] - d[1] * d[1] - d[2] * d[2] - d[3] * d[3]);
                }
            }
            for k in 0..width {
                let x = (k * 7 + 3 * point + 11 * column + 1) as f64;
                coefficients.push([(x * 0.37).sin() * 10., (x * 0.11).cos()]);
            }
        }
    }
    let rows = owner.len();
    let ids: Vec<u64> = (0..rows as u64).collect();
    let batch = |values: Vec<[String; 2]>, columns| {
        Batch::from_decimal(values, rows, columns, arithmetic, digits, Some(ids.clone())).unwrap()
    };
    let complex: Vec<[String; 2]> = coefficients
        .iter()
        .map(|[re, im]: &[f64; 2]| [format!("{re:e}"), format!("{im:e}")])
        .collect();
    Lanes {
        n,
        shifts: batch(decimal(&shifts), 4 * n),
        masses: batch(decimal(&family.masses.repeat(rows)), n),
        scales: batch(decimal(&vec![8.0e5; rows]), 1),
        matrix: batch(decimal(&matrix), n * n),
        coefficients: batch(complex, width),
        points: owner,
    }
}

fn group(lanes: &Lanes) -> FamilyGroup<'_> {
    FamilyGroup {
        propagators: lanes.n,
        shifts: &lanes.shifts,
        masses_squared: &lanes.masses,
        scales_squared: &lanes.scales,
        s_matrix: &lanes.matrix,
        coefficients: &lanes.coefficients,
    }
}

/// `rows` rank-zero tadpoles `∫ 1 / (q² - m²)` at `μ² = 16`, lane `row`
/// labelled with point `label(row)`. With a complex `m²` the binary64
/// masters fail every lane (`MasterFailed`), a refused row in a call that
/// returns.
fn tadpoles(
    rows: usize,
    [re, im]: [f64; 2],
    arithmetic: &str,
    digits: Option<u32>,
    label: impl Fn(usize) -> usize,
) -> Lanes {
    let ids: Vec<u64> = (0..rows as u64).collect();
    let batch = |values: Vec<[String; 2]>, columns| {
        Batch::from_decimal(values, rows, columns, arithmetic, digits, Some(ids.clone())).unwrap()
    };
    let complex = |z: [f64; 2], count: usize| -> Vec<[String; 2]> {
        (0..count)
            .map(|_| [format!("{:e}", z[0]), format!("{:e}", z[1])])
            .collect()
    };
    Lanes {
        n: 1,
        shifts: batch(complex([0., 0.], 4 * rows), 4),
        masses: batch(complex([re, im], rows), 1),
        scales: batch(complex([16., 0.], rows), 1),
        matrix: batch(complex([0., 0.], rows), 1),
        coefficients: batch(complex([1., 0.], rows), tensor_monomials(0).len()),
        points: (0..rows).map(label).collect(),
    }
}

fn all_lanes(points: usize, columns: usize, arithmetic: &str, digits: Option<u32>) -> Vec<Lanes> {
    let kinematics: Vec<_> = (0..points)
        .map(|k| momenta(0.3 + 2.5 * k as f64 / points as f64, 0.7 * k as f64))
        .collect();
    families()
        .into_iter()
        .chain(std::iter::once(light()))
        .collect::<Vec<_>>()
        .iter()
        .map(|family| lanes(family, &kinematics, columns, arithmetic, digits))
        // Lanes whose masters fail (refused rows beside the served ones), on
        // the same points.
        .chain(std::iter::once(tadpoles(
            points * columns,
            [4., 1.],
            arithmetic,
            digits,
            |row| row / columns,
        )))
        .collect()
}

/// Everything a call returns, as exact text (decimals of every value).
fn fingerprint(output: &V2Output, reducer: &mut V2Reducer) -> String {
    let mut text = String::new();
    for (frame, batches) in std::iter::once(&output.direct)
        .chain(output.check.as_ref())
        .enumerate()
    {
        for (g, batch) in batches.iter().enumerate() {
            text += &format!(
                "frame {frame} group {g} ids {:?} values {:?} statuses {:?}\n",
                batch.successful_values().ids(),
                batch.successful_values().to_decimal(),
                batch.statuses()
            );
        }
    }
    text += &format!(
        "rescued {:?}\nuncertified {:?}\nbounds {:?}\n",
        output.rescued, output.uncertified, output.uncertified_bounds
    );
    if let Some(statistics) = reducer.take_master_statistics() {
        text += &format!(
            "masters requests {:?} evaluated {:?} hits {:?}\n",
            statistics.requests, statistics.evaluated, statistics.hits
        );
    }
    text += &format!(
        "exact lanes {} rescued lanes {}\n",
        reducer.take_exact_lanes(),
        reducer.take_rescued_lanes()
    );
    text
}

/// Three calls of one reducer (a new chunk of points before the first and
/// the third).
fn calls(
    reducer: &mut V2Reducer,
    all: &[Lanes],
    options: ReduceOptions,
    with_points: bool,
) -> Vec<String> {
    let groups: Vec<_> = all.iter().map(group).collect();
    let points: Vec<&[usize]> = all.iter().map(|l| l.points.as_slice()).collect();
    let mut out = Vec::new();
    for call in 0..3 {
        // A new chunk of points (`begin`) before the first and the third
        // call; the second reuses the first's masters.
        if call != 1 {
            reducer.clear_masters();
        }
        let output = reducer
            .reduce_at(
                &groups,
                with_points.then_some(points.as_slice()),
                None,
                options,
            )
            .unwrap();
        out.push(fingerprint(&output, reducer));
    }
    out
}

fn reducer(arithmetic: &str, digits: Option<u32>, engine: &str, unchecked: bool) -> V2Reducer {
    let mut reducer = V2Reducer::new(arithmetic, digits, engine, true).unwrap();
    reducer.set_unchecked(unchecked);
    reducer
}

fn check_invariance(
    arithmetic: &str,
    digits: Option<u32>,
    engine: &str,
    points: usize,
    columns: usize,
    threads: &[usize],
) {
    // The generic engines build Symbolica expressions: the library key on
    // this thread (the pool's workers unlock theirs, as the executor's do).
    let _unlock = pyamplicol::unlock();
    let all = all_lanes(points, columns, arithmetic, digits);
    for unchecked in [false, true] {
        for check in [None, Some(ReductionFrame::REVERSED)] {
            let options = ReduceOptions {
                poles: Poles::Split,
                check,
                ..ReduceOptions::default()
            };
            // The serial reduction: called outside any pool.
            let serial = calls(
                &mut reducer(arithmetic, digits, engine, unchecked),
                &all,
                options,
                false,
            );
            for &t in threads {
                let pool = rayon::ThreadPoolBuilder::new()
                    .num_threads(t)
                    .start_handler(|_| pyamplicol::unlock_thread())
                    .build()
                    .unwrap();
                for with_points in [false, true] {
                    // One reducer across settings changes, as the executor
                    // keeps its backend.
                    let mut parallel = reducer(arithmetic, digits, engine, !unchecked);
                    pool.install(|| {
                        let _ = calls(&mut parallel, &all, options, with_points);
                        parallel.set_unchecked(unchecked);
                        let got = calls(&mut parallel, &all, options, with_points);
                        for (call, (a, b)) in serial.iter().zip(&got).enumerate() {
                            assert!(
                                a == b,
                                "{arithmetic} {engine} unchecked {unchecked} check {check:?} \
                                 {t} threads points {with_points} call {call}:\n{a}\nvs\n{b}"
                            );
                        }
                    });
                }
            }
        }
    }
}

#[test]
fn binary64_fast_reductions_do_not_depend_on_the_threads() {
    check_invariance("double", None, "fast", 24, 7, &[1, 2, 4, 8, 16]);
}

#[test]
fn double_double_reductions_do_not_depend_on_the_threads() {
    check_invariance("double-double", None, "generic", 3, 2, &[1, 2, 4]);
}

#[test]
fn arbitrary_precision_reductions_do_not_depend_on_the_threads() {
    check_invariance("arbitrary", Some(40), "generic", 2, 1, &[1, 3]);
}

/// The executor's path (typed slices, `reduce_views`) reduces as the batch
/// path (`reduce_at`), bit for bit, serially and on a pool.
#[test]
fn lane_views_reduce_as_batches() {
    let _unlock = pyamplicol::unlock();
    let all = all_lanes(6, 3, "double", None);
    let groups: Vec<_> = all.iter().map(group).collect();
    fn slice(b: &Batch) -> &[rusticol_loop_reduction::Complex<f64>] {
        match b.data() {
            Data::Double(values) => values.as_slice(),
            _ => panic!("binary64 lanes"),
        }
    }
    let views: Vec<LaneViews<'_, f64>> = all
        .iter()
        .map(|l| LaneViews {
            propagators: l.n,
            rows: l.points.len(),
            shifts: slice(&l.shifts),
            masses_squared: slice(&l.masses),
            scales_squared: slice(&l.scales),
            s_matrix: slice(&l.matrix),
            coefficients: slice(&l.coefficients),
        })
        .collect();
    let options = ReduceOptions {
        poles: Poles::Split,
        check: Some(ReductionFrame::REVERSED),
        ..ReduceOptions::default()
    };
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(4)
        .start_handler(|_| pyamplicol::unlock_thread())
        .build()
        .unwrap();
    let reduce = |with_views: bool| {
        let mut reducer = reducer("double", None, "fast", false);
        let output = if with_views {
            reducer.reduce_views(&views, None, None, options)
        } else {
            reducer.reduce_at(&groups, None, None, options)
        };
        fingerprint(&output.unwrap(), &mut reducer)
    };
    let serial = reduce(false);
    assert_eq!(serial, reduce(true));
    pool.install(|| {
        assert_eq!(serial, reduce(false));
        assert_eq!(serial, reduce(true));
    });
}

/// Invariant 5: a parallel reduction builds no template of its own on its
/// workers (the generic engines lend the reducer's templates per bucket;
/// the fast engine's routed lanes share the reducer's exact engine): the
/// templates kept after a call are the serial reduction's, at any count.
#[test]
fn parallel_reductions_build_no_template_per_worker() {
    let _unlock = pyamplicol::unlock();
    for (arithmetic, engine, points) in [("double", "fast", 6), ("double-double", "generic", 2)] {
        let all = all_lanes(points, 2, arithmetic, None);
        let groups: Vec<_> = all.iter().map(group).collect();
        let options = ReduceOptions {
            poles: Poles::All,
            check: Some(ReductionFrame::REVERSED),
            ..ReduceOptions::default()
        };
        let mut serial = reducer(arithmetic, None, engine, false);
        let want = fingerprint(
            &serial.reduce_at(&groups, None, None, options).unwrap(),
            &mut serial,
        );
        let templates = serial.built_templates();
        assert!(templates > 0, "{arithmetic}: the call builds templates");
        for threads in [2, 8] {
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(threads)
                .start_handler(|_| pyamplicol::unlock_thread())
                .build()
                .unwrap();
            let mut parallel = reducer(arithmetic, None, engine, false);
            pool.install(|| {
                for _ in 0..2 {
                    let got = fingerprint(
                        &parallel.reduce_at(&groups, None, None, options).unwrap(),
                        &mut parallel,
                    );
                    parallel.clear_masters();
                    assert_eq!(got, want, "{arithmetic} {threads} threads");
                }
            });
            assert_eq!(
                parallel.built_templates(),
                templates,
                "{arithmetic} {threads} threads"
            );
        }
    }
}

/// One call's fingerprint at `threads` workers (`None`: outside any pool,
/// the serial reduction).
fn one_call(all: &[Lanes], threads: Option<usize>, options: ReduceOptions) -> String {
    let groups: Vec<_> = all.iter().map(group).collect();
    let points: Vec<&[usize]> = all.iter().map(|l| l.points.as_slice()).collect();
    let run = || {
        let mut reducer = reducer("double", None, "fast", false);
        let output = reducer
            .reduce_at(&groups, Some(points.as_slice()), None, options)
            .unwrap();
        fingerprint(&output, &mut reducer)
    };
    match threads {
        None => run(),
        Some(threads) => rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .start_handler(|_| pyamplicol::unlock_thread())
            .build()
            .unwrap()
            .install(run),
    }
}

/// Review finding 1: point labels are any `usize`; a parallel reduction
/// orders a bucket's lanes by comparison, never by the label's value (32
/// valid tadpoles labelled `usize::MAX` panicked at two workers before).
#[test]
fn point_labels_of_any_value_reduce_as_the_serial_reduction() {
    let _unlock = pyamplicol::unlock();
    let options = ReduceOptions::default();
    for label in [
        (|_| usize::MAX) as fn(usize) -> usize,
        |row| usize::MAX - row,
        |row| if row % 2 == 0 { usize::MAX } else { row << 40 },
    ] {
        let all = vec![tadpoles(32, [4., 0.], "double", None, label)];
        let serial = one_call(&all, None, options);
        assert!(
            !serial.contains("MasterFailed"),
            "valid tadpoles:\n{serial}"
        );
        for threads in [1, 2, 8] {
            assert_eq!(
                one_call(&all, Some(threads), options),
                serial,
                "{threads} workers"
            );
        }
    }
}

/// Review finding 2: 32 tadpoles with `m² = 4 + i` fail their masters in a
/// call that returns; the statuses and every master count are the serial
/// reduction's at any worker count, and the failed row counts once (as main
/// counts it in one engine call).
#[test]
fn failed_master_rows_count_once_per_call_at_any_worker_count() {
    let _unlock = pyamplicol::unlock();
    let options = ReduceOptions::default();
    let all = vec![tadpoles(32, [4., 1.], "double", None, |_| 0)];
    let serial = one_call(&all, None, options);
    assert_eq!(serial.matches("MasterFailed").count(), 32, "{serial}");
    assert!(
        serial.contains("masters requests [32, 0, 0, 0, 0, 0] evaluated [1, 0, 0, 0, 0, 0] hits [31, 0, 0, 0, 0, 0]"),
        "{serial}"
    );
    for threads in [1, 2, 8] {
        assert_eq!(
            one_call(&all, Some(threads), options),
            serial,
            "{threads} workers"
        );
    }
    // Several points and the check's frame: still once per key and call.
    let all = vec![tadpoles(64, [4., 1.], "double", None, |row| row / 8)];
    let options = ReduceOptions {
        check: Some(ReductionFrame::REVERSED),
        ..ReduceOptions::default()
    };
    let serial = one_call(&all, None, options);
    for threads in [2, 8, 16] {
        assert_eq!(
            one_call(&all, Some(threads), options),
            serial,
            "{threads} workers"
        );
    }
}

/// A pool of `threads` workers, unlocked as the executor's.
fn pool(threads: usize) -> rayon::ThreadPool {
    rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .start_handler(|_| pyamplicol::unlock_thread())
        .build()
        .unwrap()
}

/// `rows` tadpoles as `tadpoles`, the shift of lane `bad_shift` and the
/// scale of lane `bad_scale` made complex (each an invalid input of the fast
/// engine), each lane its own point.
fn invalid_tadpoles(rows: usize, bad_shift: Option<usize>, bad_scale: Option<usize>) -> Lanes {
    let ids: Vec<u64> = (0..rows as u64).collect();
    let batch = |values: Vec<[String; 2]>, columns| {
        Batch::from_decimal(values, rows, columns, "double", None, Some(ids.clone())).unwrap()
    };
    let z = |re: f64, im: f64| [format!("{re:e}"), format!("{im:e}")];
    let shifts = (0..4 * rows)
        .map(|k| {
            if Some(k / 4) == bad_shift && k % 4 == 0 {
                z(0., 1.)
            } else {
                z(0., 0.)
            }
        })
        .collect();
    let scales = (0..rows)
        .map(|row| {
            if Some(row) == bad_scale {
                z(16., 1.)
            } else {
                z(16., 0.)
            }
        })
        .collect();
    Lanes {
        n: 1,
        shifts: batch(shifts, 4),
        masses: batch((0..rows).map(|_| z(4., 0.)).collect(), 1),
        scales: batch(scales, 1),
        matrix: batch((0..rows).map(|_| z(0., 0.)).collect(), 1),
        coefficients: batch((0..rows).map(|_| z(1., 0.)).collect(), 1),
        points: (0..rows).collect(),
    }
}

/// The error text of a call at `threads` workers (`None`: serial).
fn error_of(reducer: &mut V2Reducer, all: &[Lanes], threads: Option<usize>) -> String {
    let groups: Vec<_> = all.iter().map(group).collect();
    let points: Vec<&[usize]> = all.iter().map(|l| l.points.as_slice()).collect();
    let mut call = || {
        reducer
            .reduce_at(
                &groups,
                Some(points.as_slice()),
                None,
                ReduceOptions::default(),
            )
            .err()
            .map(|e| e.to_string())
            .expect("an invalid input")
    };
    match threads {
        None => call(),
        Some(threads) => pool(threads).install(call),
    }
}

/// Review finding 4 (a rejected batch): after a call that fails on an
/// invalid input, the next successful call's counters are the serial
/// reduction's at every worker count (the reviewer's sequence: masters
/// cleared, then two equal tadpoles, 2 requests and 1 evaluation).
#[test]
fn a_rejected_call_leaves_nothing_in_the_next_report() {
    let _unlock = pyamplicol::unlock();
    let good = vec![tadpoles(2, [4., 0.], "double", None, |row| row)];
    let groups: Vec<_> = good.iter().map(group).collect();
    let points: Vec<&[usize]> = good.iter().map(|l| l.points.as_slice()).collect();
    for threads in [None, Some(1), Some(2), Some(8)] {
        let mut reducer = reducer("double", None, "fast", false);
        // Many valid lanes and one invalid one: slices without it run first
        // in parallel.
        let bad = vec![invalid_tadpoles(64, Some(37), None)];
        let _ = error_of(&mut reducer, &bad, threads);
        reducer.clear_masters();
        let mut call = || {
            let output = reducer
                .reduce_at(
                    &groups,
                    Some(points.as_slice()),
                    None,
                    ReduceOptions::default(),
                )
                .unwrap();
            fingerprint(&output, &mut reducer)
        };
        let report = match threads {
            None => call(),
            Some(threads) => pool(threads).install(call),
        };
        assert!(
            report.contains("masters requests [2, 0, 0, 0, 0, 0] evaluated [1, 0, 0, 0, 0, 0]"),
            "{threads:?} workers:\n{report}"
        );
    }
}

/// Review finding 4 (several invalid inputs): the error is the serial
/// reduction's, the first in serial order, at every worker count.
#[test]
fn several_invalid_inputs_report_the_serial_error() {
    let _unlock = pyamplicol::unlock();
    for (shift, scale) in [(Some(40), Some(3)), (Some(3), Some(40)), (None, Some(50))] {
        let bad = vec![invalid_tadpoles(64, shift, scale)];
        let serial = error_of(&mut reducer("double", None, "fast", false), &bad, None);
        for threads in [1, 2, 8] {
            let got = error_of(
                &mut reducer("double", None, "fast", false),
                &bad,
                Some(threads),
            );
            assert_eq!(
                got, serial,
                "{threads} workers, invalid {shift:?} {scale:?}"
            );
        }
    }
}

/// Review finding 4 (a warm topology switch): one reducer called serially,
/// then on pools of 2 and 8 workers and serially again, without clearing
/// its masters, reports what a reducer that stayed serial reports, call by
/// call (values, statuses, every counter).
#[test]
fn a_warm_reducer_switching_worker_counts_reports_as_the_serial_one() {
    let _unlock = pyamplicol::unlock();
    let all = all_lanes(6, 2, "double", None);
    let groups: Vec<_> = all.iter().map(group).collect();
    let points: Vec<&[usize]> = all.iter().map(|l| l.points.as_slice()).collect();
    let options = ReduceOptions {
        check: Some(ReductionFrame::REVERSED),
        ..ReduceOptions::default()
    };
    let call = |reducer: &mut V2Reducer| {
        let output = reducer
            .reduce_at(&groups, Some(points.as_slice()), None, options)
            .unwrap();
        fingerprint(&output, reducer)
    };
    let mut serial = reducer("double", None, "fast", false);
    let want: Vec<String> = (0..5).map(|_| call(&mut serial)).collect();
    let mut switching = reducer("double", None, "fast", false);
    let got = [
        call(&mut switching),
        pool(2).install(|| call(&mut switching)),
        pool(8).install(|| call(&mut switching)),
        call(&mut switching),
        pool(2).install(|| call(&mut switching)),
    ];
    for (k, (a, b)) in want.iter().zip(&got).enumerate() {
        assert_eq!(a, b, "call {k}");
    }
}

/// A refinement source that panics (a caller's callback failing).
struct Panicking;
impl GroupRefinementSource for Panicking {
    fn lane(
        &self,
        _: usize,
        _: usize,
        _: &mut [[f64; 4]],
        _: &mut [f64],
        _: &mut [rusticol_loop_reduction::C64],
    ) -> bool {
        panic!("a refinement callback panics");
    }
}

fn typed(values: &[f64], columns: usize) -> Batch {
    Batch::typed(
        values
            .iter()
            .map(|&v| rusticol_loop_reduction::Complex::new(v, 0.))
            .collect(),
        (0..(values.len() / columns) as u64).collect(),
        columns,
        53,
    )
    .unwrap()
}

/// Review finding 1 (the routed exact engine): a panic in a refinement
/// callback during a two-worker call leaves the reducer as the
/// uninterrupted one: after `set_target(1e-28)` a light tadpole (routed to
/// the exact engine) is refused `Unstable` as on a reducer that was never
/// interrupted (the reviewer's sequence).
#[test]
fn a_panic_in_a_parallel_call_leaves_the_reducer_as_the_uninterrupted_one() {
    let _unlock = pyamplicol::unlock();
    let tadpole = [
        typed(&[0., 0., 0., 0.], 4),
        typed(&[1e-12], 1),
        typed(&[1.], 1),
        typed(&[0.], 1),
        typed(&[1.], 1),
    ];
    let n = 2f64.powi(60);
    let bubble = [
        typed(
            &[
                0., 0., 0., 0., 1., 0., 0., 0., 0., 0., 0., 0., 1., 0., 0., 0.,
            ],
            8,
        ),
        typed(&[4., 4., 4., 4.], 2),
        typed(&[1., 1.], 1),
        typed(&[0., 1., 1., 0., 0., 1., 1., 0.], 4),
        typed(&[n, 2. * n, 0., 0., 0., n, 2. * n, 0., 0., 0.], 5),
    ];
    fn family(b: &[Batch; 5], n: usize) -> Vec<FamilyGroup<'_>> {
        vec![FamilyGroup {
            propagators: n,
            shifts: &b[0],
            masses_squared: &b[1],
            scales_squared: &b[2],
            s_matrix: &b[3],
            coefficients: &b[4],
        }]
    }
    let mut reports = Vec::new();
    for interrupt in [false, true] {
        let mut reducer = V2Reducer::new("double", None, "fast", true).unwrap();
        let warm = reducer
            .reduce(&family(&tadpole, 1), ReduceOptions::default())
            .unwrap();
        let mut report = format!("warm {:?}\n", warm.direct[0].statuses());
        if interrupt {
            let caught = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                pool(2).install(|| {
                    reducer.reduce_refined(
                        &family(&bubble, 2),
                        Some(&Panicking),
                        ReduceOptions::default(),
                    )
                })
            }));
            assert!(caught.is_err(), "the callback panics");
        }
        reducer.set_target(1e-28);
        let after = reducer
            .reduce(&family(&tadpole, 1), ReduceOptions::default())
            .unwrap();
        report += &format!("after {:?}\n", after.direct[0].statuses());
        report += &fingerprint(&after, &mut reducer);
        reports.push(report);
    }
    assert!(reports[0].contains("Unstable"), "control:\n{}", reports[0]);
    assert_eq!(reports[1], reports[0]);
}
