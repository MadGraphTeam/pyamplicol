// SPDX-License-Identifier: 0BSD

//! The parts of the public API the history harness uses beyond the serial
//! reducer's (`reduce_at`'s point labels, worker pools, `built_templates`),
//! kept apart so that the same histories can be replayed on a build without
//! them (a serial version of this file) and their serial records compared.
use rusticol_loop_reduction::runtime::{
    FamilyGroup, GroupRefinementSource, ReduceOptions, V2Output, V2Reducer,
};

/// The API takes point labels.
pub const LABELS: bool = true;

/// `f` on a pool of `workers` threads, unlocked as the executor's (`None`:
/// on the calling thread, the serial reduction).
pub fn run<R: Send>(workers: Option<usize>, f: impl FnOnce() -> R + Send) -> R {
    match workers {
        None => f(),
        Some(threads) => rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .start_handler(|_| pyamplicol::unlock_thread())
            .build()
            .unwrap()
            .install(f),
    }
}

pub fn reduce(
    reducer: &mut V2Reducer,
    groups: &[FamilyGroup<'_>],
    labels: Option<&[&[usize]]>,
    source: Option<&dyn GroupRefinementSource>,
    options: ReduceOptions,
) -> rusticol_loop_reduction::runtime::ExecutionResult<V2Output> {
    reducer.reduce_at(groups, labels, source, options)
}

/// Retained state beyond the serial reducer's API.
pub fn retained(reducer: &V2Reducer) -> String {
    format!("  templates {}\n", reducer.built_templates())
}
