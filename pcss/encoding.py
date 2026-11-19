"""Message <-> field-element chunks (fixed-length byte chunking).

Encoding
--------
1. ``message.encode("utf-8")``.
2. Split the bytes into blocks of ``CHUNK_SIZE`` (31) bytes.
3. Right-pad the last block with ``b"\\x00"`` up to 31 bytes.
4. ``int.from_bytes(block, "big")`` -> one integer < 2^248 < p per block.

Each integer becomes the constant term of one secret-sharing polynomial.

Empty message rule
------------------
An empty message is encoded as **one** all-zero chunk with
``original_length == 0`` (so ``chunk_count == 1``).  This keeps every
sharing task non-degenerate (at least one polynomial, every share carries at
least one value).  Decoding truncates to ``original_length`` bytes and
therefore returns ``""``.

This replaces the legacy decimal-string splitting in
``legacy/message_coding.py``, which lost leading ``\\x00`` bytes and could
produce chunks larger than the field modulus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from .config import CHUNK_SIZE, MAX_CHUNK_COUNT, MAX_MESSAGE_BYTES
from .errors import DecodingError, ValidationError
from .field import require_int

#: Exclusive upper bound of a chunk integer (2^248).
CHUNK_LIMIT = 256**CHUNK_SIZE


def expected_chunk_count(original_length: int, chunk_size: int = CHUNK_SIZE) -> int:
    """Number of chunks for a message of ``original_length`` UTF-8 bytes (>= 1)."""
    if original_length < 0:
        raise ValidationError("original_length must be non-negative")
    return max(1, -(-original_length // chunk_size))


@dataclass(frozen=True)
class EncodedMessage:
    """Chunks plus the metadata needed to decode them."""

    chunks: List[int]
    original_length: int          # UTF-8 byte length (NOT the character count)
    chunk_size: int = CHUNK_SIZE
    chunk_count: int = 1


def encode_message(message: str) -> EncodedMessage:
    """Encode ``message`` into 31-byte big-endian integer chunks."""
    if not isinstance(message, str):
        raise ValidationError(f"message must be str, got {type(message).__name__}")
    try:
        data = message.encode("utf-8")
    except UnicodeEncodeError as exc:  # e.g. lone surrogates such as "\ud800"
        raise ValidationError(f"message is not encodable as UTF-8: {exc.reason}") from exc
    if len(data) > MAX_MESSAGE_BYTES:
        raise ValidationError(
            f"message is {len(data)} UTF-8 bytes; limit is {MAX_MESSAGE_BYTES} bytes")

    count = expected_chunk_count(len(data))
    padded = data.ljust(count * CHUNK_SIZE, b"\x00")
    chunks = [int.from_bytes(padded[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE], "big")
              for i in range(count)]
    return EncodedMessage(chunks=chunks, original_length=len(data),
                          chunk_size=CHUNK_SIZE, chunk_count=count)


def validate_encoding_metadata(original_length: int, chunk_size: int, chunk_count: int) -> None:
    """Check that the three encoding metadata fields are mutually consistent."""
    require_int(original_length, "original_length")
    require_int(chunk_size, "chunk_size")
    require_int(chunk_count, "chunk_count")
    if chunk_size != CHUNK_SIZE:
        raise ValidationError(f"unsupported chunk_size {chunk_size}; expected {CHUNK_SIZE}")
    if not 0 <= original_length <= MAX_MESSAGE_BYTES:
        raise ValidationError(f"original_length must be in [0, {MAX_MESSAGE_BYTES}]")
    if not 1 <= chunk_count <= MAX_CHUNK_COUNT:
        raise ValidationError(f"chunk_count must be in [1, {MAX_CHUNK_COUNT}]")
    if chunk_count != expected_chunk_count(original_length, chunk_size):
        raise ValidationError(
            f"chunk_count {chunk_count} is inconsistent with original_length {original_length}")


def decode_message(chunks: Sequence[int], original_length: int,
                   chunk_size: int = CHUNK_SIZE, chunk_count: int | None = None) -> str:
    """Inverse of :func:`encode_message`.

    Raises DecodingError if a chunk is out of range, the padding bytes are
    not zero (a sign of corrupted / wrong shares) or the bytes are not UTF-8.
    """
    chunks = list(chunks)
    if chunk_count is None:
        chunk_count = len(chunks)
    validate_encoding_metadata(original_length, chunk_size, chunk_count)
    if len(chunks) != chunk_count:
        raise ValidationError(f"expected {chunk_count} chunks, got {len(chunks)}")

    blocks = []
    for i, value in enumerate(chunks):
        require_int(value, f"chunks[{i}]")
        if not 0 <= value < CHUNK_LIMIT:
            raise DecodingError(
                f"chunk {i} does not fit in {chunk_size} bytes (wrong or corrupted shares?)")
        blocks.append(value.to_bytes(chunk_size, "big"))
    data = b"".join(blocks)

    payload, padding = data[:original_length], data[original_length:]
    if padding.strip(b"\x00"):
        raise DecodingError("non-zero padding bytes (wrong or corrupted shares?)")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DecodingError(f"recovered bytes are not valid UTF-8: {exc.reason}") from exc
