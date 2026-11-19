"""Threshold (Shamir) secret sharing of an encoded message.

Parameters (never mix them up)
------------------------------
* ``chunk_count`` – number of 31-byte message chunks = number of polynomials.
* ``share_count`` (n) – number of participants / shares.
* ``threshold`` (k) – minimum number of shares needed for recovery.

For every chunk ``s_j`` the dealer builds

    f_j(X) = s_j + a_{j,1} X + ... + a_{j,k-1} X^{k-1},   a_{j,k-1} != 0

i.e. the degree is **fixed by the system** to d = k - 1 (the caller can no
longer choose an arbitrary degree as in the legacy GUI).  A share for
participant x is ``(x, [f_1(x), ..., f_m(x)])``.

The threshold is stored in :class:`SharingMetadata` when the shares are
created.  Recovery never tries to infer the degree from the number of
supplied points: it requires at least ``metadata.threshold`` shares.

Randomness
----------
The default entry point :func:`split_secret` draws every random coefficient
with :func:`secrets.randbelow` (a CSPRNG); the ``random`` module is never
used, and callers cannot supply coefficients.  Each chunk gets its own,
independently sampled polynomial.  :func:`split_secret_with_coefficients`
exists only for research / debugging (deterministic examples, legacy-style
manual input) and is not used by the application layer.

FRI-style degree reduction is intentionally **not** applied here, because
folding changes both the degree and the constant term of f_j and would break
the threshold property; see ``pcss/fri.py``.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field as dc_field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import field, polynomial
from .config import CHUNK_SIZE, MAX_SHARE_COUNT, MAX_THRESHOLD, MIN_THRESHOLD
from .encoding import EncodedMessage, decode_message, encode_message, validate_encoding_metadata
from .errors import (DuplicatePointError, InconsistentSharesError, InsufficientSharesError,
                     ValidationError)

P = field.P


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SharingMetadata:
    """Public parameters fixed when the shares were generated."""

    threshold: int
    share_count: int
    original_length: int
    chunk_count: int
    chunk_size: int = CHUNK_SIZE

    @property
    def degree(self) -> int:
        """Degree of every sharing polynomial (d = k - 1)."""
        return self.threshold - 1

    def validate(self) -> "SharingMetadata":
        validate_sharing_parameters(self.threshold, self.share_count)
        validate_encoding_metadata(self.original_length, self.chunk_size, self.chunk_count)
        return self

    def to_dict(self) -> Dict[str, int]:
        return {
            "threshold": self.threshold,
            "share_count": self.share_count,
            "original_length": self.original_length,
            "chunk_size": self.chunk_size,
            "chunk_count": self.chunk_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> "SharingMetadata":
        if not isinstance(data, dict):
            raise ValidationError("metadata must be a mapping")
        try:
            meta = cls(threshold=data["threshold"], share_count=data["share_count"],
                       original_length=data["original_length"],
                       chunk_count=data["chunk_count"],
                       chunk_size=data.get("chunk_size", CHUNK_SIZE))
        except KeyError as exc:
            raise ValidationError(f"metadata is missing field {exc.args[0]!r}") from exc
        return meta.validate()


@dataclass(frozen=True)
class Share:
    """One participant's share: the x-coordinate and one value per chunk polynomial."""

    x: int
    values: Tuple[int, ...]

    def to_dict(self) -> Dict[str, object]:
        return {"x": self.x, "values": list(self.values)}

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "Share":
        if not isinstance(data, dict):
            raise ValidationError("share must be a mapping")
        try:
            x, values = data["x"], data["values"]
        except KeyError as exc:
            raise ValidationError(f"share is missing field {exc.args[0]!r}") from exc
        if not isinstance(values, (list, tuple)):
            raise ValidationError("share values must be a list")
        return cls(x=x, values=tuple(values))  # type: ignore[arg-type]


@dataclass(frozen=True)
class SharingResult:
    """Output of :func:`split_secret`.

    ``polynomials`` is dealer-private data (it contains the secret chunks); it
    is returned so that the commitment step can be built on the same
    polynomials, and must not be handed to participants.
    """

    metadata: SharingMetadata
    shares: Tuple[Share, ...]
    polynomials: Tuple[Tuple[int, ...], ...] = dc_field(repr=False)


# --------------------------------------------------------------------------- #
# Parameter validation
# --------------------------------------------------------------------------- #

def validate_sharing_parameters(threshold: int, share_count: int) -> None:
    """Check k >= 2, n >= k, n < p and the configured resource limits."""
    field.require_int(threshold, "threshold")
    field.require_int(share_count, "share_count")
    if threshold < MIN_THRESHOLD:
        raise ValidationError(f"threshold k must be >= {MIN_THRESHOLD}, got {threshold}")
    if threshold > MAX_THRESHOLD:
        raise ValidationError(f"threshold k must be <= {MAX_THRESHOLD}, got {threshold}")
    if share_count < threshold:
        raise ValidationError(
            f"share_count n must be >= threshold k (n={share_count}, k={threshold})")
    if share_count >= P:  # implied by the limit below; kept to state the requirement n < p
        raise ValidationError("share_count n must be smaller than the field modulus p")
    if share_count > MAX_SHARE_COUNT:
        raise ValidationError(f"share_count n must be <= {MAX_SHARE_COUNT}, got {share_count}")


def default_x_coordinates(share_count: int, excluded: Iterable[int] = ()) -> List[int]:
    """The ``share_count`` smallest positive integers that are not in ``excluded``."""
    banned = set(excluded) | {0}
    xs: List[int] = []
    candidate = 1
    while len(xs) < share_count:
        if candidate not in banned:
            xs.append(candidate)
        candidate += 1
    return xs


def validate_x_coordinates(xs: Sequence[int], name: str = "x_coordinates",
                           excluded: Iterable[int] = ()) -> List[int]:
    """Share x-coordinates must be non-zero, pairwise distinct field elements (and not excluded)."""
    values = field.require_field_elements(xs, name)
    for i, x in enumerate(values):
        if x == 0:
            raise ValidationError(f"{name}[{i}] is 0; x = 0 would reveal the secret itself")
    if len(set(values)) != len(values):
        raise DuplicatePointError(f"{name} contains duplicate x-coordinates")
    banned = set(excluded)
    for i, x in enumerate(values):
        if x in banned:
            raise ValidationError(f"{name}[{i}] = {x} is in the excluded set")
    return values


# --------------------------------------------------------------------------- #
# Dealer side
# --------------------------------------------------------------------------- #

def build_sharing_polynomial(secret: int, threshold: int,
                             random_coefficients: Sequence[int]) -> List[int]:
    """Return ``[secret, a_1, ..., a_{k-1}]`` (low-to-high), enforcing degree exactly k - 1."""
    field.require_field_element(secret, "secret")
    coeffs = field.require_field_elements(random_coefficients, "random_coefficients")
    if len(coeffs) != threshold - 1:
        raise ValidationError(
            f"expected exactly k - 1 = {threshold - 1} non-constant coefficients, got {len(coeffs)}")
    if coeffs[-1] == 0:
        raise ValidationError("leading coefficient must be non-zero so that degree == k - 1")
    return [secret, *coeffs]


def random_sharing_polynomial(secret: int, threshold: int) -> List[int]:
    """CSPRNG polynomial: a_1..a_{k-2} uniform in GF(p), a_{k-1} uniform in GF(p)* (degree = k - 1)."""
    middle = [secrets.randbelow(P) for _ in range(threshold - 2)]
    leading = secrets.randbelow(P - 1) + 1
    return build_sharing_polynomial(secret, threshold, [*middle, leading])


def _resolve_x_coordinates(share_count: int, x_coordinates: Optional[Sequence[int]],
                           excluded: List[int]) -> List[int]:
    if x_coordinates is None:
        return default_x_coordinates(share_count, excluded)
    xs = validate_x_coordinates(x_coordinates, excluded=excluded)
    if len(xs) != share_count:
        raise ValidationError(f"expected {share_count} x-coordinates, got {len(xs)}")
    return xs


def _build_result(encoded: EncodedMessage, threshold: int, share_count: int, xs: Sequence[int],
                  polys: Sequence[Sequence[int]]) -> SharingResult:
    shares = tuple(
        Share(x=x, values=tuple(polynomial.evaluate(f, x) for f in polys)) for x in xs)
    metadata = SharingMetadata(threshold=threshold, share_count=share_count,
                               original_length=encoded.original_length,
                               chunk_count=encoded.chunk_count, chunk_size=encoded.chunk_size)
    return SharingResult(metadata=metadata, shares=shares,
                         polynomials=tuple(tuple(f) for f in polys))


def split_secret(message: str, threshold: int, share_count: int, *,
                 x_coordinates: Optional[Sequence[int]] = None,
                 excluded_x: Iterable[int] = ()) -> SharingResult:
    """Encode ``message`` and create ``share_count`` shares with recovery threshold ``threshold``.

    Default (and only production-style) path: one independent CSPRNG
    polynomial of degree exactly k - 1 per chunk.  ``x_coordinates`` defaults to
    1..n (skipping ``excluded_x``); ``excluded_x`` lets the commitment layer
    forbid share x-coordinates that lie in its evaluation set T.
    """
    validate_sharing_parameters(threshold, share_count)
    xs = _resolve_x_coordinates(share_count, x_coordinates, list(excluded_x))
    encoded = encode_message(message)
    polys = [random_sharing_polynomial(secret, threshold) for secret in encoded.chunks]
    return _build_result(encoded, threshold, share_count, xs, polys)


def split_secret_with_coefficients(message: str, threshold: int, share_count: int,
                                   coefficients: Sequence[Sequence[int]], *,
                                   x_coordinates: Optional[Sequence[int]] = None,
                                   excluded_x: Iterable[int] = ()) -> SharingResult:
    """RESEARCH / DEBUG ONLY: share with caller-chosen coefficients.

    ``coefficients`` holds, per chunk, exactly k - 1 non-constant coefficients
    (low-to-high, leading one non-zero), so the threshold relation d = k - 1 is
    still enforced.  Not exposed by the REST API.
    """
    validate_sharing_parameters(threshold, share_count)
    xs = _resolve_x_coordinates(share_count, x_coordinates, list(excluded_x))
    encoded = encode_message(message)
    if len(coefficients) != encoded.chunk_count:
        raise ValidationError(
            f"expected coefficients for {encoded.chunk_count} chunk polynomials, "
            f"got {len(coefficients)}")
    polys = [build_sharing_polynomial(secret, threshold, coefficients[j])
             for j, secret in enumerate(encoded.chunks)]
    return _build_result(encoded, threshold, share_count, xs, polys)


# --------------------------------------------------------------------------- #
# Recovery side
# --------------------------------------------------------------------------- #

def validate_shares(shares: Sequence[Share], metadata: SharingMetadata) -> List[Share]:
    """Validate shares against the stored metadata (count, x-coordinates, value ranges)."""
    metadata.validate()
    shares = list(shares)
    if len(shares) < metadata.threshold:
        raise InsufficientSharesError(
            f"Insufficient shares for recovery: got {len(shares)}, threshold is {metadata.threshold}")
    if len(shares) > metadata.share_count:
        raise ValidationError(
            f"got {len(shares)} shares but only {metadata.share_count} were issued")
    for i, share in enumerate(shares):
        if not isinstance(share, Share):
            raise ValidationError(f"shares[{i}] must be a Share, got {type(share).__name__}")
        if len(share.values) != metadata.chunk_count:
            raise ValidationError(
                f"shares[{i}] has {len(share.values)} values; expected chunk_count = "
                f"{metadata.chunk_count}")
        field.require_field_elements(share.values, f"shares[{i}].values")
    validate_x_coordinates([s.x for s in shares], name="share x-coordinates")
    return shares


def recover_constants(shares: Sequence[Share], metadata: SharingMetadata, *,
                      check_consistency: bool = True) -> List[int]:
    """Recover f_j(0) for every chunk polynomial.

    The first ``threshold`` shares determine each polynomial.  If more shares
    are supplied and ``check_consistency`` is True, every extra share must lie
    on the same degree-(k-1) polynomial, otherwise InconsistentSharesError is
    raised.  With exactly k shares a modified share cannot be detected by
    recovery alone.
    """
    shares = validate_shares(shares, metadata)
    k = metadata.threshold
    base, extra = shares[:k], shares[k:]
    constants: List[int] = []
    for j in range(metadata.chunk_count):
        points = [(s.x, s.values[j]) for s in base]
        if check_consistency and extra:
            f_j = polynomial.interpolate(points)
            for s in extra:
                if polynomial.evaluate(f_j, s.x) != s.values[j]:
                    raise InconsistentSharesError(
                        f"share at x={s.x} is inconsistent with the other shares (chunk {j})")
            constants.append(polynomial.evaluate(f_j, 0))
        else:
            constants.append(polynomial.lagrange_evaluate(points, 0))
    return constants


def recover_message(shares: Sequence[Share], metadata: SharingMetadata, *,
                    check_consistency: bool = True) -> str:
    """Recover the constants and decode them back to the original UTF-8 message."""
    constants = recover_constants(shares, metadata, check_consistency=check_consistency)
    return decode_message(constants, metadata.original_length, metadata.chunk_size,
                          metadata.chunk_count)
