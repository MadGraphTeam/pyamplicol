// SPDX-License-Identifier: 0BSD

//! The parallel NinjaRS reduction (`lane_slices`): every value, status,
//! rescued and uncertified lane and every count of a reduction call is the
//! same bit for bit on pools of 1, 2, 4, 8 and 16 threads as the serial
//! reduction's, in binary64 (fast engine, checked and unchecked, with and
//! without the check's frame and the lanes' points), double-double and
//! arbitrary precision, over several calls of one reducer.
use rusticol_loop_reduction::runtime::{
    Batch, Data, FamilyGroup, LaneViews, Poles, ReduceOptions, ReductionFrame, V2Output, V2Reducer,
    tensor_monomials,
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
