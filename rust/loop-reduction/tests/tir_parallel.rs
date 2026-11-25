// SPDX-License-Identifier: 0BSD

//! The TIR backend's parallel reduction (`v2_tir` module docs 'Threads'):
//! what its per-worker engines need from TIRust (Send bounds), and every
//! value, reason, measure and count independent of the number of threads,
//! in every carrier, unchecked and checked (rotation copy, rescaled frame),
//! with the method choice, its acceptance and the last resort at work.
#![cfg(feature = "tir")]

use iregi_rust::{DirectReductionPlan, DirectWorkspace, TensorStore};
use ninjars::fast::tensor_layout::ncoeff;
use rusticol_core::loop_execution::v2::{
    FamilyLanes, LaneKey, LaneOutcome, Poles, Reduced, V2Backend,
};
use rusticol_core::loop_v2::dress::{Carrier, cast, exact_value};
use rusticol_core::loop_v2::retest::ReductionCheck;
use rusticol_loop_reduction::runtime::{TypedBatch, V2Backends};
use rusticol_loop_reduction::v2_tir::{TirOptions, TirReductionBackend};
use symbolica::domains::float::{Complex, DoubleFloat, Float, RealLike};

type C = Complex<f64>;

fn send<T: Send>() {}
fn sync<T: Sync>() {}

/// What a worker's engine needs from TIRust: workspaces that move to a
/// worker, plans and the store shared between them.
#[test]
fn tirust_engines_can_move_to_a_worker() {
    send::<DirectWorkspace<f64>>();
    send::<DirectWorkspace<DoubleFloat>>();
    send::<DirectWorkspace<Float>>();
    send::<DirectReductionPlan>();
    sync::<DirectReductionPlan>();
    send::<TensorStore>();
    sync::<TensorStore>();
    send::<TirReductionBackend>();
}

/// A deterministic generator of reals in (-1, 1).
struct Lcg(u64);

impl Lcg {
    fn next(&mut self) -> f64 {
        self.0 = self
            .0
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        ((self.0 >> 11) as f64 / (1u64 << 53) as f64) * 2. - 1.
    }
}

fn minkowski(v: [f64; 4]) -> f64 {
    v[0] * v[0] - v[1] * v[1] - v[2] * v[2] - v[3] * v[3]
}

/// One family's lanes over `points` (shifts per point), `columns` lanes per
/// point, coefficients of true rank `rank`.
fn family(
    family: usize,
    points: &[Vec<[f64; 4]>],
    masses: &[f64],
    rank: usize,
    columns: usize,
    rng: &mut Lcg,
) -> FamilyLanes<f64> {
    let n = masses.len();
    let mut out = FamilyLanes {
        family,
        propagators: n,
        rank,
        points: Vec::new(),
        keys: Vec::new(),
        shifts: Vec::new(),
        masses: Vec::new(),
        scales: Vec::new(),
        s_matrix: Vec::new(),
        coefficients: Vec::new(),
    };
    for (p, shifts) in points.iter().enumerate() {
        for column in 0..columns {
            out.points.push(p);
            out.keys.push(LaneKey {
                family,
                order: 0,
                column,
            });
            for v in shifts {
                out.shifts.extend(v.iter().map(|&x| C::new(x, 0.)));
            }
            out.masses.extend(masses.iter().map(|&m| C::new(m, 0.)));
            out.scales.push(C::new(91.188 * 91.188, 0.));
            for i in 0..n {
                for j in 0..n {
                    let d = std::array::from_fn(|mu| shifts[i][mu] - shifts[j][mu]);
                    out.s_matrix.push(C::new(minkowski(d), 0.));
                }
            }
            for _ in 0..ncoeff(rank) {
                out.coefficients.push(C::new(rng.next(), rng.next()));
            }
        }
    }
    out
}

/// Generic shifts of `n` propagators.
fn generic(n: usize, rng: &mut Lcg) -> Vec<[f64; 4]> {
    let mut shifts = vec![[0.; 4]];
    for _ in 1..n {
        let last = *shifts.last().unwrap();
        let p = [
            400. + 150. * rng.next(),
            200. * rng.next(),
            200. * rng.next(),
            200. * rng.next(),
        ];
        shifts.push(std::array::from_fn(|mu| last[mu] + p[mu]));
    }
    shifts
}

/// Near-forward box shifts at `sin(theta) = 2m / (m^2 + 1)` (exact
/// Pythagorean momenta: massless invariants exactly zero, small Gram
/// determinants the gates refuse).
fn forward(m: f64) -> Vec<[f64; 4]> {
    let unit = 2f64.powi(-(((m * m + 1.) / 500.).log2().ceil() as i32));
    let (a, b, c) = ((m * m - 1.) * unit, 2. * m * unit, (m * m + 1.) * unit);
    let p1 = [c, 0., 0., c];
    let p2 = [c, 0., 0., -c];
    let p3 = [c, b, 0., a];
    let v2: [f64; 4] = std::array::from_fn(|mu| p1[mu] + p2[mu]);
    let v3: [f64; 4] = std::array::from_fn(|mu| v2[mu] - p3[mu]);
    vec![[0.; 4], p1, v2, v3]
}

/// Families of 1 to 6 propagators at several points (massless and massive
/// lines, ranks up to N + 1) and near-forward top boxes (gate refusals:
/// method choice, acceptance, last resort): many rows of unequal cost.
fn groups() -> Vec<FamilyLanes<f64>> {
    let mut rng = Lcg(41);
    let mut out = Vec::new();
    let mt2 = 173. * 173.;
    for n in 1..=6usize {
        let points: Vec<_> = (0..5).map(|_| generic(n, &mut rng)).collect();
        let massless = vec![0.; n];
        let massive: Vec<f64> = (0..n).map(|k| if k % 2 == 0 { mt2 } else { 0. }).collect();
        for (masses, rank) in [(&massless, n.min(4)), (&massive, (n + 1).min(5))] {
            let index = out.len();
            out.push(family(index, &points, masses, rank, 3, &mut rng));
        }
    }
    let points: Vec<_> = [100., 1000., 9000., 30000.].map(forward).into();
    for rank in [4, 6] {
        let index = out.len();
        out.push(family(index, &points, &[mt2; 4], rank, 2, &mut rng));
    }
    out
}

fn lift<T: Carrier>(groups: &[FamilyLanes<f64>], zero: &T) -> Vec<FamilyLanes<T>> {
    let z = |v: &[C]| -> Vec<Complex<T>> {
        v.iter()
            .map(|c| {
                let exact = |x: f64| cast(zero, &exact_value(&x).expect("a finite input"));
                Complex::new(exact(c.re), exact(c.im))
            })
            .collect()
    };
    groups
        .iter()
        .map(|g| FamilyLanes {
            family: g.family,
            propagators: g.propagators,
            rank: g.rank,
            points: g.points.clone(),
            keys: g.keys.clone(),
            shifts: z(&g.shifts),
            masses: z(&g.masses),
            scales: z(&g.scales),
            s_matrix: z(&g.s_matrix),
            coefficients: z(&g.coefficients),
        })
        .collect()
}

/// Everything one call returns and reports, bit for bit (values as their
/// exact bits through `Debug` of the carrier's exact rational, reasons,
/// measures, counts; seconds are timings and left out).
fn fingerprint<T: Carrier + RealLike>(reduced: &Reduced<T>, backend: &mut V2Backends) -> Vec<String>
where
    V2Backends: V2Backend<T>,
{
    let mut out = Vec::new();
    let lanes = |outcomes: &[Vec<LaneOutcome<T>>], out: &mut Vec<String>| {
        for (g, group) in outcomes.iter().enumerate() {
            for (l, outcome) in group.iter().enumerate() {
                out.push(match outcome {
                    Ok(values) => format!(
                        "{g}/{l} ok {:?}",
                        values
                            .iter()
                            .map(|z| (exact_value(&z.re), exact_value(&z.im)))
                            .collect::<Vec<_>>()
                    ),
                    Err(reason) => format!("{g}/{l} err {reason}"),
                });
            }
        }
    };
    lanes(&reduced.0, &mut out);
    if let Some(check) = &reduced.1 {
        out.push("check".into());
        lanes(check, &mut out);
    }
    for m in V2Backend::<T>::take_lane_measures(backend) {
        out.push(format!(
            "measure {} {} {} {:?} {:x}",
            m.group,
            m.lane,
            m.check,
            m.measure.kind,
            m.measure.value.to_bits()
        ));
    }
    for (name, value) in V2Backend::<T>::take_statistics(backend).counts {
        out.push(format!("count {name} {value}"));
    }
    out
}

/// One call on a pool of `threads` threads (the executor's way: the call
/// runs inside the pool's `install`), twice on the same backend (its
/// engines kept), the fingerprints of both calls.
fn run<T: TypedBatch + Carrier + RealLike>(
    groups: &[FamilyLanes<T>],
    options: TirOptions,
    check: Option<ReductionCheck>,
    threads: usize,
) -> Vec<String>
where
    V2Backends: V2Backend<T>,
{
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()
        .unwrap();
    let mut backend = V2Backends::TiRust(Box::new(TirReductionBackend::new(options)));
    pool.install(|| {
        let mut all = Vec::new();
        for _ in 0..2 {
            V2Backend::<T>::begin(&mut backend);
            let reduced =
                V2Backend::<T>::reduce(&mut backend, groups, Poles::Split, check).unwrap();
            all.extend(fingerprint(&reduced, &mut backend));
        }
        all
    })
}

fn modes() -> Vec<(&'static str, TirOptions, Option<ReductionCheck>)> {
    let checked = TirOptions {
        unchecked: false,
        ..TirOptions::default()
    };
    let unchecked = TirOptions {
        unchecked: true,
        ..TirOptions::default()
    };
    let rotation = ReductionCheck {
        rescale: false,
        ..ReductionCheck::REVERSED
    };
    vec![
        ("unchecked", unchecked, None),
        ("unchecked, rotation check", unchecked, Some(rotation)),
        ("checked", checked, None),
        ("checked, rotation check", checked, Some(rotation)),
        (
            "checked, rescaled check",
            checked,
            Some(ReductionCheck::RESCALED),
        ),
        (
            "checked, no rotation copy",
            TirOptions {
                rotation_copy: false,
                ..checked
            },
            Some(rotation),
        ),
        (
            "checked, extended method choice",
            TirOptions {
                extended_method_choice: true,
                ..checked
            },
            Some(rotation),
        ),
    ]
}

fn invariant<T: TypedBatch + Carrier + RealLike>(groups: &[FamilyLanes<T>], carrier: &str)
where
    V2Backends: V2Backend<T>,
{
    for (mode, options, check) in modes() {
        let serial = run(groups, options, check, 1);
        assert!(
            serial.iter().any(|line| line.contains(" ok ")),
            "{carrier} {mode}"
        );
        for threads in [2, 4, 8, 16] {
            let parallel = run(groups, options, check, threads);
            assert_eq!(serial.len(), parallel.len(), "{carrier} {mode} {threads}");
            for (a, b) in serial.iter().zip(&parallel) {
                assert_eq!(a, b, "{carrier} {mode} at {threads} threads");
            }
        }
    }
}

/// The served and refused lanes of the fixture: the method choice and the
/// gate refusals are at work (binary64, checked, rotation check).
#[test]
fn the_fixture_exercises_the_method_choice() {
    let fingerprint = run(
        &groups(),
        TirOptions::default(),
        Some(ReductionCheck {
            rescale: false,
            ..ReductionCheck::REVERSED
        }),
        4,
    );
    let count = |name: &str| {
        fingerprint
            .iter()
            .find_map(|line| line.strip_prefix(&format!("count {name} ")))
            .map_or(0, |v| v.parse::<u64>().unwrap())
    };
    eprintln!(
        "{:?}",
        fingerprint
            .iter()
            .filter(|l| l.starts_with("count"))
            .collect::<Vec<_>>()
    );
    assert!(count("TIR gate refusals") > 0);
    assert!(count("TIR method-choice rows") > 0);
}

#[test]
fn binary64_does_not_depend_on_the_threads() {
    invariant(&groups(), "binary64");
}

#[test]
fn double_double_does_not_depend_on_the_threads() {
    invariant(&lift(&groups(), &DoubleFloat::from(0.)), "double-double");
}

#[test]
fn arbitrary_precision_does_not_depend_on_the_threads() {
    let _unlock = pyamplicol::unlock();
    // Fewer rows (MPFR is slow): the generic families up to five
    // propagators and the forward boxes at rank 4.
    let groups: Vec<_> = groups()
        .into_iter()
        .filter(|g| g.propagators <= 5 && g.rank <= 4)
        .collect();
    let zero = Float::with_val(Float::decimal_digits_to_bits(40.).unwrap(), 0);
    invariant(&lift(&groups, &zero), "arbitrary precision");
}

/// The rows of a call on one thread of a pool, off any pool, and on a pool
/// of several threads are the same (the serial path is the one-thread
/// pool's).
#[test]
fn off_a_pool_the_call_is_the_one_thread_call() {
    let groups = groups();
    let options = TirOptions::default();
    let check = Some(ReductionCheck::RESCALED);
    let mut backend = V2Backends::TiRust(Box::new(TirReductionBackend::new(options)));
    V2Backend::<f64>::begin(&mut backend);
    let reduced = V2Backend::<f64>::reduce(&mut backend, &groups, Poles::Split, check).unwrap();
    let mut off = fingerprint(&reduced, &mut backend);
    V2Backend::<f64>::begin(&mut backend);
    let reduced = V2Backend::<f64>::reduce(&mut backend, &groups, Poles::Split, check).unwrap();
    off.extend(fingerprint(&reduced, &mut backend));
    assert_eq!(off, run(&groups, options, check, 1));
    assert_eq!(off, run(&groups, options, check, 3));
}

/// A call on a pool of several threads reduces its slices on the
/// backend's engine and up to one more per other thread (kept for the next
/// call); on one thread on the backend's alone.
#[test]
fn several_threads_use_engines_of_their_own() {
    let groups = groups();
    for (threads, parallel) in [(1, false), (2, true), (8, true)] {
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build()
            .unwrap();
        let mut backend = TirReductionBackend::new(TirOptions::default());
        pool.install(|| backend.reduce(&groups, Poles::All, None).unwrap());
        let engines = backend.parallel_engines();
        assert_eq!(
            engines > 0,
            parallel,
            "{threads} threads: {engines} engines"
        );
        assert!(
            engines < threads.max(2),
            "{threads} threads: {engines} engines"
        );
    }
}

/// A nearly degenerate row's outcome does not depend on the rows reduced
/// before it, in the same call or in an earlier call on the same backend
/// (`v2_tir` module docs 'Threads': the workspaces are lane-independent, so
/// a slice boundary or an engine's history changes no bit). The fixture: an
/// exactly degenerate box (two equal external momenta, a vanishing Gram
/// determinant) and the same box moved by 1e-13, at ranks 2 and 4, checked
/// and unchecked. With the invariants supplied, these rows show no history
/// dependence even without lane independence; TIRust's own tests reproduce
/// the dependence its setting removes (`tests/parallel_engines.rs`).
#[test]
fn a_nearly_degenerate_row_does_not_depend_on_the_rows_before_it() {
    let box_at = |eps: f64| {
        vec![
            [-1., -1., 0., 0.],
            [0., -3., -1., 0.],
            [0., 0., 0., 0.],
            [1., -2., -1. + eps, 0.],
        ]
    };
    let masses = [0., 2., 0., 2.];
    for rank in [2, 4] {
        let mut rng = Lcg(7);
        let both = family(0, &[box_at(0.), box_at(1e-13)], &masses, rank, 2, &mut rng);
        // The two lanes of each box, as a family of their own at point 0.
        let part = |lanes: std::ops::Range<usize>| {
            let n = |per: usize| lanes.start * per..lanes.end * per;
            FamilyLanes {
                family: 0,
                propagators: 4,
                rank,
                points: vec![0; lanes.len()],
                keys: both.keys[lanes.clone()].to_vec(),
                shifts: both.shifts[n(16)].to_vec(),
                masses: both.masses[n(4)].to_vec(),
                scales: both.scales[n(1)].to_vec(),
                s_matrix: both.s_matrix[n(16)].to_vec(),
                coefficients: both.coefficients[n(ncoeff(rank))].to_vec(),
            }
        };
        let (exact, near) = (part(0..2), part(2..4));
        for unchecked in [true, false] {
            let options = TirOptions {
                unchecked,
                ..TirOptions::default()
            };
            let outcomes = |calls: &[&FamilyLanes<f64>]| {
                let mut backend = V2Backends::TiRust(Box::new(TirReductionBackend::new(options)));
                let mut last = Vec::new();
                for lanes in calls {
                    V2Backend::<f64>::begin(&mut backend);
                    let reduced = V2Backend::<f64>::reduce(
                        &mut backend,
                        std::slice::from_ref(*lanes),
                        Poles::Split,
                        None,
                    )
                    .unwrap();
                    last = reduced.0[0]
                        .iter()
                        .map(|outcome| match outcome {
                            Ok(values) => format!(
                                "ok {:?}",
                                values
                                    .iter()
                                    .map(|z| (z.re.to_bits(), z.im.to_bits()))
                                    .collect::<Vec<_>>()
                            ),
                            Err(reason) => format!("err {reason}"),
                        })
                        .collect::<Vec<_>>();
                }
                last
            };
            let alone = outcomes(&[&near]);
            let after_in_call = outcomes(&[&both]).split_off(2);
            let after_a_call = outcomes(&[&exact, &near]);
            let what = format!("rank {rank}, unchecked {unchecked}");
            assert_eq!(
                alone, after_in_call,
                "{what}: after the exact box in one call"
            );
            assert_eq!(alone, after_a_call, "{what}: after a call of the exact box");
        }
    }
}
