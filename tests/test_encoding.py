import pytest

from pcss.config import CHUNK_SIZE, FIELD_MODULUS, MAX_MESSAGE_BYTES
from pcss.encoding import (CHUNK_LIMIT, decode_message, encode_message, expected_chunk_count,
                           validate_encoding_metadata)
from pcss.errors import DecodingError, ValidationError

MESSAGES = {
    "english": "Hello, polynomial commitments!",
    "chinese": "基于多项式承诺的可验证秘密分享",
    "japanese": "多項式コミットメントに基づく検証可能な秘密分散",
    "emoji": "🔐🧮✅👍🏽👨‍👩‍👧",
    "long": "長いメッセージ long message 长消息 🚀 " * 40,
    "nul_inside": "a\x00b\x00\x00c",
    "leading_nul": "\x00\x00secret",
    "trailing_nul": "secret\x00\x00",
    "only_nul": "\x00" * 31,
    "short": "hi",
    "exactly_31": "x" * 31,
    "exactly_62": "y" * 62,
    "32_bytes": "z" * 32,
    "empty": "",
}


@pytest.mark.parametrize("message", MESSAGES.values(), ids=MESSAGES.keys())
def test_round_trip(message):
    enc = encode_message(message)
    data = message.encode("utf-8")
    assert enc.original_length == len(data)               # bytes, not characters
    assert enc.chunk_size == CHUNK_SIZE
    assert enc.chunk_count == len(enc.chunks) == expected_chunk_count(len(data))
    assert all(0 <= c < CHUNK_LIMIT < FIELD_MODULUS for c in enc.chunks)
    assert decode_message(enc.chunks, enc.original_length, enc.chunk_size, enc.chunk_count) == message


def test_original_length_is_utf8_byte_length():
    enc = encode_message("秘密")  # 2 characters, 6 bytes
    assert enc.original_length == 6


@pytest.mark.parametrize("length,count", [(0, 1), (1, 1), (30, 1), (31, 1), (32, 2), (62, 2), (63, 3)])
def test_chunk_count(length, count):
    assert expected_chunk_count(length) == count


def test_empty_message_rule():
    enc = encode_message("")
    assert enc.chunks == [0] and enc.original_length == 0 and enc.chunk_count == 1
    assert decode_message([0], 0) == ""


def test_padding_is_on_the_right_and_big_endian():
    enc = encode_message("A")
    assert enc.chunks == [0x41 << (8 * 30)]
    enc = encode_message("\x00A")  # leading NUL survives because chunks are fixed length
    assert enc.chunks == [0x41 << (8 * 29)]
    assert decode_message(enc.chunks, enc.original_length) == "\x00A"


def test_message_too_long():
    encode_message("a" * MAX_MESSAGE_BYTES)
    with pytest.raises(ValidationError):
        encode_message("a" * (MAX_MESSAGE_BYTES + 1))
    with pytest.raises(ValidationError):
        encode_message("中" * (MAX_MESSAGE_BYTES // 3 + 1))  # limit is in bytes


@pytest.mark.parametrize("bad", [b"x", 123, None])
def test_encode_requires_str(bad):
    with pytest.raises(ValidationError):
        encode_message(bad)


def test_lone_surrogate_rejected():
    with pytest.raises(ValidationError):
        encode_message("\ud800")


def test_decode_rejects_chunk_out_of_range():
    with pytest.raises(DecodingError):
        decode_message([CHUNK_LIMIT], 1)
    with pytest.raises(DecodingError):
        decode_message([FIELD_MODULUS - 1], 1)


def test_decode_rejects_non_zero_padding():
    enc = encode_message("abc")
    with pytest.raises(DecodingError):
        decode_message([enc.chunks[0] + 1], enc.original_length)


def test_decode_rejects_invalid_utf8():
    bad = int.from_bytes(b"\xff\xfe".ljust(31, b"\x00"), "big")
    with pytest.raises(DecodingError):
        decode_message([bad], 2)
    # A multi-byte character cut by a wrong original_length is also detected.
    enc = encode_message("中")
    with pytest.raises(DecodingError):
        decode_message(enc.chunks, 2)


def test_decode_metadata_consistency():
    enc = encode_message("x" * 40)  # 2 chunks
    with pytest.raises(ValidationError):
        decode_message(enc.chunks[:1], 40)              # chunk_count mismatch
    with pytest.raises(ValidationError):
        decode_message(enc.chunks, 40, chunk_size=32)
    with pytest.raises(ValidationError):
        decode_message(enc.chunks, 40, chunk_count=3)
    with pytest.raises(ValidationError):
        validate_encoding_metadata(-1, CHUNK_SIZE, 1)
    with pytest.raises(ValidationError):
        validate_encoding_metadata(0, CHUNK_SIZE, 0)
