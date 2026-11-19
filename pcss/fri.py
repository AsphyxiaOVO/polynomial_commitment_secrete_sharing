"""FRI-style degree reduction — independent research prototype.

Refactored from ``legacy/FRI.py`` (which is kept unchanged).  The algorithm
is the same:

    f(X) = f_even(X^2) + X * f_odd(X^2)
    g(Y) = f_even(Y) + alpha * f_odd(Y)            (one folding round)

repeated until ``deg <= max_degree``.  ``alpha = 6`` reproduces the legacy
``reduce_power`` default.  Differences to the legacy code:

* all coefficients are reduced modulo p = 2^255 - 19;
* coefficient order is explicit (low-to-high), no ``print`` side effects;
* the stop condition is ``degree <= max_degree`` (the legacy code mixed
  ``degree > 5`` in ``main_withui_finally.py`` with ``len > 5`` in
  ``FRI.py``, and the degree computation scanned the wrong end of the list);
* every round is recorded and the input size is bounded.

Why it is NOT applied to the threshold sharing polynomials
-----------------------------------------------------------
For a Shamir polynomial f of degree k - 1, one folding round yields g with

* ``deg g = floor((k-1)/2)`` -> fewer than k shares would suffice, and
* ``g(0) = f_0 + alpha * f_1`` -> the constant term (the secret) changes.

So folding breaks d = k - 1.  In the legacy GUI this was hidden because the
constant was overwritten *after* folding and the threshold was never tied to
the degree.  The refactored project therefore keeps FRI folding only as a
stand-alone research feature.  ``fold_consistency_holds`` checks the standard
FRI relation between f and its fold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

from . import field, polynomial
from .config import FRI_DEFAULT_ALPHA, FRI_DEFAULT_MAX_DEGREE, MAX_POLYNOMIAL_LENGTH
from .errors import ValidationError

P = field.P


def split_even_odd(coeffs: Sequence[int]) -> Tuple[List[int], List[int]]:
    """Return (f_even, f_odd) with f(X) = f_even(X^2) + X f_odd(X^2) (low-to-high)."""
    return polynomial.trim(list(coeffs[0::2])), polynomial.trim(list(coeffs[1::2]))


def fold(coeffs: Sequence[int], alpha: int) -> List[int]:
    """One folding round: g(Y) = f_even(Y) + alpha * f_odd(Y)  (mod p)."""
    even, odd = split_even_odd(coeffs)
    return polynomial.add(even, polynomial.scale(odd, alpha))


@dataclass(frozen=True)
class FriReduction:
    original: Tuple[int, ...]
    rounds: Tuple[Tuple[int, ...], ...]   # polynomial after each folding round
    alpha: int
    max_degree: int

    @property
    def result(self) -> Tuple[int, ...]:
        return self.rounds[-1] if self.rounds else self.original

    @property
    def degrees(self) -> List[int]:
        return [polynomial.degree(self.original)] + [polynomial.degree(r) for r in self.rounds]


def reduce_degree(coeffs: Sequence[int], *, alpha: int = FRI_DEFAULT_ALPHA,
                  max_degree: int = FRI_DEFAULT_MAX_DEGREE) -> FriReduction:
    """Fold repeatedly until ``degree <= max_degree``.

    Terminates after at most ceil(log2(len(coeffs))) rounds because every round
    roughly halves the number of coefficients.
    """
    f = polynomial.as_polynomial(coeffs, "coefficients", max_length=MAX_POLYNOMIAL_LENGTH)
    alpha = field.require_field_element(alpha, "alpha")
    field.require_int(max_degree, "max_degree")
    if max_degree < 0:
        raise ValidationError("max_degree must be >= 0")
    rounds: List[Tuple[int, ...]] = []
    current = f
    while polynomial.degree(current) > max_degree:
        current = fold(current, alpha)
        rounds.append(tuple(current))
    return FriReduction(original=tuple(f), rounds=tuple(rounds), alpha=alpha, max_degree=max_degree)


def fold_consistency_holds(f: Sequence[int], g: Sequence[int], alpha: int, x: int) -> bool:
    """Check the FRI relation  g(x^2) == (f(x)+f(-x))/2 + alpha*(f(x)-f(-x))/(2x)  for x != 0."""
    x = field.require_field_element(x, "x")
    if x == 0:
        raise ValidationError("x must be non-zero")
    fx, fmx = polynomial.evaluate(f, x), polynomial.evaluate(f, (-x) % P)
    inv2 = field.inv(2)
    even = (fx + fmx) * inv2 % P
    odd = (fx - fmx) * inv2 * field.inv(x) % P
    return polynomial.evaluate(g, x * x % P) == (even + alpha * odd) % P
