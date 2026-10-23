// SPDX-License-Identifier: 0BSD

//! Native family and schedule construction for the shared-recursion loop engine.
//!
//! Each stage replaces one stage of the Python generator (`loops/v2`) and
//! reproduces its ordering. Inputs are model tables plus the field-level block
//! table. Names are represented by their rank in a sorted table, so comparing
//! ids follows the semantic name ordering. The typed inputs can be built in
//! Rust or deserialized from JSON; generation itself has no Python dependency.
//! Model normalization, block construction and color-state algebra remain the
//! caller's responsibility. These stages alone do not prepare a full amplitude.
//!
//! - [`families`]: the loop-prefix family recursion (`families.py`);
//! - [`schedules`]: skeletons, the view, frames and schedule-B tries
//!   (`skeletons.py`, `schedules.py`).

pub mod families;
pub mod orders;
pub mod schedules;

#[cfg(test)]
mod tests;

use std::collections::{HashMap, HashSet};
use std::hash::{BuildHasherDefault, Hasher};

/// The multiplicative word hash of rustc (`FxHasher`): the generator's maps
/// are keyed by small integer tuples, for which SipHash dominates the cost.
/// Iteration order never reaches an output (every output is sorted or in
/// insertion order).
#[derive(Default, Clone, Copy)]
pub struct WordHasher(u64);

const SEED: u64 = 0x51_7c_c1_b7_27_22_0a_95;

impl Hasher for WordHasher {
    #[inline]
    fn write(&mut self, bytes: &[u8]) {
        for chunk in bytes.chunks(8) {
            let mut word = [0u8; 8];
            word[..chunk.len()].copy_from_slice(chunk);
            self.write_u64(u64::from_le_bytes(word));
        }
    }

    #[inline]
    fn write_u8(&mut self, value: u8) {
        self.write_u64(u64::from(value));
    }

    #[inline]
    fn write_u16(&mut self, value: u16) {
        self.write_u64(u64::from(value));
    }

    #[inline]
    fn write_u32(&mut self, value: u32) {
        self.write_u64(u64::from(value));
    }

    #[inline]
    fn write_u64(&mut self, value: u64) {
        self.0 = (self.0.rotate_left(5) ^ value).wrapping_mul(SEED);
    }

    #[inline]
    fn write_usize(&mut self, value: usize) {
        self.write_u64(value as u64);
    }

    #[inline]
    fn finish(&self) -> u64 {
        self.0
    }
}

pub type FastMap<K, V> = HashMap<K, V, BuildHasherDefault<WordHasher>>;
pub type FastSet<K> = HashSet<K, BuildHasherDefault<WordHasher>>;
