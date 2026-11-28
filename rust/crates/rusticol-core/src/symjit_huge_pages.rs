// SPDX-License-Identifier: 0BSD

//! No SymJIT code of this process is placed on huge pages.
//!
//! SymJIT 2.28.4 and 2.28.5 free the pages of dropped machine code, but on
//! Linux the huge-page allocation (the `HUGE` option, when the kernel reports
//! a huge-page size) acquires them through `hugepage_rs::alloc`, while the
//! destructor always returns them to the global allocator with the ordinary
//! page layout: a mismatched free. Until a release pairs the two, every
//! route by which the option could reach a SymJIT allocation is closed
//! before it:
//!
//! - a stored application (a plane kernel, a SymJIT application evaluator,
//!   the JIT member of a saved Symbolica evaluator) carries its options and
//!   SymJIT compiles it with them at load: [`without_huge_pages`] clears the
//!   stored `HUGE` bit of every embedded application in a copy of the bytes,
//!   before any load or decode, for artifacts written by any version;
//! - a fresh Symbolica JIT compilation starts from `Config::default()`
//!   (which reads `./symjit.toml` or `$SYMJIT_TOML`) and applies the saved
//!   settings' options: the settings get `huge = false` (`backend.rs`);
//! - pyAmpliCol's own SymJIT configurations set it off explicitly.

use std::borrow::Cow;

// The leading words of a stored SymJIT application: its magic, the storage
// version, the program magic, the configuration magic, then the option word
// (options in the low 32 bits, the compiler type in the high ones).
const APPLICATION_MAGIC: u64 = 0x4056_8795_410d_08e9;
const PROGRAM_MAGIC: u64 = 0xc2b2_44ae_fb8e_4d5d;
const CONFIG_MAGIC: u64 = 0x802c_3c77_c742_2e70;
/// SymJIT's `Config` bit for huge pages.
const HUGE: u64 = 0x0010_0000;
const HEADER_LEN: usize = 40;

fn word(bytes: &[u8], offset: usize) -> u64 {
    let mut word = [0u8; 8];
    word.copy_from_slice(&bytes[offset..offset + 8]);
    u64::from_le_bytes(word)
}

/// `bytes` with the `HUGE` option of every stored SymJIT application they
/// contain (at the start, or embedded, as in a saved Symbolica evaluator)
/// cleared; borrowed when none asks for huge pages.
pub(crate) fn without_huge_pages(bytes: &[u8]) -> Cow<'_, [u8]> {
    let magic = APPLICATION_MAGIC.to_le_bytes();
    let mut owned: Option<Vec<u8>> = None;
    let mut offset = 0;
    while offset + HEADER_LEN <= bytes.len() {
        if bytes[offset..offset + 8] == magic
            && word(bytes, offset + 16) == PROGRAM_MAGIC
            && word(bytes, offset + 24) == CONFIG_MAGIC
        {
            let options = word(bytes, offset + 32);
            if options & HUGE != 0 {
                let copy = owned.get_or_insert_with(|| bytes.to_vec());
                copy[offset + 32..offset + 40].copy_from_slice(&(options & !HUGE).to_le_bytes());
            }
            offset += HEADER_LEN;
        } else {
            offset += 1;
        }
    }
    owned.map_or(Cow::Borrowed(bytes), Cow::Owned)
}

/// Whether a stored application's options ask for huge pages (tests).
#[cfg(test)]
pub(crate) fn asks_for_huge_pages(bytes: &[u8]) -> bool {
    bytes.len() >= HEADER_LEN && word(bytes, 32) & HUGE != 0
}

#[cfg(test)]
pub(crate) fn with_huge_pages(bytes: &[u8]) -> Vec<u8> {
    let mut copy = bytes.to_vec();
    let options = word(&copy, 32) | HUGE;
    copy[32..40].copy_from_slice(&options.to_le_bytes());
    copy
}

/// `bytes` with the `HUGE` option of every embedded stored application set
/// (tests: an artifact written by a producer that asked for huge pages).
#[cfg(test)]
pub(crate) fn with_embedded_huge_pages(bytes: &[u8]) -> (Vec<u8>, usize) {
    let magic = APPLICATION_MAGIC.to_le_bytes();
    let mut copy = bytes.to_vec();
    let mut count = 0;
    let mut offset = 0;
    while offset + HEADER_LEN <= copy.len() {
        if copy[offset..offset + 8] == magic
            && word(&copy, offset + 16) == PROGRAM_MAGIC
            && word(&copy, offset + 24) == CONFIG_MAGIC
        {
            let options = word(&copy, offset + 32) | HUGE;
            copy[offset + 32..offset + 40].copy_from_slice(&options.to_le_bytes());
            count += 1;
            offset += HEADER_LEN;
        } else {
            offset += 1;
        }
    }
    (copy, count)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn header(options: u64) -> Vec<u8> {
        let mut bytes = Vec::new();
        for value in [APPLICATION_MAGIC, 4, PROGRAM_MAGIC, CONFIG_MAGIC, options] {
            bytes.extend_from_slice(&value.to_le_bytes());
        }
        bytes.extend_from_slice(&[7; 24]);
        bytes
    }

    #[test]
    fn the_huge_option_of_every_embedded_application_is_cleared() {
        let mut bytes = b"prefix".to_vec();
        bytes.extend(header(HUGE | 0x3));
        bytes.extend_from_slice(b"middle");
        bytes.extend(header(HUGE));
        let cleared = without_huge_pages(&bytes);
        assert!(matches!(cleared, Cow::Owned(_)));
        let mut expected = b"prefix".to_vec();
        expected.extend(header(0x3));
        expected.extend_from_slice(b"middle");
        expected.extend(header(0));
        assert_eq!(cleared.as_ref(), expected.as_slice());
    }

    #[test]
    fn bytes_without_the_option_are_borrowed_unchanged() {
        let bytes = header(0x3);
        assert!(matches!(without_huge_pages(&bytes), Cow::Borrowed(_)));
        let other = vec![0u8; 100];
        assert!(matches!(without_huge_pages(&other), Cow::Borrowed(_)));
    }
}
