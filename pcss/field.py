"""Arithmetic in the prime field GF(p), p = FIELD_MODULUS = 2^255 - 19.

Only Python's built-in arbitrary-precision ``int`` is used, so 255-bit values
never overflow (the legacy ``rxi.py`` relied on NumPy int64 and failed for
this modulus).
"""

from __future__ import annotations

from typing import Iterable, List

from .config import FIELD_MODULUS
from .errors import FieldElementError, NonInvertibleError, ValidationError

P = FIELD_MODULUS


def _is_int(value: object) -> bool:
    # bool is a subclass of int; True/False are almost always input mistakes here.
    return isinstance(value, int) and not isinstance(value, bool)


def is_field_element(value: object) -> bool:
    """Return True iff ``value`` is an int in the canonical range [0, p)."""
    return _is_int(value) and 0 <= value < P  # type: ignore[operator]


def require_int(value: object, name: str = "value") -> int:
    """Return ``value`` if it is a (non-bool) int, else raise ValidationError."""
    if not _is_int(value):
        raise ValidationError(f"{name} must be an integer, got {type(value).__name__}")
    return value  # type: ignore[return-value]


def require_field_element(value: object, name: str = "value") -> int:
    """Return ``value`` if it is a canonical field element, else raise FieldElementError."""
    if not _is_int(value):
        raise FieldElementError(f"{name} must be an integer, got {type(value).__name__}")
    if not 0 <= value < P:  # type: ignore[operator]
        raise FieldElementError(f"{name} must satisfy 0 <= {name} < p (p = 2^255 - 19)")
    return value  # type: ignore[return-value]


def require_field_elements(values: Iterable[object], name: str = "values") -> List[int]:
    """Validate every item of ``values`` as a field element and return them as a list."""
    return [require_field_element(v, f"{name}[{i}]") for i, v in enumerate(values)]


def reduce(value: int) -> int:
    """Map an arbitrary integer to its canonical representative in [0, p)."""
    return require_int(value) % P


def add(a: int, b: int) -> int:
    return (a + b) % P


def sub(a: int, b: int) -> int:
    return (a - b) % P


def neg(a: int) -> int:
    return (-a) % P


def mul(a: int, b: int) -> int:
    return (a * b) % P


def power(base: int, exponent: int) -> int:
    """base ** exponent mod p for a non-negative exponent."""
    if exponent < 0:
        return power(inv(base), -exponent)
    return pow(base % P, exponent, P)


def inv(a: int) -> int:
    """Multiplicative inverse of ``a`` modulo p.

    Raises NonInvertibleError when ``a`` ≡ 0 (mod p).  The legacy
    ``mod_inverse`` silently returned 0 in that case, which produced wrong
    recovery results for duplicate x-coordinates.
    """
    a_mod = require_int(a, "a") % P
    if a_mod == 0:
        raise NonInvertibleError("0 has no multiplicative inverse modulo p")
    return pow(a_mod, -1, P)


def div(a: int, b: int) -> int:
    return mul(a, inv(b))
