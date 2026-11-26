// SPDX-License-Identifier: 0BSD

//! The TIR backend's parallel reduction keeps per-slice state proportional
//! to what a slice touches (`v2_tir` module docs 'Threads'): one rank-six
//! hexagon next to thousands of rank-zero tadpole groups (one costly row,
//! many cheap ones: the shape that cut a call into one-row slices) needs
//! about the serial reduction's memory on two workers, and its memory grows
//! linearly with the number of groups. Peak heap bytes of the call are
//! measured with a counting allocator (this test binary only).
#![cfg(feature = "tir")]

use ninjars::fast::tensor_layout::ncoeff;
use rusticol_core::loop_execution::v2::{FamilyLanes, LaneKey, Poles};
use rusticol_core::loop_v2::retest::ReductionCheck;
use rusticol_loop_reduction::v2_tir::{TirOptions, TirReductionBackend};
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicUsize, Ordering};
use symbolica::domains::float::Complex;

type C = Complex<f64>;

/// The system allocator, counting the bytes in use and their peak.
struct Counting;

static IN_USE: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);

unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let pointer = unsafe { System.alloc(layout) };
        if !pointer.is_null() {
            let now = IN_USE.fetch_add(layout.size(), Ordering::Relaxed) + layout.size();
            PEAK.fetch_max(now, Ordering::Relaxed);
        }
        pointer
    }

    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        unsafe { System.dealloc(pointer, layout) };
        IN_USE.fetch_sub(layout.size(), Ordering::Relaxed);
    }

    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let moved = unsafe { System.realloc(pointer, layout, size) };
        if !moved.is_null() {
            if size >= layout.size() {
                let now = IN_USE.fetch_add(size - layout.size(), Ordering::Relaxed)
                    + (size - layout.size());
                PEAK.fetch_max(now, Ordering::Relaxed);
            } else {
                IN_USE.fetch_sub(layout.size() - size, Ordering::Relaxed);
            }
        }
        moved
    }
}

#[global_allocator]
static ALLOCATOR: Counting = Counting;

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

/// One lane of a family of `shifts.len()` propagators of squared masses
/// `masses` at rank `rank`.
fn group(
    family: usize,
    shifts: &[[f64; 4]],
    masses: &[f64],
    rank: usize,
    rng: &mut Lcg,
) -> FamilyLanes<f64> {
    let n = shifts.len();
    let mut s_matrix = Vec::with_capacity(n * n);
    for i in 0..n {
        for j in 0..n {
            let d: [f64; 4] = std::array::from_fn(|mu| shifts[i][mu] - shifts[j][mu]);
            s_matrix.push(C::new(
                d[0] * d[0] - d[1] * d[1] - d[2] * d[2] - d[3] * d[3],
                0.,
            ));
        }
    }
    FamilyLanes {
        family,
        propagators: n,
        rank,
        points: vec![0],
        keys: vec![LaneKey {
            family,
            order: 0,
            column: 0,
        }],
        shifts: shifts.iter().flatten().map(|&x| C::new(x, 0.)).collect(),
        masses: masses.iter().map(|&m| C::new(m, 0.)).collect(),
        scales: vec![C::new(91.188 * 91.188, 0.)],
        s_matrix,
        coefficients: (0..ncoeff(rank))
            .map(|_| C::new(rng.next(), rng.next()))
            .collect(),
    }
}

/// One rank-six hexagon (generic massive kinematics) and `tadpoles`
/// rank-zero tadpole groups of distinct masses, the hexagon first or (with
/// `last`) last.
fn call(tadpoles: usize, last: bool) -> Vec<FamilyLanes<f64>> {
    let mut rng = Lcg(3);
    let mut shifts = vec![[0f64; 4]];
    for _ in 1..6 {
        let last = *shifts.last().unwrap();
        let p = [
            400. + 150. * rng.next(),
            200. * rng.next(),
            200. * rng.next(),
            200. * rng.next(),
        ];
        shifts.push(std::array::from_fn(|mu| last[mu] + p[mu]));
    }
    let hexagon = group(0, &shifts, &[173. * 173.; 6], 6, &mut rng);
    let mut groups: Vec<FamilyLanes<f64>> = (0..tadpoles)
        .map(|k| {
            let mass = 100. + k as f64;
            group(1 + k, &[[0.; 4]], &[mass * mass], 0, &mut rng)
        })
        .collect();
    if last {
        groups.push(hexagon);
    } else {
        groups.insert(0, hexagon);
    }
    for (index, g) in groups.iter_mut().enumerate() {
        g.family = index;
        g.keys[0].family = index;
    }
    groups
}

/// The peak heap bytes of one reduction of `groups` above what was in use
/// before it, on a pool of `threads` threads (a fresh backend each time),
/// and the outcomes.
fn peak(
    groups: &[FamilyLanes<f64>],
    threads: usize,
    check: Option<ReductionCheck>,
) -> (usize, String) {
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()
        .unwrap();
    let options = TirOptions {
        method_choice: false,
        ..TirOptions::default()
    };
    let mut backend = TirReductionBackend::new(options);
    // The plans and the pool's threads before the measurement.
    let hexagon: Vec<FamilyLanes<f64>> = groups
        .iter()
        .filter(|g| g.propagators == 6)
        .map(|g| FamilyLanes {
            family: 0,
            propagators: g.propagators,
            rank: g.rank,
            points: g.points.clone(),
            keys: vec![LaneKey {
                family: 0,
                order: 0,
                column: 0,
            }],
            shifts: g.shifts.clone(),
            masses: g.masses.clone(),
            scales: g.scales.clone(),
            s_matrix: g.s_matrix.clone(),
            coefficients: g.coefficients.clone(),
        })
        .collect();
    pool.install(|| backend.reduce(&hexagon, Poles::All, check).unwrap());
    let base = IN_USE.load(Ordering::Relaxed);
    PEAK.store(base, Ordering::Relaxed);
    let started = std::time::Instant::now();
    let reduced = pool.install(|| backend.reduce(groups, Poles::All, check).unwrap());
    let seconds = started.elapsed().as_secs_f64();
    let peak = PEAK.load(Ordering::Relaxed) - base;
    eprintln!("  {threads} thread(s): {:.1} ms", seconds * 1e3);
    let served = reduced.0.iter().flatten().filter(|o| o.is_ok()).count();
    assert!(
        served > groups.len() / 2,
        "the reduction serves the tadpoles"
    );
    (peak, format!("{reduced:?}"))
}

/// The reviewer's case: one rank-six hexagon and thousands of rank-zero
/// tadpole groups, two workers, the method choice off. Bound: on two
/// workers a call needs at most twice the serial call's heap plus 16 MB
/// (the second worker's workspaces of the hexagon plan and its slices'
/// moments), at both sizes, and its growth from 2,000 to 4,000 groups is at
/// most twice the serial growth plus 4 MB (linear, not quadratic: the
/// quadratic directory grew about fourfold). The outcomes are those of the
/// serial call.
#[test]
fn many_small_groups_next_to_one_costly_row_need_the_serial_memory() {
    let rotation = Some(ReductionCheck {
        rescale: false,
        ..ReductionCheck::REVERSED
    });
    // The reviewer's form: the hexagon last, the reversed check (TIRust's
    // rotation copy); and the hexagon first, without and with the rotation.
    for (last, check) in [
        (true, Some(ReductionCheck::REVERSED)),
        (false, None),
        (false, rotation),
    ] {
        let mut measured = Vec::new();
        for tadpoles in [1999, 3999] {
            let groups = call(tadpoles, last);
            let (serial, one) = peak(&groups, 1, check);
            let (parallel, two) = peak(&groups, 2, check);
            assert_eq!(one, two, "{tadpoles} tadpoles: outcomes at two workers");
            eprintln!(
                "hexagon last {last}, check {}: {} groups: peak heap serial {:.1} MB, two workers {:.1} MB",
                check.is_some(),
                groups.len(),
                serial as f64 / 1e6,
                parallel as f64 / 1e6
            );
            assert!(
                parallel <= 2 * serial + 16_000_000,
                "{} groups: {parallel} bytes on two workers against {serial} serial",
                groups.len()
            );
            measured.push((serial, parallel));
        }
        let [(s1, p1), (s2, p2)] = [measured[0], measured[1]];
        assert!(
            p2.saturating_sub(p1) <= 2 * s2.saturating_sub(s1) + 4_000_000,
            "growth 2,000 -> 4,000 groups: {p1} -> {p2} bytes on two workers, {s1} -> {s2} serial"
        );
    }
}
