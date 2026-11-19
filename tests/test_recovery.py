"""Phase 1 recovery matrix: k-of-n recovery with real CSPRNG polynomials."""

import itertools
import random

import pytest

from pcss import polynomial
from pcss.config import CHUNK_SIZE, FIELD_MODULUS
from pcss.errors import DuplicatePointError, InsufficientSharesError, ValidationError
from pcss.sharing import Share, recover_message, split_secret

P = FIELD_MODULUS
MULTI_CHUNK = "秘密分享 / 秘密分散 / secret sharing 🔐 \x00 end"   # > 31 bytes, multibyte, NUL


@pytest.mark.parametrize("k,n", [(2, 3), (3, 5), (5, 10)])
def test_every_k_subset_recovers(k, n):
    result = split_secret(MULTI_CHUNK, k, n)
    assert result.metadata.chunk_count == 2          # 55 UTF-8 bytes -> 2 chunks
    for f in result.polynomials:
        assert polynomial.degree(f) == k - 1
    for subset in itertools.combinations(result.shares, k):
        assert recover_message(subset, result.metadata) == MULTI_CHUNK


@pytest.mark.parametrize("k,n", [(2, 3), (3, 5), (5, 10)])
def test_every_k_minus_1_subset_is_rejected(k, n):
    result = split_secret(MULTI_CHUNK, k, n)
    for subset in itertools.combinations(result.shares, k - 1):
        with pytest.raises(InsufficientSharesError):
            recover_message(subset, result.metadata)


@pytest.mark.parametrize("k,n", [(2, 3), (3, 5), (5, 10)])
def test_share_order_does_not_matter(k, n):
    result = split_secret(MULTI_CHUNK, k, n)
    shares = list(result.shares)
    random.Random(k * 100 + n).shuffle(shares)   # test-data shuffling only
    assert recover_message(shares[:k], result.metadata) == MULTI_CHUNK
    assert recover_message(shares, result.metadata) == MULTI_CHUNK


MESSAGES = {
    "english": "The quick brown fox jumps over the lazy dog.",
    "chinese": "基于多项式承诺的可验证秘密分享",
    "japanese": "多項式コミットメントに基づく検証可能な秘密分散",
    "emoji": "🔐🧮✅👨‍👩‍👧🏳️‍🌈",
    "zero_bytes": "\x00\x00a\x00b\x00",
    "empty": "",
    "exactly_31_bytes": "a" * CHUNK_SIZE,
    "32_bytes": "b" * (CHUNK_SIZE + 1),
    "two_full_chunks": "c" * (2 * CHUNK_SIZE),
    "partial_last_chunk": "d" * (3 * CHUNK_SIZE + 7),
}


@pytest.mark.parametrize("message", MESSAGES.values(), ids=MESSAGES.keys())
def test_decode_encode_identity_through_sharing(message):
    result = split_secret(message, 3, 5)
    expected_chunks = max(1, -(-len(message.encode("utf-8")) // CHUNK_SIZE))
    assert result.metadata.chunk_count == expected_chunks
    assert all(len(s.values) == expected_chunks for s in result.shares)   # every chunk, every holder
    assert recover_message(result.shares[1:4], result.metadata) == message


def test_x_coordinates_unique_non_zero_and_in_field():
    result = split_secret("x", 5, 10)
    xs = [s.x for s in result.shares]
    assert len(set(xs)) == 10 and 0 not in xs and all(0 < x < P for x in xs)


def test_duplicate_participant_coordinate_rejected():
    result = split_secret(MULTI_CHUNK, 3, 5)
    s = result.shares
    with pytest.raises(DuplicatePointError):
        recover_message([s[0], s[1], Share(x=s[0].x, values=s[2].values)], result.metadata)


@pytest.mark.parametrize("bad_values", [("1",), (1.0,), (None,), (-5,), (P,)])
def test_malformed_share_values_rejected(bad_values):
    result = split_secret("abc", 2, 3)
    bad = Share(x=result.shares[0].x, values=bad_values)
    with pytest.raises(ValidationError):
        recover_message([bad, result.shares[1]], result.metadata)
