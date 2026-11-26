// SPDX-License-Identifier: 0BSD

//! Parallel reduction of one call's lanes, independent of the backend:
//! cutting the lanes into slices, a pool of per-worker engines on the
//! calling pool, and the merge of the slices' results in slice order.
//!
//! **Where it runs.** [`workers`] is the number of threads of the pool the
//! caller runs on, or 1 when the caller is not on a pool worker. The
//! executor runs every reduction inside its own pool
//! (`V2Executor::install`), so the parallel region below runs on the
//! executor's workers and respects its `threads` bound; a caller outside any
//! pool (the Python reference path, a test thread) gets 1 worker and stays
//! serial. Nothing here touches rayon's global pool.
//!
//! **One thread is the serial path.** With one worker a backend keeps its
//! serial code (no slicing, no pool, no allocation or lock of this module).
//!
//! **Slices.** A backend lays a call's lanes out in an order in which the
//! lanes of one point (or any other affinity: lanes that share cached work)
//! are contiguous, and [`cut`] cuts that order into slices of at most
//! [`slice_size`] lanes, on affinity boundaries where the slice is at least
//! half full. The size follows the work and the pool: about
//! [`SLICES_PER_WORKER`] slices per worker (dynamic scheduling evens out
//! unequal lane costs), at most the backend's own call size.
//!
//! **Engines.** [`EnginePool::run`] reduces every slice on one engine per
//! task: the caller's own engine is the first, the others are kept in the
//! pool between calls, made on first use by the caller's `make` and brought
//! to the call's settings by its `follow` before each call. An engine is
//! used by one slice at a time and every slice runs start to finish on one
//! thread (a backend's thread-local records, taken right after its
//! evaluation, stay the slice's), so an engine needs to be `Send` only.
//!
//! **Determinism.** The results come back in slice order, whichever worker
//! reduced a slice and in whichever order: a backend whose lanes are
//! independent of the other lanes of their call gets every value bit for bit
//! at any number of threads, and merges its order-dependent records
//! (statistics, rescued and uncertified lanes) from the results in slice
//! order ([`merge_counts`], [`concat`]). A failure is the failure of the
//! lowest failing slice: every slice below a failing one is still reduced, so
//! the error does not depend on the scheduling.

use rayon::prelude::*;
use std::ops::Range;
use std::sync::atomic::{AtomicUsize, Ordering};

/// Slices per worker a call is cut into (at most): enough for the dynamic
/// scheduling to even out unequal lane costs, few enough that a slice keeps
/// the per-call costs (gathering, engine set-up, shared masters) small.
pub const SLICES_PER_WORKER: usize = 4;

/// The workers of a parallel region started here: the threads of the
/// current pool when called on one of its workers, else 1.
pub fn workers() -> usize {
    match rayon::current_thread_index() {
        Some(_) => rayon::current_num_threads().max(1),
        None => 1,
    }
}

/// The slice size of a call of `lanes` lanes on `workers` workers: about
/// [`SLICES_PER_WORKER`] slices per worker, at most `cap` lanes (the
/// backend's own call size), at least one lane.
pub fn slice_size(lanes: usize, workers: usize, cap: usize) -> usize {
    let slices = SLICES_PER_WORKER * workers.max(1);
    lanes.div_ceil(slices).clamp(1, cap.max(1))
}

/// Cut positions `0..affinity.len()` of an order into contiguous slices of
/// at most `size` positions. A slice ends where the affinity changes once it
/// holds at least half of `size`; a run of one affinity longer than the
/// space left is cut inside. Every position is in exactly one slice, in
/// order.
pub fn cut<K: PartialEq>(affinity: &[K], size: usize) -> Vec<Range<usize>> {
    let size = size.max(1);
    let len = affinity.len();
    let mut slices = Vec::with_capacity(len.div_ceil(size));
    let mut start = 0;
    let mut position = 0;
    while position < len {
        // The run of equal affinity at `position`.
        let mut end = position + 1;
        while end < len && affinity[end] == affinity[position] {
            end += 1;
        }
        let mut run = position;
        while run < end {
            let held = run - start;
            let space = size - held;
            if end - run <= space {
                run = end;
            } else if held > 0 && 2 * held >= size {
                // Close the slice on the affinity boundary at `run`.
                slices.push(start..run);
                start = run;
            } else {
                run += space;
                slices.push(start..run);
                start = run;
            }
        }
        position = end;
        if position - start == size {
            slices.push(start..position);
            start = position;
        }
    }
    if start < len {
        slices.push(start..len);
    }
    slices
}

/// Per-worker engines kept between calls ([`Self::run`]); the caller's own
/// engine is not in the pool.
pub struct EnginePool<E> {
    forks: Vec<Option<E>>,
}

impl<E> Default for EnginePool<E> {
    fn default() -> Self {
        Self { forks: Vec::new() }
    }
}

enum Slot<'a, E> {
    Main(&'a mut E),
    Fork(&'a mut Option<E>),
}

impl<E: Send> EnginePool<E> {
    pub fn new() -> Self {
        Self::default()
    }

    /// The engines made so far (not the caller's): their caches to clear,
    /// their counters to take.
    pub fn engines_mut(&mut self) -> impl Iterator<Item = &mut E> {
        self.forks.iter_mut().flatten()
    }

    /// The engines made so far (not the caller's).
    pub fn engines(&self) -> impl Iterator<Item = &E> {
        self.forks.iter().flatten()
    }

    /// Take every engine made so far out of the pool (it is empty after):
    /// a backend whose copies must not outlive a call folds their counters
    /// into its own engine and drops them.
    pub fn drain(&mut self) -> impl Iterator<Item = E> + '_ {
        self.forks.drain(..).flatten()
    }

    /// Reduce every slice with `reduce` on up to [`workers`] engines in
    /// parallel on the current pool: `main` and engines of the pool, made
    /// by `make` on first use and brought to the call's settings by `follow`
    /// before their first slice of the call. The results in slice order;
    /// the error of the lowest failing slice (every slice below it reduced).
    /// With one worker or one slice, every slice is reduced on `main` in
    /// order on the calling thread.
    pub fn run<S, R, Err>(
        &mut self,
        main: &mut E,
        slices: &[S],
        make: impl Fn() -> Result<E, Err> + Sync,
        follow: impl Fn(&mut E) + Sync,
        reduce: impl Fn(&mut E, &S) -> Result<R, Err> + Sync,
    ) -> Result<Vec<R>, Err>
    where
        S: Sync,
        R: Send,
        Err: Send,
    {
        self.run_ordered(main, slices, None, make, follow, reduce)
    }

    /// [`Self::run`] with the slices taken up in the order `schedule` (a
    /// permutation of the slice indices; `None`: slice order), for example
    /// the most expensive first. The results, and which failure is
    /// returned, do not depend on it.
    pub fn run_ordered<S, R, Err>(
        &mut self,
        main: &mut E,
        slices: &[S],
        schedule: Option<&[usize]>,
        make: impl Fn() -> Result<E, Err> + Sync,
        follow: impl Fn(&mut E) + Sync,
        reduce: impl Fn(&mut E, &S) -> Result<R, Err> + Sync,
    ) -> Result<Vec<R>, Err>
    where
        S: Sync,
        R: Send,
        Err: Send,
    {
        if let Some(schedule) = schedule {
            assert_eq!(schedule.len(), slices.len(), "a schedule of every slice");
        }
        let tasks = workers().min(slices.len());
        if tasks <= 1 {
            return slices.iter().map(|slice| reduce(main, slice)).collect();
        }
        if self.forks.len() < tasks - 1 {
            self.forks.resize_with(tasks - 1, || None);
        }
        let mut slots = Vec::with_capacity(tasks);
        slots.push(Slot::Main(main));
        slots.extend(self.forks[..tasks - 1].iter_mut().map(Slot::Fork));
        let next = AtomicUsize::new(0);
        // The lowest failing slice so far: slices above it are skipped,
        // slices below it are still reduced.
        let failed = AtomicUsize::new(usize::MAX);
        let parts: Vec<Vec<(usize, Result<R, Err>)>> = slots
            .into_par_iter()
            .map(|slot| {
                let mut done = Vec::new();
                let mut slot = Some(slot);
                let mut engine: Option<&mut E> = None;
                loop {
                    let taken = next.fetch_add(1, Ordering::Relaxed);
                    if taken >= slices.len() {
                        break;
                    }
                    let index = schedule.map_or(taken, |schedule| schedule[taken]);
                    if index > failed.load(Ordering::Relaxed) {
                        continue;
                    }
                    if engine.is_none() {
                        let slot = slot.take().expect("a task's slot is taken once");
                        match engine_of(slot, &make, &follow) {
                            Ok(got) => engine = Some(got),
                            Err(error) => {
                                failed.fetch_min(index, Ordering::Relaxed);
                                done.push((index, Err(error)));
                                // This task has no engine: the others
                                // reduce the remaining slices.
                                break;
                            }
                        }
                    }
                    let engine = engine.as_deref_mut().expect("the task's engine");
                    let result = reduce(engine, &slices[index]);
                    if result.is_err() {
                        failed.fetch_min(index, Ordering::Relaxed);
                    }
                    done.push((index, result));
                }
                done
            })
            .collect();
        let mut results: Vec<Option<Result<R, Err>>> = (0..slices.len()).map(|_| None).collect();
        for (index, result) in parts.into_iter().flatten() {
            results[index] = Some(result);
        }
        let failed = failed.into_inner();
        let mut out = Vec::with_capacity(slices.len());
        for (index, result) in results.into_iter().enumerate() {
            match result {
                Some(Ok(value)) if index < failed => out.push(value),
                Some(Err(error)) if index == failed => return Err(error),
                // A task without an engine leaves its slice to the others;
                // a slice skipped above the failure is not needed.
                _ if index > failed => break,
                Some(Ok(_)) | Some(Err(_)) | None => {
                    unreachable!("a slice below the lowest failure was not reduced")
                }
            }
        }
        Ok(out)
    }
}

/// A task's engine: the caller's, or a copy of the pool, made on first use
/// or brought to the call's settings.
fn engine_of<'a, E, Err>(
    slot: Slot<'a, E>,
    make: &impl Fn() -> Result<E, Err>,
    follow: &impl Fn(&mut E),
) -> Result<&'a mut E, Err> {
    match slot {
        Slot::Main(main) => Ok(main),
        Slot::Fork(fork) => {
            match fork.as_mut() {
                Some(copy) => follow(copy),
                None => *fork = Some(make()?),
            }
            Ok(fork.as_mut().expect("the copy was made"))
        }
    }
}

/// Named counters of several slices summed per name, the names in the
/// order of their first appearance in slice order (sums of integers do not
/// depend on the order).
pub fn merge_counts<'a, N: PartialEq + Copy + 'a>(
    parts: impl IntoIterator<Item = &'a [(N, u64)]>,
) -> Vec<(N, u64)> {
    let mut out: Vec<(N, u64)> = Vec::new();
    for part in parts {
        for &(name, value) in part {
            match out.iter_mut().find(|(n, _)| *n == name) {
                Some((_, sum)) => *sum += value,
                None => out.push((name, value)),
            }
        }
    }
    out
}

/// Per-slice lists concatenated in slice order, each item mapped with its
/// slice's index (a slice-local lane index to the call's).
pub fn concat<X, Y>(
    parts: impl IntoIterator<Item = Vec<X>>,
    mut map: impl FnMut(usize, X) -> Y,
) -> Vec<Y> {
    parts
        .into_iter()
        .enumerate()
        .flat_map(|(slice, items)| items.into_iter().map(move |item| (slice, item)))
        .map(|(slice, item)| map(slice, item))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pool(threads: usize) -> rayon::ThreadPool {
        rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build()
            .unwrap()
    }

    #[test]
    fn slices_cover_every_position_once_and_respect_the_size() {
        let affinity: Vec<u32> = [5, 5, 5, 1, 1, 7, 7, 7, 7, 7, 7, 7, 2, 3, 3, 3]
            .into_iter()
            .collect();
        for size in 1..=20 {
            let slices = cut(&affinity, size);
            let mut next = 0;
            for slice in &slices {
                assert_eq!(slice.start, next, "contiguous, in order");
                assert!(!slice.is_empty() && slice.len() <= size);
                next = slice.end;
            }
            assert_eq!(next, affinity.len());
        }
        assert!(cut::<u32>(&[], 4).is_empty());
    }

    #[test]
    fn slices_end_on_affinity_boundaries_where_half_full() {
        // Points of 3, 2, 7, 1 and 3 lanes, slices of at most 4.
        let affinity = [0, 0, 0, 1, 1, 2, 2, 2, 2, 2, 2, 2, 3, 4, 4, 4];
        let slices = cut(&affinity, 4);
        // The one-lane point fits the slice holding the tail of the long one.
        assert_eq!(slices, vec![0..3, 3..5, 5..9, 9..13, 13..16]);
        // A slice less than half full takes the next point's lanes.
        let affinity = [0, 1, 1, 1, 1, 1];
        assert_eq!(cut(&affinity, 4), vec![0..4, 4..6]);
        // Equal affinity everywhere: plain chunks.
        assert_eq!(cut(&[9; 10], 4), vec![0..4, 4..8, 8..10]);
    }

    #[test]
    fn the_slice_size_follows_the_work_and_the_pool() {
        assert_eq!(slice_size(40_448, 8, 1024), 1024);
        assert_eq!(slice_size(2_528, 8, 1024), 79);
        assert_eq!(slice_size(2_528, 1, 1024), 632);
        assert_eq!(slice_size(3, 16, 1024), 1);
        assert_eq!(slice_size(0, 4, 1024), 1);
    }

    /// An engine that records the slices it reduced.
    struct Engine {
        id: usize,
        seen: Vec<usize>,
        setting: u32,
    }

    fn reduce_all(
        engines: &mut EnginePool<Engine>,
        main: &mut Engine,
        slices: usize,
        made: &AtomicUsize,
        fail: &[usize],
        setting: u32,
    ) -> Result<Vec<(usize, u32)>, String> {
        let slices: Vec<usize> = (0..slices).collect();
        engines.run(
            main,
            &slices,
            || {
                let id = 1 + made.fetch_add(1, Ordering::Relaxed);
                Ok(Engine {
                    id,
                    seen: Vec::new(),
                    setting,
                })
            },
            |engine| engine.setting = setting,
            |engine, &slice| {
                // Uneven work, so that the workers interleave.
                let mut x = 0u64;
                for k in 0..(1000 * (slice % 7) as u64) {
                    x = x.wrapping_mul(31).wrapping_add(k);
                }
                std::hint::black_box(x);
                engine.seen.push(slice);
                if fail.contains(&slice) {
                    Err(format!("slice {slice}"))
                } else {
                    Ok((slice * slice, engine.setting))
                }
            },
        )
    }

    #[test]
    fn results_come_back_in_slice_order_on_any_pool() {
        for threads in [1, 2, 3, 8, 16] {
            let pool = pool(threads);
            pool.install(|| {
                assert_eq!(workers(), threads);
                let mut engines = EnginePool::new();
                let mut main = Engine {
                    id: 0,
                    seen: Vec::new(),
                    setting: 7,
                };
                let made = AtomicUsize::new(0);
                // More slices than workers, several calls on the same pool.
                for (call, setting) in [7, 9].into_iter().enumerate() {
                    main.setting = setting;
                    let out = reduce_all(&mut engines, &mut main, 37, &made, &[], setting)
                        .expect("no failure");
                    let want: Vec<_> = (0..37).map(|s| (s * s, setting)).collect();
                    assert_eq!(out, want, "{threads} threads, call {call}");
                }
                // Every slice of every call reduced exactly once, on one engine.
                let mut seen: Vec<usize> = main.seen.clone();
                for engine in engines.engines() {
                    assert!(engine.id >= 1 && engine.id < threads);
                    seen.extend(&engine.seen);
                }
                seen.sort_unstable();
                let mut want: Vec<usize> = (0..37).chain(0..37).collect();
                want.sort_unstable();
                assert_eq!(seen, want);
                // Engines made once, at most one per extra worker.
                assert!(made.load(Ordering::Relaxed) < threads.max(2));
                assert_eq!(engines.engines().count(), made.load(Ordering::Relaxed));
            });
        }
    }

    #[test]
    fn one_worker_reduces_every_slice_on_the_callers_engine_in_order() {
        let mut engines = EnginePool::new();
        let mut main = Engine {
            id: 0,
            seen: Vec::new(),
            setting: 1,
        };
        let made = AtomicUsize::new(0);
        // Not on a pool worker: one worker.
        assert_eq!(workers(), 1);
        let out = reduce_all(&mut engines, &mut main, 5, &made, &[], 1).unwrap();
        assert_eq!(out.len(), 5);
        assert_eq!(main.seen, vec![0, 1, 2, 3, 4]);
        assert_eq!(made.load(Ordering::Relaxed), 0);
        // A one-thread pool alike.
        pool(1).install(|| {
            let out = reduce_all(&mut engines, &mut main, 3, &made, &[], 1).unwrap();
            assert_eq!(out.len(), 3);
        });
        assert_eq!(main.seen, vec![0, 1, 2, 3, 4, 0, 1, 2]);
        assert_eq!(made.load(Ordering::Relaxed), 0);
    }

    #[test]
    fn a_schedule_changes_neither_the_results_nor_the_failure() {
        for threads in [1, 2, 4, 8] {
            pool(threads).install(|| {
                let mut engines: EnginePool<Engine> = EnginePool::new();
                let mut main = Engine {
                    id: 0,
                    seen: Vec::new(),
                    setting: 0,
                };
                let slices: Vec<usize> = (0..23).collect();
                let schedule: Vec<usize> = (0..23).rev().collect();
                let make = || -> Result<Engine, String> {
                    Ok(Engine {
                        id: 1,
                        seen: Vec::new(),
                        setting: 0,
                    })
                };
                let out = engines
                    .run_ordered(
                        &mut main,
                        &slices,
                        Some(&schedule),
                        make,
                        |_| {},
                        |_, &s| Ok::<_, String>(3 * s),
                    )
                    .unwrap();
                assert_eq!(out, (0..23).map(|s| 3 * s).collect::<Vec<_>>());
                let error = engines
                    .run_ordered(
                        &mut main,
                        &slices,
                        Some(&schedule),
                        make,
                        |_| {},
                        |_, &s| {
                            if s == 4 || s == 19 {
                                Err(format!("slice {s}"))
                            } else {
                                Ok(s)
                            }
                        },
                    )
                    .unwrap_err();
                assert_eq!(error, "slice 4", "{threads} threads");
            });
        }
    }

    #[test]
    fn the_error_is_the_lowest_failing_slices_on_any_pool() {
        for threads in [1, 2, 4, 8] {
            pool(threads).install(|| {
                let mut engines = EnginePool::new();
                let mut main = Engine {
                    id: 0,
                    seen: Vec::new(),
                    setting: 0,
                };
                let made = AtomicUsize::new(0);
                for _ in 0..5 {
                    let error = reduce_all(&mut engines, &mut main, 40, &made, &[33, 11, 30], 0)
                        .unwrap_err();
                    assert_eq!(error, "slice 11", "{threads} threads");
                }
            });
        }
    }

    #[test]
    fn counts_and_lists_merge_in_slice_order() {
        let a: Vec<(&str, u64)> = vec![("x", 1), ("y", 2)];
        let b: Vec<(&str, u64)> = vec![("z", 5), ("x", 3)];
        assert_eq!(
            merge_counts([a.as_slice(), b.as_slice()]),
            vec![("x", 4), ("y", 2), ("z", 5)]
        );
        let lists = vec![vec![0usize, 2], vec![], vec![1]];
        let offsets = [0usize, 10, 20];
        assert_eq!(
            concat(lists, |slice, lane| offsets[slice] + lane),
            vec![0, 2, 21]
        );
    }
}
