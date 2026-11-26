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
//! **Failed rows.** A row the provider fails (its status false) is never
//! cached. By default every `evaluate` is a call of its own: a row that
//! failed in an earlier `evaluate` is asked of the provider again (and
//! cached if it now succeeds); within one `evaluate`, a row asked several
//! times reaches the provider once and every request gets its status (one
//! evaluated, the others hits). A caller that cuts one call into several
//! `evaluate`s (the v2 reducer's reduction call, cut into engine calls and
//! into the slices of a parallel reduction) opens a grouped call
//! ([`MasterCache::begin_call`]): while its [`GroupedCall`] lives, a key the
//! provider failed is remembered, so it is evaluated and counted once in the
//! whole grouped call and its later requests are hits served failed, and
//! `evaluated` does not depend on how the call is cut. A grouped call is
//! opened on the cache's failure scope at that moment: its shared tier when
//! it has one (every engine on the tier is then in the call), the cache
//! itself otherwise. It ends when its [`GroupedCall`] is dropped (also when a
//! panic unwinds past it) or by [`MasterCache::discard_call`]; the failed
//! keys it remembered are never read again, so the calls after it are
//! ordinary calls as if it had not happened. [`MasterCache::clear`],
//! [`MasterCache::release`] and a change of tier ([`MasterCache::share`])
//! drop the failed keys they drop the values of, and neither open nor end a
//! grouped call.
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
//! those of the plain canonical look-up. What the memo keeps across calls is
//! call-independent (the offset of a stored value, dropped with the values);
//! a miss of the current call is tagged with the call's id and read by that
//! call only, so a call that ends early (a provider error, or a panic
//! unwinding out of the provider) leaves nothing a later call could read.

use ninjars::Result;
use ninjars::fast::{C64, FastMaster, FastMasters};
use std::collections::HashMap;
use std::hash::{BuildHasher, BuildHasherDefault, Hash, Hasher};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, RwLock};
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

/// The grouped call open on a failure scope (a cache, or a shared tier),
/// if any (module docs, 'Failed rows').
#[derive(Default)]
struct Calls {
    /// The id of the open grouped call; zero when none is open.
    open: AtomicU64,
    /// The last id given (ids increase and are never reused, so failed keys
    /// stamped with an ended call's id are never read again, and a failure
    /// stamped with an older id than the remembered keys' is not remembered).
    last: AtomicU64,
}

impl Calls {
    /// Open a new grouped call (ending any open one) and return its id.
    fn open(&self) -> u64 {
        let id = self.last.fetch_add(1, Ordering::Relaxed) + 1;
        self.open.store(id, Ordering::Release);
        id
    }

    /// The id of the open grouped call, or zero (ordinary calls).
    fn current(&self) -> u64 {
        self.open.load(Ordering::Acquire)
    }

    /// End grouped call `id` if it is still the open one.
    fn close(&self, id: u64) {
        let _ = self
            .open
            .compare_exchange(id, 0, Ordering::AcqRel, Ordering::Relaxed);
    }

    /// End whatever grouped call is open.
    fn close_any(&self) {
        self.open.store(0, Ordering::Release);
    }
}

/// An open grouped call of a [`MasterCache`] ([`MasterCache::begin_call`];
/// module docs, 'Failed rows'): until it is dropped, the cache's `evaluate`
/// calls (and those of every engine on its shared tier) are one call for
/// failed rows. Dropping it ends the grouped call, also when a panic
/// unwinds past it.
#[must_use = "the grouped call ends when this is dropped"]
pub struct GroupedCall {
    calls: Arc<Calls>,
    id: u64,
}

impl Drop for GroupedCall {
    fn drop(&mut self) {
        self.calls.close(self.id);
    }
}

/// The failed keys of a shared tier's grouped call.
#[derive(Default)]
struct Failures {
    /// The grouped call the keys belong to ([`Calls`]).
    call: u64,
    keys: ExactMap<()>,
}

/// The master values the engines of one parallel reduction share
/// ([`MasterCache::share`]; module docs): successful rows by their exact
/// canonical key, in shards (each a reader-writer lock) so that the workers
/// rarely wait for one another.
pub struct SharedMasters {
    shards: Vec<RwLock<ExactMap<[[C64; 3]; MAX_OUTPUTS]>>>,
    /// The grouped call open on this tier ([`MasterCache::begin_call`]).
    calls: Arc<Calls>,
    /// The keys the provider failed in the tier's grouped call: each counts
    /// once in the call however it is sliced, as in the serial cache. Looked
    /// at on a miss only, and only in a grouped call.
    failed: Mutex<Failures>,
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
            calls: Arc::default(),
            failed: Mutex::default(),
        }
    }

    fn shard(&self, key: &Key) -> &RwLock<ExactMap<[[C64; 3]; MAX_OUTPUTS]>> {
        // Bits of the hash that a shard's table uses neither for its buckets
        // (the low bits) nor for its tags (the top seven).
        let hash = Digested::default().hash_one(key);
        &self.shards[((hash >> 40) as usize) & (self.shards.len() - 1)]
    }

    /// Drop every value (a new chunk of points, or a failed call).
    pub fn clear(&self) {
        for shard in &self.shards {
            shard
                .write()
                .unwrap_or_else(std::sync::PoisonError::into_inner)
                .clear();
        }
        self.failed
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .keys
            .clear();
    }

    /// Whether the provider failed `key` in grouped call `call`.
    fn has_failed(&self, call: u64, key: &Key) -> bool {
        let failures = self.failed.lock().expect("shared masters");
        failures.call == call && failures.keys.contains_key(key)
    }

    /// Remember that the provider failed `key` in grouped call `call`
    /// (forgetting the keys of an earlier one); whether it is new. A failure
    /// of a call older than the one the keys belong to (an engine finishing
    /// an `evaluate` it began before another engine opened a new grouped
    /// call) is not remembered: its call has ended, and the newer call's keys
    /// stay as they are. It counts as evaluated, as in an ordinary call.
    fn record_failure(&self, call: u64, key: Key) -> bool {
        let mut failures = self.failed.lock().expect("shared masters");
        if call < failures.call {
            return true;
        }
        if call > failures.call {
            failures.keys.clear();
            failures.call = call;
        }
        failures.keys.insert(key, ()).is_none()
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
/// the cache's values), a miss of the current call (its index), or a key the
/// provider already failed in the open grouped call (no value).
#[derive(Clone, Copy)]
enum Source {
    Cached(usize),
    Evaluated(usize),
    Failed,
}

/// What the memo of asked rows holds for a row.
#[derive(Clone, Copy)]
enum Asked {
    /// The offset of its cached outputs in the cache's values: valid until
    /// they are dropped (`forget`, `release`), which drops the memo too.
    Cached(usize),
    /// Miss `miss` of the call with id `call`. Only that call reads it: every
    /// call takes a new id when it starts, so a miss left by a call that
    /// ended early (a provider error, or a panic unwinding out of the
    /// provider) is never read by a later one, which looks the row up again
    /// as if that call had not happened. A call that ends normally turns its
    /// misses into `Cached` (stored) or removes them (failed rows).
    Miss { call: u64, miss: usize },
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
    /// Triangle and box rows as asked -> what their canonical key resolved
    /// to (module docs, 'Look-ups'): a cached value, or one of the misses of
    /// the call that asked them, read only by that call ([`Asked`]).
    asked: ExactMap<Asked>,
    /// The id of the current (or last) call ([`Asked::Miss`]); a new one at
    /// the start of every call.
    call: u64,
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
    /// The grouped call open on this cache itself ([`Self::begin_call`];
    /// with a shared tier, the tier's is used instead).
    calls: Arc<Calls>,
    /// The keys the provider failed in grouped call `failed_call` of this
    /// cache (without a shared tier): a failed row is not cached, but within
    /// a grouped call it is evaluated and counted once, so that the count
    /// does not depend on how the call is cut into engine calls.
    failed: ExactMap<()>,
    failed_call: u64,
}

impl<M: FastMasters> MasterCache<M> {
    pub fn new(inner: M, enabled: bool) -> Self {
        Self {
            inner,
            enabled,
            entries: ExactMap::default(),
            asked: ExactMap::default(),
            call: 0,
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
            calls: Arc::default(),
            failed: ExactMap::default(),
            failed_call: 0,
        }
    }

    /// Open a grouped call on this cache's failure scope (its shared tier's
    /// when it has one, else its own), ending any grouped call open there:
    /// until the returned [`GroupedCall`] is dropped (or
    /// [`Self::discard_call`]), a row the provider fails is evaluated and
    /// counted once in all the `evaluate` calls of this cache and of every
    /// engine on its tier, its later requests served failed. Without one,
    /// every `evaluate` is a call of its own (module docs, 'Failed rows').
    pub fn begin_call(&mut self) -> GroupedCall {
        let calls = self.scope().clone();
        let id = calls.open();
        GroupedCall { calls, id }
    }

    /// The failure scope of this cache: its shared tier's grouped calls, or
    /// its own.
    fn scope(&self) -> &Arc<Calls> {
        match &self.shared {
            Some(shared) => &shared.calls,
            None => &self.calls,
        }
    }

    /// Use `shared` as this cache's tier (module docs, 'Shared tier'), or
    /// none: the cache's own values only. A change of tier keeps every value
    /// cached so far (review finding 4, a warm cache switching between the
    /// serial and the parallel reduction): a new tier receives this cache's
    /// values, and leaving a tier keeps the tier's values in this cache, so
    /// a row cached before the switch is a hit after it, as in a reduction
    /// that never switched.
    pub fn share(&mut self, shared: Option<Arc<SharedMasters>>) {
        let same = match (&self.shared, &shared) {
            (Some(a), Some(b)) => Arc::ptr_eq(a, b),
            (None, None) => true,
            _ => false,
        };
        if same {
            return;
        }
        if let Some(old) = self.shared.take() {
            // Keep the old tier's values in front of whatever comes next.
            for shard in &old.shards {
                let shard = shard
                    .read()
                    .unwrap_or_else(std::sync::PoisonError::into_inner);
                for (key, value) in shard.iter() {
                    if !self.entries.contains_key(key) {
                        let width = key.family.outputs();
                        self.entries.insert(*key, self.values.len());
                        self.values.extend_from_slice(&value[..width]);
                    }
                }
            }
        }
        if let Some(new) = &shared {
            for (key, &offset) in self.entries.iter() {
                let width = key.family.outputs();
                let mut value = [[C64::ZERO; 3]; MAX_OUTPUTS];
                value[..width].copy_from_slice(&self.values[offset..offset + width]);
                new.shard(key)
                    .write()
                    .unwrap_or_else(std::sync::PoisonError::into_inner)
                    .entry(*key)
                    .or_insert(value);
            }
        }
        self.failed.clear();
        self.shared = shared;
    }

    /// The shared tier in use ([`Self::share`]).
    pub fn shared(&self) -> Option<&Arc<SharedMasters>> {
        self.shared.as_ref()
    }

    /// Drop this cache's own values, its buffers and its shared tier (a
    /// parallel reduction's worker copy between calls); the provider and the
    /// statistics stay.
    pub fn release(&mut self) {
        // Every map that holds offsets into `values` goes with it (as in
        // `forget`): `asked` remembers cached sources by offset.
        self.entries = ExactMap::default();
        self.asked = ExactMap::default();
        self.values = Vec::new();
        self.canonical = Vec::new();
        self.sources = Vec::new();
        self.pending = ExactMap::default();
        self.pending_keys = Vec::new();
        self.asked_misses = Vec::new();
        self.stored = Vec::new();
        self.miss_args = Vec::new();
        self.miss_out = Vec::new();
        self.miss_ok = Vec::new();
        self.shared = None;
        self.failed = ExactMap::default();
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
        self.failed.clear();
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

    /// Discard a failed reduction call (an error or a caught panic): the
    /// statistics back to `before` (those at the call's start), every value,
    /// remembered row and failed key dropped, the shared tier's too, and the
    /// grouped call open on this cache's failure scope ended. The next call
    /// starts as after the serial reduction's failure, whatever the
    /// interrupted call had reached.
    pub fn discard_call(&mut self, before: MasterStatistics) {
        self.statistics = before;
        self.forget();
        if let Some(shared) = &self.shared {
            shared.clear();
        }
        self.scope().close_any();
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
        // The open grouped call (zero: this call is an ordinary one). The
        // failed keys of an ended one are never read again.
        let call = self.scope().current();
        if shared.is_none() && call != self.failed_call {
            self.failed.clear();
            self.failed_call = call;
        }
        self.resolve(family, args, shared, call);
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
            // On an error (or a panic unwinding from the provider) the call's
            // misses in `asked` are left to its id ([`Asked::Miss`]).
            result?;
        }
        // Store the successful misses and, in a grouped call, remember the
        // failed ones for the rest of it. On the shared tier, a row is
        // evaluated when it is the first stored under its key, its value or,
        // for a failed row, its failure (once per grouped call, as the serial
        // cache counts it; every time in an ordinary call).
        self.stored.clear();
        let mut evaluated = 0;
        for (miss, key) in self.pending_keys.iter().enumerate() {
            if !self.miss_ok[miss] {
                self.stored.push(None);
                match shared {
                    _ if call == 0 => evaluated += 1,
                    None => {
                        self.failed.insert(*key, ());
                    }
                    Some(shared) => {
                        if shared.record_failure(call, *key) {
                            evaluated += 1;
                        }
                    }
                }
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
            let entry = self.asked.get_mut(key).expect("a row of this call");
            let Asked::Miss { call, miss } = *entry else {
                unreachable!("a row of this call's misses")
            };
            debug_assert_eq!(call, self.call);
            match self.stored[miss] {
                Some(offset) => *entry = Asked::Cached(offset),
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
                Source::Failed => {
                    target.fill([C64::ZERO; 3]);
                    *status = false;
                }
            }
        }
        Ok(())
    }

    /// The source of every row of a call (`self.sources`), its misses
    /// (`self.pending_keys`, their canonical rows in `self.miss_args`): a
    /// row's canonical key is looked up in the cache's values, then among the
    /// call's misses, then in the shared tier (whose value the cache then
    /// keeps, so that a row it has seen takes no lock), then, in grouped call
    /// `call` (nonzero), among the keys it failed, else it is a new miss.
    /// A triangle or box row asked before resolves to the source its first
    /// occurrence found (module docs, 'Look-ups').
    fn resolve(
        &mut self,
        family: FastMaster,
        args: &[C64],
        shared: Option<&SharedMasters>,
        call: u64,
    ) {
        let arity = family.arity();
        let width = family.outputs();
        let relabelled = relabelled(family);
        self.sources.clear();
        self.pending.clear();
        self.pending_keys.clear();
        self.asked_misses.clear();
        self.miss_args.clear();
        self.call += 1;
        let this = self.call;
        let mut canonical = [C64::ZERO; MAX_ARITY];
        for row in args.chunks_exact(arity) {
            let asked = Key::new(family, row);
            if relabelled {
                match self.asked.get(&asked) {
                    Some(&Asked::Cached(offset)) => {
                        self.sources.push(Source::Cached(offset));
                        continue;
                    }
                    Some(&Asked::Miss { call: of, miss }) if of == this => {
                        self.sources.push(Source::Evaluated(miss));
                        continue;
                    }
                    // Absent, or a miss of an earlier call that ended early.
                    _ => {}
                }
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
            } else if call != 0
                && match shared {
                    None => self.failed.contains_key(&key),
                    Some(shared) => shared.has_failed(call, &key),
                }
            {
                // Failed earlier in this grouped call (here or on another
                // engine of the tier): a hit without a value, not evaluated
                // again.
                Source::Failed
            } else {
                let miss = self.pending_keys.len();
                self.pending.insert(key, miss);
                self.pending_keys.push(key);
                self.miss_args.extend_from_slice(canonical);
                Source::Evaluated(miss)
            };
            if relabelled {
                // A row failed earlier in this grouped call is not
                // remembered as asked: it is looked up again (and fails).
                let entry = match source {
                    Source::Cached(offset) => Some(Asked::Cached(offset)),
                    Source::Evaluated(miss) => {
                        self.asked_misses.push(asked);
                        Some(Asked::Miss { call: this, miss })
                    }
                    Source::Failed => None,
                };
                if let Some(entry) = entry {
                    self.asked.insert(asked, entry);
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
        let call = cache.begin_call();
        cache
            .evaluate(FastMaster::BubbleRank3, &rows, &mut out, &mut ok)
            .unwrap();
        assert_eq!(ok, [true, true, false]);
        assert_eq!(out[..4], out[4..8]);
        assert_eq!(cache.inner.0, 2);
        // Asked again in the same grouped call: the failed row is not
        // evaluated (nor counted) again, and still fails.
        cache
            .evaluate(FastMaster::BubbleRank3, &rows, &mut out, &mut ok)
            .unwrap();
        assert_eq!(ok, [true, true, false]);
        assert_eq!(cache.inner.0, 2);
        // A new grouped call: the successful row is cached; the failed one
        // is evaluated again.
        drop(call);
        let _call = cache.begin_call();
        cache
            .evaluate(FastMaster::BubbleRank3, &rows, &mut out, &mut ok)
            .unwrap();
        assert_eq!(ok, [true, true, false]);
        assert_eq!(cache.inner.0, 3);
        assert_eq!(cache.len(), 1);
        let statistics = cache.statistics();
        assert_eq!(statistics.total_requests(), 9);
        assert_eq!(statistics.total_evaluated(), 3);
        assert_eq!(statistics.total_hits(), 6);
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

    /// A failed triangle row (in a later reduction call) and the rows of a
    /// call whose provider failed are not remembered: asked again, they are
    /// evaluated again.
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
        let _call = cache.begin_call();
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

    /// Returns the row's scale (its last argument) as the first output, so
    /// that a value given to the wrong row shows; panics in `evaluate` while
    /// `panic` is set, returns an error while `error` is set.
    #[derive(Default)]
    struct Scaled {
        rows: usize,
        panic: bool,
        error: bool,
    }
    impl FastMasters for Scaled {
        fn evaluate(
            &mut self,
            family: FastMaster,
            args: &[C64],
            out: &mut [[C64; 3]],
            ok: &mut [bool],
        ) -> Result<()> {
            if self.panic {
                panic!("provider panic (test)");
            }
            if self.error {
                return Err(ninjars::Error::Shape {
                    name: "provider error (test)",
                    expected: 0,
                    actual: 1,
                });
            }
            let (arity, width) = (family.arity(), family.outputs());
            for (r, (row, values)) in args
                .chunks_exact(arity)
                .zip(out.chunks_exact_mut(width))
                .enumerate()
            {
                self.rows += 1;
                for triple in values.iter_mut() {
                    *triple = [row[arity - 1], value(row[0].re), value(1.)];
                }
                ok[r] = true;
            }
            Ok(())
        }
    }

    /// A triangle row at scale `mu2`.
    fn scaled_triangle(mu2: f64) -> Vec<C64> {
        [2., -5., 11., 0., 3., 7., mu2].map(value).to_vec()
    }

    fn scales(out: &[[C64; 3]]) -> Vec<f64> {
        out.iter().map(|triple| triple[0].re).collect()
    }

    fn catch<T>(f: impl FnOnce() -> T) -> std::thread::Result<T> {
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(f))
    }

    /// The reviewer's sequence: row A's call unwinds out of the provider (the
    /// panic is caught), then [A, B] at scales 2 and 3 gets 2 and 3, as from a
    /// cache that never saw the unwound call.
    #[test]
    fn a_call_that_unwinds_from_the_provider_leaves_no_miss_behind() {
        let (a, b) = (scaled_triangle(2.), scaled_triangle(3.));
        for repeated in [false, true] {
            let mut cache = MasterCache::new(Scaled::default(), true);
            cache.inner.panic = true;
            let first = if repeated {
                vec![a.clone(), a.clone()]
            } else {
                vec![a.clone()]
            };
            assert!(catch(|| evaluate_rows(&mut cache, FastMaster::C0, &first)).is_err());
            cache.inner.panic = false;
            let (out, ok) =
                evaluate_rows(&mut cache, FastMaster::C0, &[a.clone(), b.clone()]).unwrap();
            assert_eq!(ok, [true, true]);
            assert_eq!(scales(&out), [2., 3.]);
            // And again (A and B now cached), and B before A.
            let (out, _) =
                evaluate_rows(&mut cache, FastMaster::C0, &[b.clone(), a.clone()]).unwrap();
            assert_eq!(scales(&out), [3., 2.]);
            assert_eq!(cache.inner.rows, 2);
        }
    }

    /// The same after a provider error, and after an unwind on the shared
    /// tier.
    #[test]
    fn a_call_that_fails_leaves_no_miss_behind() {
        let (a, b) = (scaled_triangle(2.), scaled_triangle(3.));
        let mut cache = MasterCache::new(Scaled::default(), true);
        cache.inner.error = true;
        assert!(evaluate_rows(&mut cache, FastMaster::C0, std::slice::from_ref(&a)).is_err());
        cache.inner.error = false;
        let (out, ok) = evaluate_rows(&mut cache, FastMaster::C0, &[a.clone(), b.clone()]).unwrap();
        assert_eq!((scales(&out), ok), (vec![2., 3.], vec![true, true]));

        let mut cache = MasterCache::new(Scaled::default(), true);
        cache.share(Some(Arc::new(SharedMasters::new(2))));
        cache.inner.panic = true;
        assert!(
            catch(|| evaluate_rows(&mut cache, FastMaster::C0, std::slice::from_ref(&a))).is_err()
        );
        cache.inner.panic = false;
        let (out, ok) = evaluate_rows(&mut cache, FastMaster::C0, &[a.clone(), b.clone()]).unwrap();
        assert_eq!((scales(&out), ok), (vec![2., 3.], vec![true, true]));
        assert_eq!(cache.len(), 2);
    }

    /// One cache across calls at other scales, after `release`, `clear` and a
    /// change of tier: every row gets its own value.
    #[test]
    fn a_cache_reused_across_scales_releases_and_tiers_keeps_rows_apart() {
        let rows: Vec<Vec<C64>> = [2., 3., 5.].map(scaled_triangle).to_vec();
        let mut cache = MasterCache::new(Scaled::default(), true);
        let check = |cache: &mut MasterCache<Scaled>, order: &[usize]| {
            let asked: Vec<Vec<C64>> = order.iter().map(|&k| rows[k].clone()).collect();
            let (out, ok) = evaluate_rows(cache, FastMaster::C0, &asked).unwrap();
            assert!(ok.iter().all(|ok| *ok));
            let expected: Vec<f64> = order.iter().map(|&k| [2., 3., 5.][k]).collect();
            assert_eq!(scales(&out), expected, "{order:?}");
        };
        check(&mut cache, &[0]);
        check(&mut cache, &[1, 0, 1]);
        cache.release();
        check(&mut cache, &[2, 1]);
        check(&mut cache, &[0, 2]);
        cache.share(Some(Arc::new(SharedMasters::new(2))));
        check(&mut cache, &[1]);
        check(&mut cache, &[2, 0, 1]);
        cache.share(None);
        check(&mut cache, &[0, 1, 2]);
        cache.clear();
        check(&mut cache, &[2, 2, 0]);
        check(&mut cache, &[1, 0, 2]);
    }

    /// Two engines on one shared tier: while one call is inside its
    /// provider (and then unwinds out of it), the other completes a call on
    /// the same rows. Afterwards both caches, and a third on the tier, give
    /// every row its own value, and the tier holds only provider values.
    #[test]
    fn a_call_that_unwinds_on_the_shared_tier_leaves_the_other_engines_right() {
        use std::sync::Barrier;
        struct Gated<'a> {
            gate: &'a Barrier,
            armed: bool,
            inner: Scaled,
        }
        impl FastMasters for Gated<'_> {
            fn evaluate(
                &mut self,
                family: FastMaster,
                args: &[C64],
                out: &mut [[C64; 3]],
                ok: &mut [bool],
            ) -> Result<()> {
                if self.armed {
                    self.armed = false;
                    self.gate.wait(); // the other engine starts its call
                    self.gate.wait(); // ... and has completed it
                    panic!("provider panic (test)");
                }
                self.inner.evaluate(family, args, out, ok)
            }
        }
        let (a, b, c) = (
            scaled_triangle(2.),
            scaled_triangle(3.),
            scaled_triangle(5.),
        );
        let tier = Arc::new(SharedMasters::new(2));
        let gate = Barrier::new(2);
        let make = |armed: bool| {
            let mut cache = MasterCache::new(
                Gated {
                    gate: &gate,
                    armed,
                    inner: Scaled::default(),
                },
                true,
            );
            cache.share(Some(tier.clone()));
            cache
        };
        let (mut first, mut second) = (make(true), make(false));
        std::thread::scope(|scope| {
            scope.spawn(|| {
                let rows = [a.clone(), c.clone(), a.clone()];
                assert!(catch(|| evaluate_rows(&mut first, FastMaster::C0, &rows)).is_err());
            });
            scope.spawn(|| {
                gate.wait();
                let (out, ok) =
                    evaluate_rows(&mut second, FastMaster::C0, &[b.clone(), a.clone()]).unwrap();
                assert_eq!((scales(&out), ok), (vec![3., 2.], vec![true, true]));
                gate.wait();
            });
        });
        let all = [a.clone(), b.clone(), c.clone(), a.clone()];
        for cache in [&mut first, &mut second, &mut make(false)] {
            let (out, ok) = evaluate_rows(cache, FastMaster::C0, &all).unwrap();
            assert_eq!((scales(&out), ok), (vec![2., 3., 5., 2.], vec![true; 4]));
        }
        assert_eq!(tier.len(), 3);
    }

    /// Fails the first `failures` rows it evaluates (`Ok`, with the row's
    /// status false), then evaluates every row as [`Scaled`] does.
    #[derive(Default)]
    struct Recovering {
        rows: usize,
        failures: usize,
    }
    impl FastMasters for Recovering {
        fn evaluate(
            &mut self,
            family: FastMaster,
            args: &[C64],
            out: &mut [[C64; 3]],
            ok: &mut [bool],
        ) -> Result<()> {
            let (arity, width) = (family.arity(), family.outputs());
            for (r, (row, values)) in args
                .chunks_exact(arity)
                .zip(out.chunks_exact_mut(width))
                .enumerate()
            {
                self.rows += 1;
                for triple in values.iter_mut() {
                    *triple = [row[arity - 1], value(row[0].re), value(1.)];
                }
                ok[r] = self.failures == 0;
                self.failures = self.failures.saturating_sub(1);
            }
            Ok(())
        }
    }

    /// A caller that never opens a grouped call: each `evaluate` asks the
    /// provider again for a row it failed before, and caches the row once it
    /// succeeds, with or without a shared tier. Within one `evaluate` a row
    /// asked twice is evaluated once and both requests get its status.
    #[test]
    fn ordinary_calls_ask_the_provider_again_for_a_failed_row() {
        let bubble = [2., 0., 9., 4.].map(value).to_vec();
        for shared in [false, true] {
            for (family, row) in [
                (FastMaster::C0, scaled_triangle(4.)),
                (FastMaster::BubbleRank2, bubble.clone()),
            ] {
                let mut cache = MasterCache::new(
                    Recovering {
                        failures: 1,
                        ..Recovering::default()
                    },
                    true,
                );
                if shared {
                    cache.share(Some(Arc::new(SharedMasters::new(2))));
                }
                let twice = [row.clone(), row.clone()];
                let (_, ok) = evaluate_rows(&mut cache, family, &twice).unwrap();
                assert_eq!((ok, cache.inner.rows), (vec![false; 2], 1), "{shared}");
                let (out, ok) = evaluate_rows(&mut cache, family, &twice).unwrap();
                assert_eq!((ok, cache.inner.rows), (vec![true; 2], 2), "{shared}");
                assert_eq!(scales(&out)[0], 4.);
                let (again, ok) = evaluate_rows(&mut cache, family, &twice).unwrap();
                assert_eq!((ok, cache.inner.rows), (vec![true; 2], 2), "{shared}");
                assert_eq!(again, out);
                assert_eq!(cache.len(), 1);
                let statistics = cache.statistics();
                assert_eq!(statistics.total_requests(), 6);
                assert_eq!(statistics.total_evaluated(), 2);
                assert_eq!(statistics.total_hits(), 4);
            }
        }
    }

    /// Fails the rows whose first argument is negative (`Ok`, the row's
    /// status false) and evaluates the others as [`Scaled`] does; panics in
    /// `evaluate` while `panic` is set, returns an error while `error` is.
    #[derive(Default)]
    struct Faulty {
        rows: usize,
        panic: bool,
        error: bool,
    }
    impl FastMasters for Faulty {
        fn evaluate(
            &mut self,
            family: FastMaster,
            args: &[C64],
            out: &mut [[C64; 3]],
            ok: &mut [bool],
        ) -> Result<()> {
            let mut scaled = Scaled {
                panic: self.panic,
                error: self.error,
                ..Scaled::default()
            };
            scaled.evaluate(family, args, out, ok)?;
            self.rows += scaled.rows;
            for (r, row) in args.chunks_exact(family.arity()).enumerate() {
                ok[r] = row[0].re >= 0.;
            }
            Ok(())
        }
    }

    /// Asks a failing triangle row once: it fails, the provider has seen
    /// `rows` rows so far, and the cache counted one request and, as
    /// evaluated, exactly the rows the provider saw.
    #[track_caller]
    fn ask_failing(cache: &mut MasterCache<Faulty>, row: &[C64], rows: usize) {
        let (before, seen) = (cache.statistics(), cache.inner.rows);
        let (_, ok) = evaluate_rows(cache, FastMaster::C0, &[row.to_vec()]).unwrap();
        assert_eq!((ok, cache.inner.rows), (vec![false], rows));
        let after = cache.statistics();
        assert_eq!(after.total_requests(), before.total_requests() + 1);
        assert_eq!(
            after.total_evaluated() - before.total_evaluated(),
            (rows - seen) as u64
        );
    }

    /// Failed rows are coalesced exactly while a grouped call is open, in
    /// every order of grouped and ordinary calls, with and without a shared
    /// tier: once a grouped call has ended (its handle dropped, by
    /// `discard_call`, by an error, or by a panic unwinding past the handle
    /// with nobody calling `discard_call`), a failed row is asked of the
    /// provider again; `clear`, `release` and a change of tier drop failed
    /// keys without ending the grouped call of the scope.
    #[test]
    fn failed_rows_are_coalesced_only_inside_a_grouped_call() {
        let f = [-2., -5., -11., 0., 3., 7., 4.].map(value).to_vec();
        for shared in [false, true] {
            let mut cache = MasterCache::new(Faulty::default(), true);
            if shared {
                cache.share(Some(Arc::new(SharedMasters::new(2))));
            }
            // Ordinary, grouped, ordinary.
            ask_failing(&mut cache, &f, 1);
            ask_failing(&mut cache, &f, 2);
            let call = cache.begin_call();
            ask_failing(&mut cache, &f, 3);
            ask_failing(&mut cache, &f, 3);
            drop(call);
            ask_failing(&mut cache, &f, 4);
            ask_failing(&mut cache, &f, 5);
            // Ended by `discard_call` while its handle lives; that handle,
            // dropped during a later grouped call, does not end it.
            let call = cache.begin_call();
            ask_failing(&mut cache, &f, 6);
            ask_failing(&mut cache, &f, 6);
            cache.discard_call(cache.statistics());
            ask_failing(&mut cache, &f, 7);
            ask_failing(&mut cache, &f, 8);
            let next = cache.begin_call();
            ask_failing(&mut cache, &f, 9);
            drop(call);
            ask_failing(&mut cache, &f, 9);
            drop(next);
            ask_failing(&mut cache, &f, 10);
            // A panic unwinding out of the provider (on a new row) and past
            // the handle.
            let unwound = catch(|| {
                let _call = cache.begin_call();
                ask_failing(&mut cache, &f, 11);
                ask_failing(&mut cache, &f, 11);
                cache.inner.panic = true;
                let _ = evaluate_rows(&mut cache, FastMaster::C0, &[scaled_triangle(9.)]);
            });
            let payload = unwound.expect_err("the provider panics");
            assert_eq!(
                payload.downcast_ref::<&str>(),
                Some(&"provider panic (test)")
            );
            cache.inner.panic = false;
            ask_failing(&mut cache, &f, 12);
            ask_failing(&mut cache, &f, 13);
            // A provider error ending the grouped call.
            let grouped = |cache: &mut MasterCache<Faulty>| -> Result<()> {
                let _call = cache.begin_call();
                ask_failing(cache, &f, 14);
                ask_failing(cache, &f, 14);
                cache.inner.error = true;
                evaluate_rows(cache, FastMaster::C0, &[scaled_triangle(10.)])?;
                Ok(())
            };
            assert!(grouped(&mut cache).is_err());
            cache.inner.error = false;
            ask_failing(&mut cache, &f, 15);
            ask_failing(&mut cache, &f, 16);
            // A successful row next to the failing one is cached throughout.
            let good = scaled_triangle(4.);
            let (out, ok) =
                evaluate_rows(&mut cache, FastMaster::C0, std::slice::from_ref(&good)).unwrap();
            assert_eq!(
                (scales(&out)[0], ok, cache.inner.rows),
                (4., vec![true], 17)
            );
            let _call = cache.begin_call();
            let (_, ok) =
                evaluate_rows(&mut cache, FastMaster::C0, &[good.clone(), f.clone()]).unwrap();
            assert_eq!((ok, cache.inner.rows), (vec![true, false], 18));
        }

        // Without a shared tier: `clear` and `release` drop the failed keys
        // of the open grouped call, which goes on; joining a tier with no
        // grouped call open makes the calls ordinary, leaving it returns to
        // the cache's own grouped call.
        let mut cache = MasterCache::new(Faulty::default(), true);
        let call = cache.begin_call();
        ask_failing(&mut cache, &f, 1);
        ask_failing(&mut cache, &f, 1);
        cache.clear();
        ask_failing(&mut cache, &f, 2);
        ask_failing(&mut cache, &f, 2);
        cache.release();
        ask_failing(&mut cache, &f, 3);
        ask_failing(&mut cache, &f, 3);
        let tier = Arc::new(SharedMasters::new(2));
        cache.share(Some(tier.clone()));
        ask_failing(&mut cache, &f, 4);
        ask_failing(&mut cache, &f, 5);
        cache.share(None);
        ask_failing(&mut cache, &f, 6);
        ask_failing(&mut cache, &f, 6);
        drop(call);
        ask_failing(&mut cache, &f, 7);

        // On a shared tier: a grouped call opened by one cache holds for
        // every cache on the tier; `clear` drops the tier's failed keys; a
        // cache that leaves the tier (`release`, `share(None)`) makes
        // ordinary calls, and one that comes back is in the call again.
        let on_tier = || {
            let mut cache = MasterCache::new(Faulty::default(), true);
            cache.share(Some(tier.clone()));
            cache
        };
        let (mut a, mut b) = (on_tier(), on_tier());
        let call = a.begin_call();
        ask_failing(&mut b, &f, 1);
        ask_failing(&mut a, &f, 0);
        a.clear();
        ask_failing(&mut b, &f, 2);
        ask_failing(&mut b, &f, 2);
        a.release();
        ask_failing(&mut a, &f, 1);
        ask_failing(&mut a, &f, 2);
        ask_failing(&mut b, &f, 2);
        b.share(None);
        ask_failing(&mut b, &f, 3);
        ask_failing(&mut b, &f, 4);
        b.share(Some(tier.clone()));
        ask_failing(&mut b, &f, 4);
        drop(call);
        ask_failing(&mut b, &f, 5);
        ask_failing(&mut b, &f, 6);
    }

    /// Relabellings of one triangle row asked in one `evaluate`, with a
    /// provider that fails the first row it sees: an ordinary call asks the
    /// provider again in the next `evaluate`, a grouped call serves the
    /// failure until it ends; either way every relabelling gets the
    /// canonical row's value and status, with and without a shared tier.
    #[test]
    fn relabelled_rows_follow_the_grouped_call_rule() {
        let a = [2., -5., 11., 0., 3., 7., 4.].map(value).to_vec();
        let r = [-5., 11., 2., 3., 7., 0., 4.].map(value).to_vec();
        for shared in [false, true] {
            for grouped in [false, true] {
                let tag = format!("shared {shared} grouped {grouped}");
                let mut cache = MasterCache::new(
                    Recovering {
                        failures: 1,
                        ..Recovering::default()
                    },
                    true,
                );
                if shared {
                    cache.share(Some(Arc::new(SharedMasters::new(2))));
                }
                let g = grouped.then(|| cache.begin_call());
                let (_, ok) =
                    evaluate_rows(&mut cache, FastMaster::C0, &[a.clone(), r.clone()]).unwrap();
                assert_eq!((ok, cache.inner.rows), (vec![false; 2], 1), "{tag}");
                let (out, ok) =
                    evaluate_rows(&mut cache, FastMaster::C0, &[r.clone(), a.clone()]).unwrap();
                if grouped {
                    assert_eq!((ok, cache.inner.rows), (vec![false; 2], 1), "{tag}");
                    assert_eq!(scales(&out), vec![0.; 2], "{tag}");
                    drop(g);
                    let (out, ok) =
                        evaluate_rows(&mut cache, FastMaster::C0, &[r.clone(), a.clone()]).unwrap();
                    assert_eq!((ok, cache.inner.rows), (vec![true; 2], 2), "{tag}");
                    assert_eq!(scales(&out), vec![4.; 2], "{tag}");
                } else {
                    assert_eq!((ok, cache.inner.rows), (vec![true; 2], 2), "{tag}");
                    assert_eq!(scales(&out), vec![4.; 2], "{tag}");
                }
                let (out, ok) = evaluate_rows(
                    &mut cache,
                    FastMaster::C0,
                    &[a.clone(), r.clone(), a.clone()],
                )
                .unwrap();
                assert_eq!((ok, cache.inner.rows), (vec![true; 3], 2), "{tag}");
                assert_eq!(scales(&out), vec![4.; 3], "{tag}");
                let st = cache.statistics();
                let req = if grouped { 9 } else { 7 };
                assert_eq!(
                    (st.total_requests(), st.total_evaluated(), st.total_hits()),
                    (req, 2, req - 2),
                    "{tag}"
                );
                assert_eq!(cache.len(), 1, "{tag}");
            }
        }
    }

    type Shared<T> = Arc<Mutex<T>>;

    /// A provider that, the first time it evaluates, lets another cache on
    /// the same tier open a new grouped call and fail a row in it, then
    /// fails its own rows as [`Faulty`] does: its cache finishes an
    /// `evaluate` of the older grouped call after the newer one has begun.
    struct Interloper {
        faulty: Faulty,
        other: Option<Shared<MasterCache<Faulty>>>,
        newer: Shared<Option<GroupedCall>>,
        row: Vec<C64>,
    }
    impl FastMasters for Interloper {
        fn evaluate(
            &mut self,
            family: FastMaster,
            args: &[C64],
            out: &mut [[C64; 3]],
            ok: &mut [bool],
        ) -> Result<()> {
            if let Some(other) = self.other.take() {
                let mut other = other.lock().unwrap();
                *self.newer.lock().unwrap() = Some(other.begin_call());
                ask_failing(&mut other, &self.row, 1);
            }
            self.faulty.evaluate(family, args, out, ok)
        }
    }

    /// A cache still inside an `evaluate` of an ended grouped call when
    /// another cache on its tier opens a new one: the failure it records
    /// belongs to the ended call, so the newer call is undisturbed (its
    /// failed row stays coalesced, the late row is not served failed in it).
    #[test]
    fn a_late_failure_of_an_ended_grouped_call_leaves_the_newer_one_alone() {
        let f = [-2., -5., -11., 0., 3., 7., 4.].map(value).to_vec();
        let late = [-3., -6., -13., 0., 3., 7., 4.].map(value).to_vec();
        let tier = Arc::new(SharedMasters::new(2));
        let mut other = MasterCache::new(Faulty::default(), true);
        other.share(Some(tier.clone()));
        let other = Arc::new(Mutex::new(other));
        let newer = Arc::new(Mutex::new(None));
        let mut cache = MasterCache::new(
            Interloper {
                faulty: Faulty::default(),
                other: Some(other.clone()),
                newer: newer.clone(),
                row: f.clone(),
            },
            true,
        );
        cache.share(Some(tier.clone()));
        let older = cache.begin_call();
        let (_, ok) =
            evaluate_rows(&mut cache, FastMaster::C0, std::slice::from_ref(&late)).unwrap();
        assert_eq!((ok, cache.inner.faulty.rows), (vec![false], 1));
        let statistics = cache.statistics();
        assert_eq!(
            (statistics.total_requests(), statistics.total_evaluated()),
            (1, 1)
        );
        drop(older);
        assert!(
            newer.lock().unwrap().is_some(),
            "the newer grouped call is open"
        );
        let mut other = other.lock().unwrap();
        // The newer call's failed row is still coalesced: no provider call.
        ask_failing(&mut other, &f, 1);
        // The late row did not fail in the newer call: the provider is asked.
        ask_failing(&mut other, &late, 2);
        ask_failing(&mut other, &late, 2);
        let statistics = other.statistics();
        assert_eq!(
            (
                statistics.total_requests(),
                statistics.total_evaluated(),
                statistics.total_hits()
            ),
            (4, 2, 2)
        );
    }
}
