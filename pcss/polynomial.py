"""Univariate polynomials over GF(p).

Coefficient order convention (used everywhere in the ``pcss`` package)
---------------------------------------------------------------------
A polynomial is a ``list[int]`` in **low-to-high** order::

    [c0, c1, c2]  represents  c0 + c1*X + c2*X^2

so ``coeffs[i]`` is the coefficient of ``X**i`` and ``coeffs[0]`` is the
constant term.  The zero polynomial is ``[]`` and has degree -1.

The legacy GUI (``legacy/main_withui_finally.py``) stored coefficients
high-to-low while ``legacy/FRI.py`` and ``legacy/secret_clipswithui.py``
used low-to-high, and the conversion was done ad hoc.  Use
:func:`from_high_to_low` / :func:`to_high_to_low` at the boundary instead.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from . import field
from .config import MAX_POLYNOMIAL_LENGTH
from .errors import DuplicatePointError, ProtocolError, ValidationError

P = field.P
Poly = List[int]


# --------------------------------------------------------------------------- #
# Construction / normalisation
# --------------------------------------------------------------------------- #

def as_polynomial(coeffs: Iterable[object], name: str = "polynomial",
                  max_length: int = MAX_POLYNOMIAL_LENGTH) -> Poly:
    """Validate user-supplied low-to-high coefficients and return a trimmed copy."""
    values = list(coeffs)
    if len(values) > max_length:
        raise ValidationError(f"{name} has {len(values)} coefficients; limit is {max_length}")
    return trim(field.require_field_elements(values, name))


def trim(coeffs: Sequence[int]) -> Poly:
    """Remove zero coefficients of the highest powers (canonical form)."""
    end = len(coeffs)
    while end > 0 and coeffs[end - 1] % P == 0:
        end -= 1
    return [c % P for c in coeffs[:end]]


def degree(coeffs: Sequence[int]) -> int:
    """Degree of the polynomial; -1 for the zero polynomial.

    Leading zeros are ignored, e.g. ``degree([5, 0, 0]) == 0``.  (The legacy
    ``reduce_high_degree_polynomials`` scanned the wrong end of a high-to-low
    list and therefore mis-computed the degree.)
    """
    return len(trim(coeffs)) - 1


def from_high_to_low(coeffs_high_to_low: Sequence[int]) -> Poly:
    """Convert the legacy high-to-low representation into the package convention."""
    return trim(list(reversed(coeffs_high_to_low)))


def to_high_to_low(coeffs: Sequence[int]) -> Poly:
    """Convert to high-to-low order (zero polynomial -> ``[0]``) for display/legacy code."""
    t = trim(coeffs)
    return list(reversed(t)) if t else [0]


# --------------------------------------------------------------------------- #
# Ring operations
# --------------------------------------------------------------------------- #

def add(a: Sequence[int], b: Sequence[int]) -> Poly:
    n = max(len(a), len(b))
    return trim([(a[i] if i < len(a) else 0) + (b[i] if i < len(b) else 0) for i in range(n)])


def sub(a: Sequence[int], b: Sequence[int]) -> Poly:
    n = max(len(a), len(b))
    return trim([(a[i] if i < len(a) else 0) - (b[i] if i < len(b) else 0) for i in range(n)])


def scale(a: Sequence[int], factor: int) -> Poly:
    return trim([c * factor for c in a])


def mul(a: Sequence[int], b: Sequence[int]) -> Poly:
    a, b = trim(a), trim(b)
    if not a or not b:
        return []
    out = [0] * (len(a) + len(b) - 1)
    for i, ai in enumerate(a):
        if ai == 0:
            continue
        for j, bj in enumerate(b):
            out[i + j] = (out[i + j] + ai * bj) % P
    return trim(out)


def evaluate(coeffs: Sequence[int], x: int) -> int:
    """Evaluate at ``x`` with Horner's rule; every step is reduced mod p."""
    acc = 0
    x %= P
    for c in reversed(coeffs):
        acc = (acc * x + c) % P
    return acc


def divmod_poly(dividend: Sequence[int], divisor: Sequence[int]) -> Tuple[Poly, Poly]:
    """Return ``(quotient, remainder)`` with ``dividend = quotient*divisor + remainder``.

    ``deg(remainder) < deg(divisor)``.  Raises ValidationError when the divisor
    is the zero polynomial (the legacy implementation crashed or produced
    garbage when the divisor's leading coefficient was 0 or the divisor longer
    than the dividend).
    """
    num = trim(dividend)
    den = trim(divisor)
    if not den:
        raise ValidationError("polynomial division by the zero polynomial")
    if len(num) < len(den):
        return [], num
    lead_inv = field.inv(den[-1])
    rem = list(num)
    quot = [0] * (len(num) - len(den) + 1)
    for k in range(len(quot) - 1, -1, -1):
        coef = (rem[k + len(den) - 1] * lead_inv) % P
        quot[k] = coef
        if coef:
            for j, dj in enumerate(den):
                rem[k + j] = (rem[k + j] - coef * dj) % P
    return trim(quot), trim(rem[: len(den) - 1])


# --------------------------------------------------------------------------- #
# Point-set helpers
# --------------------------------------------------------------------------- #

def require_distinct_points(xs: Sequence[int], name: str = "points") -> List[int]:
    """Validate ``xs`` as field elements that are pairwise distinct in GF(p)."""
    values = field.require_field_elements(xs, name)
    if len(set(values)) != len(values):
        raise DuplicatePointError(f"{name} contains duplicate x-coordinates")
    return values


def vanishing_polynomial(points: Sequence[int]) -> Poly:
    """Z(X) = prod_{s in points} (X - s).

    The empty product is the constant polynomial 1, which is the correct value
    of Z_{T \\ S_i} when S_i == T (the legacy code raised IndexError there).
    """
    result: Poly = [1]
    for s in points:
        result = mul(result, [(-s) % P, 1])
    return result


def evaluate_vanishing(points: Sequence[int], x: int) -> int:
    """Z(x) = prod (x - s) without building the polynomial."""
    acc = 1
    for s in points:
        acc = (acc * (x - s)) % P
    return acc


def interpolate(points: Sequence[Tuple[int, int]]) -> Poly:
    """Lagrange interpolation: the unique polynomial of degree < len(points) through ``points``.

    Uses only Python integers (no NumPy/SymPy), so it is exact for 255-bit values.
    """
    if not points:
        raise ValidationError("cannot interpolate an empty point set")
    xs = require_distinct_points([pt[0] for pt in points], "interpolation x-coordinates")
    ys = field.require_field_elements([pt[1] for pt in points], "interpolation y-values")
    full = vanishing_polynomial(xs)                       # prod (X - x_j)
    result: Poly = []
    for xi, yi in zip(xs, ys):
        if yi == 0:
            continue
        basis, rem = divmod_poly(full, [(-xi) % P, 1])    # prod_{j != i} (X - x_j)
        if rem:  # x_i is a root of `full` by construction
            raise ProtocolError("vanishing polynomial not divisible by (X - x_i)")
        denom = evaluate(basis, xi)                       # prod_{j != i} (x_i - x_j) != 0
        result = add(result, scale(basis, yi * field.inv(denom)))
    return result


def lagrange_evaluate(points: Sequence[Tuple[int, int]], x: int = 0) -> int:
    """Evaluate the interpolating polynomial of ``points`` at ``x`` (default: 0, the secret)."""
    if not points:
        raise ValidationError("cannot interpolate an empty point set")
    xs = require_distinct_points([pt[0] for pt in points], "interpolation x-coordinates")
    ys = field.require_field_elements([pt[1] for pt in points], "interpolation y-values")
    x = field.require_field_element(x, "x")
    total = 0
    for i, (xi, yi) in enumerate(zip(xs, ys)):
        num, den = 1, 1
        for j, xj in enumerate(xs):
            if i != j:
                num = (num * (x - xj)) % P
                den = (den * (xi - xj)) % P
        total = (total + yi * num * field.inv(den)) % P
    return total
