// SPDX-License-Identifier: 0BSD

//! What one worker of the TIR backend's parallel reduction keeps in memory
//! (`v2_tir` module docs 'Threads'): a probe, run by hand
//! (`cargo test --test tir_memory -- --ignored --nocapture`), on families of
//! one to six propagators at massless legs (the lightlike pinches of a
//! gluon amplitude) and every rank up to N.
#![cfg(feature = "tir")]

use ninjars::fast::tensor_layout::ncoeff;
use rusticol_core::loop_execution::v2::{FamilyLanes, LaneKey, Poles};
use rusticol_core::loop_v2::dress::{Carrier, cast, exact_value};
use rusticol_loop_reduction::v2_tir::{TirOptions, TirReductionBackend};
use symbolica::domains::float::{Complex, DoubleFloat};

type C = Complex<f64>;

unsafe extern "C" {
    fn malloc_trim(pad: usize) -> i32;
}

/// Resident memory in MB after returning free heap memory to the system.
fn rss() -> f64 {
    unsafe { malloc_trim(0) };
    let statm = std::fs::read_to_string("/proc/self/statm").unwrap();
    let pages: f64 = statm.split_whitespace().nth(1).unwrap().parse().unwrap();
    pages * 4096. / 1e6
}

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

/// `points` points of a family of `n` massless propagators with massless
/// legs (adjacent invariants exactly zero), `columns` lanes per point at
/// rank `rank`.
fn massless(
    family: usize,
    n: usize,
    rank: usize,
    points: usize,
    columns: usize,
    rng: &mut Lcg,
) -> FamilyLanes<f64> {
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
    for p in 0..points {
        let mut shifts = vec![[0f64; 4]];
        for _ in 1..n {
            let v = [300. * rng.next(), 300. * rng.next(), 300. * rng.next()];
            let e = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt();
            let last = *shifts.last().unwrap();
            shifts.push([last[0] + e, last[1] + v[0], last[2] + v[1], last[3] + v[2]]);
        }
        for column in 0..columns {
            out.points.push(p);
            out.keys.push(LaneKey {
                family,
                order: 0,
                column,
            });
            for v in &shifts {
                out.shifts.extend(v.iter().map(|&x| C::new(x, 0.)));
            }
            out.masses.extend((0..n).map(|_| C::new(0., 0.)));
            out.scales.push(C::new(91.188 * 91.188, 0.));
            for i in 0..n {
                for j in 0..n {
                    let adjacent = (i + 1) % n == j || (j + 1) % n == i;
                    let d: [f64; 4] = std::array::from_fn(|mu| shifts[i][mu] - shifts[j][mu]);
                    let s = d[0] * d[0] - d[1] * d[1] - d[2] * d[2] - d[3] * d[3];
                    out.s_matrix
                        .push(C::new(if adjacent || i == j { 0. } else { s }, 0.));
                }
            }
            for _ in 0..ncoeff(rank) {
                out.coefficients.push(C::new(rng.next(), rng.next()));
            }
        }
    }
    out
}

/// Families of 2 to 6 propagators at ranks N - 1 and N, 16 points each.
fn gluon_like() -> Vec<FamilyLanes<f64>> {
    let mut rng = Lcg(7);
    let mut out = Vec::new();
    for n in 2..=6usize {
        for rank in [n - 1, n] {
            for _ in 0..3 {
                let index = out.len();
                out.push(massless(index, n, rank, 16, 1, &mut rng));
            }
        }
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

fn pool(threads: usize) -> rayon::ThreadPool {
    rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()
        .unwrap()
}

/// The memory of a backend's plans, of its own engine after a call on one
/// thread and of the other workers' engines after a call on 8 threads, per
/// carrier and option set.
fn probe<T: rusticol_loop_reduction::v2_tir::TirCarrier>(
    label: &str,
    groups: &[FamilyLanes<T>],
    options: TirOptions,
) where
    Complex<T>: symbolica::evaluate::EvaluationDomain,
{
    let histogram: Vec<(usize, usize)> = (1..=6).map(|n| (n, n)).collect();
    let (one, eight) = (pool(1), pool(8));
    let start = rss();
    let mut backend =
        TirReductionBackend::with_histogram(histogram.iter().copied(), 53, options).unwrap();
    let plans = rss();
    one.install(|| backend.reduce(groups, Poles::All, None).unwrap());
    let main = rss();
    eight.install(|| backend.reduce(groups, Poles::All, None).unwrap());
    let workers = rss();
    eight.install(|| backend.reduce(groups, Poles::All, None).unwrap());
    let again = rss();
    let forks = backend.parallel_engines();
    drop(backend);
    let end = rss();
    // TIRust's per-thread caches (its small-Gram expansions' auxiliary
    // executors and tables) go with the pools' threads.
    drop(eight);
    let threads8 = rss();
    drop(one);
    let threads1 = rss();
    println!(
        "{label}: plans {:.1} MB, own engine {:.1} MB, {forks} other engines {:.1} MB ({:.1} MB each; \
         after a second 8-thread call {:.1} MB); left after dropping the backend {:.1} MB, \
         then the 8-thread pool {:.1} MB, then the 1-thread pool {:.1} MB",
        plans - start,
        main - plans,
        workers - main,
        (workers - main) / forks.max(1) as f64,
        again - main,
        end - start,
        threads8 - start,
        threads1 - start
    );
}

#[test]
#[ignore = "a measurement: run by hand with --nocapture"]
fn memory_of_a_worker() {
    let groups = gluon_like();
    let checked = TirOptions {
        unchecked: false,
        ..TirOptions::default()
    };
    let unchecked = TirOptions {
        unchecked: true,
        ..TirOptions::default()
    };
    probe("binary64 unchecked", &groups, unchecked);
    probe("binary64 checked", &groups, checked);
    probe(
        "binary64 checked, no method choice",
        &groups,
        TirOptions {
            method_choice: false,
            ..checked
        },
    );
    let dd = lift(&groups, &DoubleFloat::from(0.));
    probe("double-double checked", &dd, checked);
}

/// The memory one thread keeps after reducing the families of one
/// (propagators, rank) only: the engine's workspaces and TIRust's caches of
/// that thread, per plan.
#[test]
#[ignore = "a measurement: run by hand with --nocapture"]
fn memory_per_plan() {
    let groups = gluon_like();
    for unchecked in [true, false] {
        for n in 2..=6usize {
            for rank in [n - 1, n] {
                let part: Vec<FamilyLanes<f64>> = groups
                    .iter()
                    .filter(|g| g.propagators == n && g.rank == rank)
                    .map(|g| FamilyLanes {
                        family: g.family,
                        propagators: g.propagators,
                        rank: g.rank,
                        points: g.points.clone(),
                        keys: g.keys.clone(),
                        shifts: g.shifts.clone(),
                        masses: g.masses.clone(),
                        scales: g.scales.clone(),
                        s_matrix: g.s_matrix.clone(),
                        coefficients: g.coefficients.clone(),
                    })
                    .collect();
                let one = pool(1);
                let start = rss();
                let mut backend = TirReductionBackend::new(TirOptions {
                    unchecked,
                    ..TirOptions::default()
                });
                let statistics = one.install(|| {
                    backend.reduce(&part, Poles::All, None).unwrap();
                    backend.take_statistics()
                });
                let kept = rss();
                drop(backend);
                let engine = kept - rss();
                let refused = statistics
                    .counts
                    .iter()
                    .find(|(k, _)| *k == "TIR gate refusals")
                    .map_or(0, |(_, v)| *v);
                println!(
                    "unchecked={unchecked} n={n} rank={rank}: {:.1} MB kept ({engine:.1} MB in the engine, \
                     the rest in the thread), {refused} gate refusals of {} rows",
                    kept - start,
                    part.iter().map(|g| g.keys.len()).sum::<usize>()
                );
                drop(one);
            }
        }
    }
}
