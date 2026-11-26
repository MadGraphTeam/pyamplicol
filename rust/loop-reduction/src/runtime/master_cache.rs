// SPDX-License-Identifier: 0BSD

//! Per-batch cache of binary64 master integrals in front of a NinjaRS
//! [`FastMasters`] provider (design §11.2).
//!
//! Every request row is first brought to a canonical argument order, then
//! keyed by the exact bit patterns of its arguments. Canonicalisation is
//! restricted to relabellings under which the requested outputs are invariant:
//!
//! - `C0`: the six relabellings of the triangle, acting consistently on its
//!   three invariants and squared masses;
//! - `D0`: the eight dihedral relabellings of the box, acting consistently on
//!   `(p_i², s12, s23, m_i²)`. They keep consecutive propagators adjacent, so a
//!   box reaches oneloopmaster in loop-cycle order whenever the caller's family
//!   is in loop-cycle order;
//! - `A0` needs none;
//! - bubbles are keyed by the ordered tuple `[p², m0², m1², mu²]`: their tensor
//!   coefficients are not invariant under `m0 <-> m1`
//!   (`B1(p²; m0, m1) = -B0 - B1(p²; m1, m0)`).
//!
//! The same canonical rows are sent to the provider whether or not caching is
//! enabled, so cached and uncached reductions agree bit for bit as long as the
//! provider evaluates each row independently of the other rows of its batch.
//! Only successful rows are cached; keys are exact, so entries never go stale,
//! and [`MasterCache::clear`] only bounds memory.
//!
//! **Shared tier (parallel reduction).** The engines of one parallel
//! reduction (`crate::lane_slices`) share one [`SharedMasters`]
//! ([`MasterCache::share`]): a cache of the same exact keys that every
//! engine reads and fills, so that a master that several slices need is
//! evaluated about once per call instead of once per worker. A value does
//! not depend on which engine evaluated it (the provider evaluates each row
//! on its own), and the statistics do not depend on the scheduling: a row
//! counts as evaluated when its value is the first stored under its key (or
//! when it fails), else as a hit; two engines that miss the same key at once
//! both evaluate it, and the second counts it as a hit. Each engine keeps
//! the rows it found in the tier or evaluated in its own values in front of
//! the tier, so that a row it has seen takes no lock (most requests are
//! repeats: about 150 per evaluated row on loop-induced plans). The serial
//! reduction uses no shared tier.
//!
//! **Look-ups.** Most requests repeat a row already seen (the lanes of one
//! point ask for the same masters; about 150 requests per evaluated row on
//! loop-induced plans), so the look-up itself dominates the cache's cost. A
//! key hashes the words of its arguments with a word hasher
//! ([`Key::digest`]); two keys are equal only when every bit of their rows
//! is, so a collision costs a comparison, never a different value. Triangle
//! and box rows are also remembered as they were asked ([`MasterCache`]'s
//! `asked`): a repeated row is resolved to the source its first occurrence
//! found, without being canonicalised again. Canonicalisation is a function
//! of the row's bits, so that source is the one the canonical look-up would
//! find: which rows reach the provider, in which order, and every count are
//! those of the plain canonical look-up.

use ninjars::Result;
use ninjars::fast::{C64, FastMaster, FastMasters};
use std::collections::HashMap;
use std::hash::{BuildHasher, BuildHasherDefault, Hash, Hasher};
use std::sync::{Arc, RwLock};
use std::time::Instant;

const FAMILIES: [FastMaster; 6] = [
    FastMaster::A0,
    FastMaster::BubbleRank2,
    FastMaster::BubbleRank3,
    FastMaster::BubbleRank4,
    FastMaster::C0,
    FastMaster::D0,
];
const MAX_ARITY: usize = 11;
/// The most Laurent triples a master row has (`FastMaster::outputs`).
const MAX_OUTPUTS: usize = {
    let mut most = 0;
    let mut k = 0;
    while k < FAMILIES.len() {
        if FAMILIES[k].outputs() > most {
            most = FAMILIES[k].outputs();
        }
        k += 1;
    }
    most
};

fn family_index(family: FastMaster) -> usize {
    FAMILIES.iter().position(|f| *f == family).unwrap()
}

/// Request counts per master family since the last reset.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct MasterStatistics {
    /// Rows requested by the reduction engine.
    pub requests: [u64; 6],
    /// Rows served without a provider evaluation (cached, or repeated in one
    /// request batch).
    pub hits: [u64; 6],
    /// Rows evaluated by the provider.
    pub evaluated: [u64; 6],
    /// Wall time of the cache's `evaluate` calls (canonicalisation, cache
    /// look-ups and the provider), nanoseconds.
    pub nanoseconds: u64,
    /// Wall time inside the provider's `evaluate` calls, nanoseconds.
    pub provider_nanoseconds: u64,
}

impl std::ops::AddAssign for MasterStatistics {
    /// The statistics of several engines (the workers of a parallel
    /// reduction): every count and time summed.
    fn add_assign(&mut self, other: Self) {
        for (a, b) in [
            (&mut self.requests, other.requests),
            (&mut self.hits, other.hits),
            (&mut self.evaluated, other.evaluated),
        ] {
            for (x, y) in a.iter_mut().zip(b) {
                *x += y;
            }
        }
        self.nanoseconds += other.nanoseconds;
        self.provider_nanoseconds += other.provider_nanoseconds;
    }
}

impl MasterStatistics {
    pub const FAMILY_NAMES: [&'static str; 6] = ["A0", "B2", "B3", "B4", "C0", "D0"];

    pub fn total_requests(&self) -> u64 {
        self.requests.iter().sum()
    }
    pub fn total_hits(&self) -> u64 {
        self.hits.iter().sum()
    }
    pub fn total_evaluated(&self) -> u64 {
        self.evaluated.iter().sum()
    }
}

/// The exact key of a master row: its family and the bit patterns of its
/// arguments (real and imaginary part of each, in order; the words past the
/// family's arity are zero).
#[derive(Clone, Copy)]
struct Key {
    family: FastMaster,
    bits: [u64; 2 * MAX_ARITY],
}

impl Key {
    fn new(family: FastMaster, row: &[C64]) -> Self {
        let mut bits = [0; 2 * MAX_ARITY];
        for (slot, value) in bits.chunks_exact_mut(2).zip(row) {
            slot[0] = value.re.to_bits();
            slot[1] = value.im.to_bits();
        }
        Self { family, bits }
    }

    /// The words that hold the arguments.
    fn words(&self) -> &[u64] {
        &self.bits[..2 * self.family.arity()]
    }

    /// A digest of every word of the key: the folded products of each
    /// argument's two words, each with constants of its position, summed (no
    /// dependency chain between the arguments), then mixed once by
    /// [`DigestHasher`]. Only the speed of a look-up depends on it.
    #[inline]
    fn digest(&self) -> u64 {
        let mut sum = (self.family as u64).wrapping_add(1).wrapping_mul(SEEDS[0]);
        for (k, pair) in self.words().chunks_exact(2).enumerate() {
            sum = sum.wrapping_add(fold(pair[0] ^ SEEDS[2 * k + 1], pair[1] ^ SEEDS[2 * k + 2]));
        }
        sum
    }
}

/// Keys are equal when their families and every bit of their arguments are.
impl PartialEq for Key {
    #[inline]
    fn eq(&self, other: &Self) -> bool {
        self.family == other.family && self.words() == other.words()
    }
}

impl Eq for Key {}

impl Hash for Key {
    #[inline]
    fn hash<H: Hasher>(&self, state: &mut H) {
        state.write_u64(self.digest());
    }
}

/// The 64-bit halves of a full product, xored (the mixing step of the
/// folded-multiply hashes).
#[inline]
fn fold(a: u64, b: u64) -> u64 {
    let product = u128::from(a) * u128::from(b);
    (product as u64) ^ ((product >> 64) as u64)
}

/// Constants of [`Key::digest`] (a SplitMix64 sequence): one for the
/// family, two per argument position, one for the final mix.
const SEEDS: [u64; 2 * MAX_ARITY + 2] = {
    let mut seeds = [0; 2 * MAX_ARITY + 2];
    let mut state: u64 = 0x9e37_79b9_7f4a_7c15;
    let mut k = 0;
    while k < seeds.len() {
        state = state.wrapping_add(0x9e37_79b9_7f4a_7c15);
        let mut z = state;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
        seeds[k] = (z ^ (z >> 31)) | 1;
        k += 1;
    }
    seeds
};

/// The hasher of the cache's maps: a [`Key`] writes its digest once, which
/// is mixed here so that every bit of it reaches the low bits (the table's
/// buckets) and the high bits (its tags). Other input is folded in word by
/// word.
#[derive(Default)]
struct DigestHasher(u64);

impl Hasher for DigestHasher {
    fn write(&mut self, bytes: &[u8]) {
        for chunk in bytes.chunks(8) {
            let mut word = [0; 8];
            word[..chunk.len()].copy_from_slice(chunk);
            self.write_u64(u64::from_le_bytes(word));
        }
    }

    #[inline]
    fn write_u64(&mut self, word: u64) {
        self.0 = fold(self.0 ^ word, SEEDS[2 * MAX_ARITY + 1]);
    }

    #[inline]
    fn finish(&self) -> u64 {
        self.0
    }
}

type Digested = BuildHasherDefault<DigestHasher>;

/// A map keyed by exact master rows.
type ExactMap<V> = HashMap<Key, V, Digested>;

fn order_key(value: &C64) -> (u64, u64) {
    (value.re.to_bits(), value.im.to_bits())
}

/// Write the canonical form of one request row into `out`.
///
/// For `n = 3, 4` cut lines the row holds the adjacent invariants
/// `(lines 0-1, 1-2, ..., (n-1)-0)`, for boxes the two diagonals `(0-2, 1-3)`,
/// then the `n` squared masses and the scale. The canonical row is the
/// lexicographic minimum (on bit patterns) over the dihedral relabellings of
/// the lines, which for `n = 3` are all permutations.
pub(crate) fn canonicalise(family: FastMaster, row: &[C64], out: &mut [C64]) {
    let n = match family {
        FastMaster::C0 => 3,
        FastMaster::D0 => 4,
        _ => {
            out.copy_from_slice(row);
            return;
        }
    };
    let sides = n;
    let diagonals = if n == 4 { 2 } else { 0 };
    let masses = sides + diagonals;
    // Invariant between distinct lines i and j of the original row.
    let pair = |i: usize, j: usize| {
        if (i + 1) % n == j {
            row[i]
        } else if (j + 1) % n == i {
            row[j]
        } else {
            row[sides + i.min(j) % 2]
        }
    };
    let mut candidate = [C64::ZERO; MAX_ARITY];
    let mut best = [C64::ZERO; MAX_ARITY];
    let arity = row.len();
    let mut first = true;
    for reflected in [false, true] {
        for rotation in 0..n {
            let line = |k: usize| {
                if reflected {
                    (rotation + n - k) % n
                } else {
                    (rotation + k) % n
                }
            };
            let (invariants, rest) = candidate.split_at_mut(masses);
            for (k, slot) in invariants[..sides].iter_mut().enumerate() {
                *slot = pair(line(k), line((k + 1) % n));
            }
            for (k, slot) in invariants[sides..].iter_mut().enumerate() {
                *slot = pair(line(k), line(k + 2));
            }
            for (k, slot) in rest[..n].iter_mut().enumerate() {
                *slot = row[masses + line(k)];
            }
            candidate[arity - 1] = row[arity - 1];
            if first
                || candidate[..arity]
                    .iter()
                    .map(order_key)
                    .lt(best[..arity].iter().map(order_key))
            {
                best[..arity].copy_from_slice(&candidate[..arity]);
                first = false;
            }
        }
    }
    out.copy_from_slice(&best[..arity]);
}

/// The master values the engines of one parallel reduction share
/// ([`MasterCache::share`]; module docs): successful rows by their exact
/// canonical key, in shards (each a reader-writer lock) so that the workers
/// rarely wait for one another.
pub struct SharedMasters {
    shards: Vec<RwLock<ExactMap<[[C64; 3]; MAX_OUTPUTS]>>>,
}

impl SharedMasters {
    /// A shared tier for `workers` engines.
    pub fn new(workers: usize) -> Self {
        // A few shards per worker: two workers rarely want one at once.
        let shards = (4 * workers.max(1)).next_power_of_two();
        Self {
            shards: (0..shards)
                .map(|_| RwLock::new(ExactMap::default()))
                .collect(),
        }
    }

    fn shard(&self, key: &Key) -> &RwLock<ExactMap<[[C64; 3]; MAX_OUTPUTS]>> {
        // Bits of the hash that a shard's table uses neither for its buckets
        // (the low bits) nor for its tags (the top seven).
        let hash = Digested::default().hash_one(key);
        &self.shards[((hash >> 40) as usize) & (self.shards.len() - 1)]
    }

    /// Drop every value (a new chunk of points).
    pub fn clear(&self) {
        for shard in &self.shards {
            shard.write().expect("shared masters").clear();
        }
    }

    /// Number of distinct stored rows.
    pub fn len(&self) -> usize {
        self.shards
            .iter()
            .map(|shard| shard.read().expect("shared masters").len())
            .sum()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

/// Where a request row's outputs come from: a cached value (its offset in
/// the cache's values) or a miss of the current call (its index).
#[derive(Clone, Copy)]
enum Source {
    Cached(usize),
    Evaluated(usize),
}

/// Whether a family's rows have a canonical form other than themselves
/// ([`canonicalise`]): those rows are also remembered as asked.
fn relabelled(family: FastMaster) -> bool {
    matches!(family, FastMaster::C0 | FastMaster::D0)
}

/// Canonicalising, optionally caching [`FastMasters`] wrapper.
pub struct MasterCache<M> {
    inner: M,
    enabled: bool,
    /// Canonical key -> offset of its outputs in `values`.
    entries: ExactMap<usize>,
    /// Triangle and box rows as asked -> the source their canonical key
    /// resolved to (module docs, 'Look-ups'). Between calls it holds cached
    /// sources only: a call's own misses are settled at its end.
    asked: ExactMap<Source>,
    values: Vec<[C64; 3]>,
    statistics: MasterStatistics,
    canonical: Vec<C64>,
    sources: Vec<Source>,
    pending: ExactMap<usize>,
    pending_keys: Vec<Key>,
    /// Rows of the current call entered in `asked` as one of its misses.
    asked_misses: Vec<Key>,
    /// Per miss of the current call: the offset of its stored outputs, or
    /// `None` (failed).
    stored: Vec<Option<usize>>,
    miss_args: Vec<C64>,
    miss_out: Vec<[C64; 3]>,
    miss_ok: Vec<bool>,
    /// The shared tier of a parallel reduction ([`Self::share`]).
    shared: Option<Arc<SharedMasters>>,
}

impl<M: FastMasters> MasterCache<M> {
    pub fn new(inner: M, enabled: bool) -> Self {
        Self {
            inner,
            enabled,
            entries: ExactMap::default(),
            asked: ExactMap::default(),
            values: Vec::new(),
            statistics: MasterStatistics::default(),
            canonical: Vec::new(),
            sources: Vec::new(),
            pending: ExactMap::default(),
            pending_keys: Vec::new(),
            asked_misses: Vec::new(),
            stored: Vec::new(),
            miss_args: Vec::new(),
            miss_out: Vec::new(),
            miss_ok: Vec::new(),
            shared: None,
        }
    }

    /// Use `shared` as this cache's values (module docs, 'Shared tier'), or
    /// none: the cache's own. The cache's own values are dropped either way
    /// when the tier changes (they would be counted again), so that the
    /// statistics follow the keys of the reduction alone.
    pub fn share(&mut self, shared: Option<Arc<SharedMasters>>) {
        let same = match (&self.shared, &shared) {
            (Some(a), Some(b)) => Arc::ptr_eq(a, b),
            (None, None) => true,
            _ => false,
        };
        if !same {
            self.forget();
            self.shared = shared;
        }
    }

    /// The shared tier in use ([`Self::share`]).
    pub fn shared(&self) -> Option<&Arc<SharedMasters>> {
        self.shared.as_ref()
    }

    /// Drop this cache's own values, its buffers and its shared tier (a
    /// parallel reduction's worker copy between calls); the provider and the
    /// statistics stay.
    pub fn release(&mut self) {
        self.entries = HashMap::new();
        self.values = Vec::new();
        self.canonical = Vec::new();
        self.sources = Vec::new();
        self.pending = HashMap::new();
        self.pending_keys = Vec::new();
        self.miss_args = Vec::new();
        self.miss_out = Vec::new();
        self.miss_ok = Vec::new();
        self.shared = None;
    }

    pub fn enabled(&self) -> bool {
        self.enabled
    }

    /// Drop every cached value (statistics are kept), the shared tier's too.
    pub fn clear(&mut self) {
        self.forget();
        if let Some(shared) = &self.shared {
            shared.clear();
        }
    }

    /// Drop this cache's own values and what points at them.
    fn forget(&mut self) {
        self.entries.clear();
        self.asked.clear();
        self.values.clear();
    }

    /// Number of distinct cached rows (the shared tier's when in use).
    pub fn len(&self) -> usize {
        match &self.shared {
            Some(shared) => shared.len(),
            None => self.entries.len(),
        }
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    pub fn statistics(&self) -> MasterStatistics {
        self.statistics
    }

    pub fn take_statistics(&mut self) -> MasterStatistics {
        std::mem::take(&mut self.statistics)
    }

    /// Add another cache's statistics to this one's (a parallel reduction's
    /// worker copy, dropped after its call).
    pub fn add_statistics(&mut self, statistics: MasterStatistics) {
        self.statistics += statistics;
    }
}

impl<M: FastMasters> FastMasters for MasterCache<M> {
    /// Forwarded, so that the fast engine refuses a provider selecting UV or
    /// IR poles behind the cache. The cache itself holds whatever its provider
    /// returns; the v2 adapter never changes its provider's selection, so
    /// every cached row has the combined poles.
    fn requires_scaleless_bubbles(&self) -> bool {
        self.inner.requires_scaleless_bubbles()
    }

    /// Forwarded uncached (NinjaRS's cancellation rescue, double-double
    /// masters at a lane's refined arguments: few calls, every argument a
    /// new point), so the rescue reaches the provider's double-double
    /// masters (oneloopmaster's) behind the cache instead of its closed
    /// forms and binary64 masters.
    fn evaluate_rescue(
        &mut self,
        family: FastMaster,
        args: &[ninjars::fast::dd::Cd],
        out: &mut [[ninjars::fast::dd::Cd; 3]],
        ok: &mut [bool],
    ) -> Result<bool> {
        self.inner.evaluate_rescue(family, args, out, ok)
    }

    fn evaluate(
        &mut self,
        family: FastMaster,
        args: &[C64],
        out: &mut [[C64; 3]],
        ok: &mut [bool],
    ) -> Result<()> {
        let start = Instant::now();
        let result = self.evaluate_rows(family, args, out, ok);
        self.statistics.nanoseconds += start.elapsed().as_nanos() as u64;
        result
    }
}

impl<M: FastMasters> MasterCache<M> {
    fn provider(
        &mut self,
        family: FastMaster,
        args: &[C64],
        out: &mut [[C64; 3]],
        ok: &mut [bool],
    ) -> Result<()> {
        let start = Instant::now();
        let result = self.inner.evaluate(family, args, out, ok);
        self.statistics.provider_nanoseconds += start.elapsed().as_nanos() as u64;
        result
    }

    fn evaluate_rows(
        &mut self,
        family: FastMaster,
        args: &[C64],
        out: &mut [[C64; 3]],
        ok: &mut [bool],
    ) -> Result<()> {
        let arity = family.arity();
        let width = family.outputs();
        let rows = ok.len();
        for (name, expected, actual) in [
            ("cached master arguments", rows * arity, args.len()),
            ("cached master outputs", rows * width, out.len()),
        ] {
            if expected != actual {
                return Err(ninjars::Error::Shape {
                    name,
                    expected,
                    actual,
                });
            }
        }
        let index = family_index(family);
        self.statistics.requests[index] += rows as u64;
        if !self.enabled {
            self.canonical.resize(args.len(), C64::ZERO);
            for (row, canonical) in args
                .chunks_exact(arity)
                .zip(self.canonical.chunks_exact_mut(arity))
            {
                canonicalise(family, row, canonical);
            }
            self.statistics.evaluated[index] += rows as u64;
            let canonical = std::mem::take(&mut self.canonical);
            let result = self.provider(family, &canonical, out, ok);
            self.canonical = canonical;
            return result;
        }
        let shared = self.shared.clone();
        let shared = shared.as_deref();
        self.resolve(family, args, shared);
        let misses = self.pending_keys.len();
        if shared.is_none() {
            // The serial cache counts before evaluating (also when the
            // provider fails).
            self.statistics.evaluated[index] += misses as u64;
            self.statistics.hits[index] += (rows - misses) as u64;
        }
        self.miss_out.clear();
        self.miss_out.resize(misses * width, [C64::ZERO; 3]);
        self.miss_ok.clear();
        self.miss_ok.resize(misses, false);
        if misses > 0 {
            let (miss_args, mut miss_out, mut miss_ok) = (
                std::mem::take(&mut self.miss_args),
                std::mem::take(&mut self.miss_out),
                std::mem::take(&mut self.miss_ok),
            );
            let result = self.provider(family, &miss_args, &mut miss_out, &mut miss_ok);
            (self.miss_args, self.miss_out, self.miss_ok) = (miss_args, miss_out, miss_ok);
            if result.is_err() {
                // This call's misses have no outputs: forget the rows that
                // point at them.
                for key in &self.asked_misses {
                    self.asked.remove(key);
                }
                return result;
            }
        }
        // Store the successful misses. On the shared tier, a successful row
        // is evaluated when its value is the first stored under its key; a
        // failed row always (as the serial cache counts it).
        self.stored.clear();
        let mut evaluated = 0;
        for (miss, key) in self.pending_keys.iter().enumerate() {
            if !self.miss_ok[miss] {
                self.stored.push(None);
                evaluated += 1;
                continue;
            }
            let outputs = &self.miss_out[miss * width..(miss + 1) * width];
            let offset = self.values.len();
            self.entries.insert(*key, offset);
            self.values.extend_from_slice(outputs);
            self.stored.push(Some(offset));
            if let Some(shared) = shared {
                let mut value = [[C64::ZERO; 3]; MAX_OUTPUTS];
                value[..width].copy_from_slice(outputs);
                if let std::collections::hash_map::Entry::Vacant(entry) = shared
                    .shard(key)
                    .write()
                    .expect("shared masters")
                    .entry(*key)
                {
                    entry.insert(value);
                    evaluated += 1;
                }
            }
        }
        if shared.is_some() {
            self.statistics.evaluated[index] += evaluated as u64;
            self.statistics.hits[index] += (rows - evaluated) as u64;
        }
        // Rows asked in this call that resolved to one of its misses now
        // point at its stored outputs, or are forgotten when it failed.
        for key in &self.asked_misses {
            let source = self.asked.get_mut(key).expect("a row of this call");
            let Source::Evaluated(miss) = *source else {
                unreachable!("a row of this call's misses")
            };
            match self.stored[miss] {
                Some(offset) => *source = Source::Cached(offset),
                None => {
                    self.asked.remove(key);
                }
            }
        }
        for ((source, target), status) in self
            .sources
            .iter()
            .zip(out.chunks_exact_mut(width))
            .zip(ok.iter_mut())
        {
            match *source {
                Source::Cached(offset) => {
                    target.copy_from_slice(&self.values[offset..offset + width]);
                    *status = true;
                }
                Source::Evaluated(miss) => {
                    target.copy_from_slice(&self.miss_out[miss * width..(miss + 1) * width]);
                    *status = self.miss_ok[miss];
                }
            }
        }
        Ok(())
    }

    /// The source of every row of a call (`self.sources`), its misses
    /// (`self.pending_keys`, their canonical rows in `self.miss_args`): a
    /// row's canonical key is looked up in the cache's values, then among the
    /// call's misses, then in the shared tier (whose value the cache then
    /// keeps, so that a row it has seen takes no lock), else it is a new miss.
    /// A triangle or box row asked before resolves to the source its first
    /// occurrence found (module docs, 'Look-ups').
    fn resolve(&mut self, family: FastMaster, args: &[C64], shared: Option<&SharedMasters>) {
        let arity = family.arity();
        let width = family.outputs();
        let relabelled = relabelled(family);
        self.sources.clear();
        self.pending.clear();
        self.pending_keys.clear();
        self.asked_misses.clear();
        self.miss_args.clear();
        let mut canonical = [C64::ZERO; MAX_ARITY];
        for row in args.chunks_exact(arity) {
            let asked = Key::new(family, row);
            if relabelled && let Some(&source) = self.asked.get(&asked) {
                self.sources.push(source);
                continue;
            }
            // The canonical row (a bubble's or a tadpole's is the row).
            let canonical = if relabelled {
                canonicalise(family, row, &mut canonical[..arity]);
                &canonical[..arity]
            } else {
                row
            };
            let key = if relabelled {
                Key::new(family, canonical)
            } else {
                asked
            };
            let source = if let Some(&offset) = self.entries.get(&key) {
                Source::Cached(offset)
            } else if let Some(&miss) = self.pending.get(&key) {
                Source::Evaluated(miss)
            } else if let Some(found) = shared.and_then(|shared| {
                shared
                    .shard(&key)
                    .read()
                    .expect("shared masters")
                    .get(&key)
                    .copied()
            }) {
                let offset = self.values.len();
                self.entries.insert(key, offset);
                self.values.extend_from_slice(&found[..width]);
                Source::Cached(offset)
            } else {
                let miss = self.pending_keys.len();
                self.pending.insert(key, miss);
                self.pending_keys.push(key);
                self.miss_args.extend_from_slice(canonical);
                Source::Evaluated(miss)
            };
            if relabelled {
                self.asked.insert(asked, source);
                if let Source::Evaluated(_) = source {
                    self.asked_misses.push(asked);
                }
            }
            self.sources.push(source);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(re: f64) -> C64 {
        C64::real(re)
    }

    /// Box row for lines with symmetric invariant table `s` and masses `m`.
    fn box_row(s: &[[f64; 4]; 4], m: [f64; 4], lines: [usize; 4]) -> Vec<C64> {
        let [a, b, c, d] = lines;
        vec![
            value(s[a][b]),
            value(s[b][c]),
            value(s[c][d]),
            value(s[d][a]),
            value(s[a][c]),
            value(s[b][d]),
            value(m[a]),
            value(m[b]),
            value(m[c]),
            value(m[d]),
            value(91.),
        ]
    }

    #[test]
    fn dihedral_relabellings_share_one_canonical_box() {
        let s = [
            [0., 1.5, -7.25, 0.],
            [1.5, 0., 0., -3.5],
            [-7.25, 0., 0., 2.125],
            [0., -3.5, 2.125, 0.],
        ];
        let m = [0., 0., 30.25, 30.25];
        let reference = box_row(&s, m, [0, 1, 2, 3]);
        let mut canonical = vec![C64::ZERO; 11];
        canonicalise(FastMaster::D0, &reference, &mut canonical);
        for lines in [
            [1, 2, 3, 0],
            [2, 3, 0, 1],
            [3, 0, 1, 2],
            [0, 3, 2, 1],
            [3, 2, 1, 0],
            [2, 1, 0, 3],
            [1, 0, 3, 2],
        ] {
            let mut other = vec![C64::ZERO; 11];
            canonicalise(FastMaster::D0, &box_row(&s, m, lines), &mut other);
            assert_eq!(other, canonical, "{lines:?}");
        }
        // A non-dihedral relabelling is a different box.
        let mut crossed = vec![C64::ZERO; 11];
        canonicalise(FastMaster::D0, &box_row(&s, m, [0, 2, 1, 3]), &mut crossed);
        assert_ne!(crossed, canonical);
    }

    #[test]
    fn triangles_canonicalise_under_all_permutations_and_bubbles_keep_order() {
        let s = [[0., 2., -5.], [2., 0., 11.], [-5., 11., 0.]];
        let m = [0., 3., 7.];
        let row = |[a, b, c]: [usize; 3]| {
            vec![
                value(s[a][b]),
                value(s[b][c]),
                value(s[c][a]),
                value(m[a]),
                value(m[b]),
                value(m[c]),
                value(4.),
            ]
        };
        let mut reference = vec![C64::ZERO; 7];
        canonicalise(FastMaster::C0, &row([0, 1, 2]), &mut reference);
        for lines in [[1, 2, 0], [2, 0, 1], [0, 2, 1], [2, 1, 0], [1, 0, 2]] {
            let mut other = vec![C64::ZERO; 7];
            canonicalise(FastMaster::C0, &row(lines), &mut other);
            assert_eq!(other, reference);
        }
        let bubble = [value(5.), value(0.), value(9.), value(4.)];
        let mut out = [C64::ZERO; 4];
        canonicalise(FastMaster::BubbleRank2, &bubble, &mut out);
        assert_eq!(out, bubble);
    }

    /// Counts provider rows and returns a row-dependent value.
    struct Counting(usize);
    impl FastMasters for Counting {
        fn evaluate(
            &mut self,
            family: FastMaster,
            args: &[C64],
            out: &mut [[C64; 3]],
            ok: &mut [bool],
        ) -> Result<()> {
            let arity = family.arity();
            let width = family.outputs();
            for (row, (point, values)) in args
                .chunks_exact(arity)
                .zip(out.chunks_exact_mut(width))
                .enumerate()
            {
                self.0 += 1;
                let sum: f64 = point.iter().map(|z| z.re).sum();
                for (k, triple) in values.iter_mut().enumerate() {
                    *triple = [value(sum + k as f64), value(1.), value(2.)];
                }
                ok[row] = point[0].re >= 0.;
            }
            Ok(())
        }
    }

    #[test]
    fn repeated_rows_are_evaluated_once_and_failures_are_not_cached() {
        let mut cache = MasterCache::new(Counting(0), true);
        let rows = [
            [value(1.), value(2.), value(3.), value(4.)],
            [value(1.), value(2.), value(3.), value(4.)],
            [value(-1.), value(2.), value(3.), value(4.)],
        ]
        .concat();
        let mut out = vec![[C64::ZERO; 3]; 12];
        let mut ok = vec![false; 3];
        cache
            .evaluate(FastMaster::BubbleRank3, &rows, &mut out, &mut ok)
            .unwrap();
        assert_eq!(ok, [true, true, false]);
        assert_eq!(out[..4], out[4..8]);
        assert_eq!(cache.inner.0, 2);
        cache
            .evaluate(FastMaster::BubbleRank3, &rows, &mut out, &mut ok)
            .unwrap();
        // The successful row is cached; the failed one is evaluated again.
        assert_eq!(cache.inner.0, 3);
        assert_eq!(cache.len(), 1);
        let statistics = cache.statistics();
        assert_eq!(statistics.total_requests(), 6);
        assert_eq!(statistics.total_evaluated(), 3);
        assert_eq!(statistics.total_hits(), 3);
    }

    /// Fails the whole call (an error, not row statuses) while `broken`.
    struct Breakable {
        counting: Counting,
        broken: bool,
    }
    impl FastMasters for Breakable {
        fn evaluate(
            &mut self,
            family: FastMaster,
            args: &[C64],
            out: &mut [[C64; 3]],
            ok: &mut [bool],
        ) -> Result<()> {
            if self.broken {
                return Err(ninjars::Error::Shape {
                    name: "broken provider",
                    expected: 0,
                    actual: 1,
                });
            }
            self.counting.evaluate(family, args, out, ok)
        }
    }

    fn evaluate_rows<M: FastMasters>(
        cache: &mut MasterCache<M>,
        family: FastMaster,
        rows: &[Vec<C64>],
    ) -> Result<(Vec<[C64; 3]>, Vec<bool>)> {
        let args = rows.concat();
        let mut out = vec![[C64::ZERO; 3]; rows.len() * family.outputs()];
        let mut ok = vec![false; rows.len()];
        cache.evaluate(family, &args, &mut out, &mut ok)?;
        Ok((out, ok))
    }

    /// Relabelled boxes asked again, in one call and across calls, get the
    /// value of their canonical row, which reaches the provider once; counts
    /// as without the memo of asked rows.
    #[test]
    fn repeated_relabelled_rows_resolve_to_their_canonical_value() {
        let s = [
            [0., 1.5, -7.25, 0.],
            [1.5, 0., 0., -3.5],
            [-7.25, 0., 0., 2.125],
            [0., -3.5, 2.125, 0.],
        ];
        let m = [0., 0., 30.25, 30.25];
        let rows: Vec<Vec<C64>> = [[0, 1, 2, 3], [1, 2, 3, 0], [0, 1, 2, 3], [3, 2, 1, 0]]
            .iter()
            .map(|lines| box_row(&s, m, *lines))
            .collect();
        let crossed = box_row(&s, m, [0, 2, 1, 3]);
        let mut cache = MasterCache::new(Counting(0), true);
        let (first, ok) = evaluate_rows(&mut cache, FastMaster::D0, &rows).unwrap();
        assert!(ok.iter().all(|ok| *ok));
        assert!(first.iter().all(|value| *value == first[0]));
        assert_eq!(cache.inner.0, 1);
        let later = [rows[1].clone(), crossed.clone(), rows[0].clone(), crossed];
        let (second, ok) = evaluate_rows(&mut cache, FastMaster::D0, &later).unwrap();
        assert!(ok.iter().all(|ok| *ok));
        assert_eq!([second[0], second[2]], [first[0], first[0]]);
        assert_eq!(second[1], second[3]);
        assert_eq!(cache.inner.0, 2);
        let statistics = cache.statistics();
        assert_eq!(statistics.total_requests(), 8);
        assert_eq!(statistics.total_evaluated(), 2);
        assert_eq!(statistics.total_hits(), 6);
        // The same values uncached (every row canonicalised and evaluated).
        let mut plain = MasterCache::new(Counting(0), false);
        let (uncached, _) = evaluate_rows(&mut plain, FastMaster::D0, &later).unwrap();
        assert_eq!(uncached, second);
        // Cleared: asked again, evaluated again.
        cache.clear();
        evaluate_rows(&mut cache, FastMaster::D0, &rows).unwrap();
        assert_eq!(cache.inner.0, 3);
    }

    /// A failed triangle row and the rows of a call whose provider failed
    /// are not remembered: asked again, they are evaluated again.
    #[test]
    fn failed_rows_and_failed_calls_are_asked_again() {
        let triangle = |[a, b, c]: [f64; 3], [m0, m1, m2]: [f64; 3]| {
            vec![
                value(a),
                value(b),
                value(c),
                value(m0),
                value(m1),
                value(m2),
                value(4.),
            ]
        };
        // Every invariant negative: the canonical row starts negative and fails.
        let failing = triangle([-2., -5., -11.], [0., 3., 7.]);
        let good = triangle([2., -5., 11.], [0., 3., 7.]);
        // `good` with its lines relabelled (1, 2, 0).
        let relabelled_good = triangle([-5., 11., 2.], [3., 7., 0.]);
        let mut cache = MasterCache::new(
            Breakable {
                counting: Counting(0),
                broken: false,
            },
            true,
        );
        let rows = [failing.clone(), good.clone(), failing.clone()];
        let (_, ok) = evaluate_rows(&mut cache, FastMaster::C0, &rows).unwrap();
        assert_eq!(ok, [false, true, false]);
        assert_eq!(cache.inner.counting.0, 2);
        let (_, ok) = evaluate_rows(&mut cache, FastMaster::C0, &rows).unwrap();
        assert_eq!(ok, [false, true, false]);
        assert_eq!(cache.inner.counting.0, 3);
        // A call that fails as a whole: its new rows are not remembered.
        cache.inner.broken = true;
        let fresh = [
            relabelled_good.clone(),
            triangle([1., 1., 1.], [0., 3., 7.]),
        ];
        assert!(evaluate_rows(&mut cache, FastMaster::C0, &fresh).is_err());
        cache.inner.broken = false;
        let (values, ok) = evaluate_rows(&mut cache, FastMaster::C0, &fresh).unwrap();
        assert_eq!(ok, [true, true]);
        assert_eq!(cache.inner.counting.0, 4);
        let mut plain = MasterCache::new(Counting(0), false);
        let (expected, _) = evaluate_rows(&mut plain, FastMaster::C0, &fresh).unwrap();
        assert_eq!(values, expected);
        let statistics = cache.statistics();
        assert_eq!(statistics.total_requests(), 10);
        assert_eq!(statistics.total_evaluated(), 2 + 1 + 1 + 1);
    }

    /// Keys differ when any bit of a row does (signed zeros, one unit in the
    /// last place, an imaginary part).
    #[test]
    fn rows_differing_in_one_bit_are_different_masters() {
        let bubble = |p: C64| vec![p, value(0.), value(9.), value(4.)];
        let next = f64::from_bits(5f64.to_bits() + 1);
        let rows = [
            bubble(value(0.)),
            bubble(value(-0.)),
            bubble(value(5.)),
            bubble(value(next)),
            bubble(C64::new(5., 1e-300)),
            bubble(value(5.)),
        ];
        let mut cache = MasterCache::new(Counting(0), true);
        evaluate_rows(&mut cache, FastMaster::BubbleRank2, &rows).unwrap();
        assert_eq!(cache.inner.0, 5);
        assert_eq!(cache.len(), 5);
        let key = |row: &[C64]| Key::new(FastMaster::BubbleRank2, row);
        assert!(key(&rows[0]) != key(&rows[1]));
        assert!(key(&rows[2]) == key(&rows[5]));
        assert!(Key::new(FastMaster::BubbleRank3, &rows[2]) != key(&rows[2]));
    }
}
