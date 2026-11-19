"""Multi-point / multi-polynomial evaluation-consistency check (kept from the thesis).

This module is a refactoring of ``Prover`` / ``Verifier`` in
``legacy/main_withui_finally.py``; the algebra is unchanged.  It follows the
batching idea of Boneh-Drake-Fisch-Gabizon, *Efficient polynomial commitment
schemes for multiple points and polynomials* (ePrint 2020/081).

Setting
-------
* polynomials f_1..f_m, point sets S_i, evaluation set T with S_i ⊆ T;
* r_i  = the interpolant of f_i on S_i (deg r_i < |S_i|);
* Z_S(X) = prod_{s in S} (X - s).

Prover (given a point x and a challenge y chosen by the verifier)::

    cm_i = f_i(x)                                  ("commitment values")
    h(X) = sum_i y^(i) * (f_i(X) - r_i(X)) / Z_{S_i}(X)     (exact division)
    W    = h(x)                                    (witness)

Verifier::

    W * Z_T(x)  ==  sum_i (cm_i - r_i(x)) * y^(i) * Z_{T \\ S_i}(x)

(i is 0-based, so the first polynomial has weight y^0 = 1, as in the legacy code.)

Security note
-------------
This is a **teaching / research prototype**.  ``cm_i`` are plain polynomial
evaluations: they are neither hiding nor binding and do **not** have the
security properties of a standard cryptographic polynomial commitment such as
KZG.  The check is an algebraic consistency test between (cm, W) and the
public r_i.  In particular a prover who knows r_i can always produce a pair
(cm', W') that passes the check for arbitrary cm'; see
``tests/test_commitment.py::test_forged_consistent_pair_is_accepted_documented_limitation``.

Degenerate inputs rejected here
-------------------------------
* S_i not a subset of T, empty S_i, duplicate points;
* x ∈ T: then Z_T(x) = 0 and every term on the right is 0 as well, so *any*
  witness would be accepted;
* y = 0: then every polynomial except the first has weight 0 and would not
  be checked at all.  (p is prime, so y != 0 implies y^i != 0 for all i.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

from . import field, polynomial
from .config import MAX_EVALUATION_SET_SIZE, MAX_POINT_SET_SIZE
from .errors import ProtocolError, ValidationError

P = field.P


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #

def validate_point_sets(point_sets: Sequence[Sequence[int]], evaluation_set: Sequence[int],
                        polynomial_count: int, *, require_zero: bool = False
                        ) -> Tuple[Tuple[Tuple[int, ...], ...], Tuple[int, ...]]:
    """Validate S_1..S_m and T; return them as canonical tuples.

    ``require_zero`` reproduces the legacy GUI rule "every S_i must contain 0".
    """
    t_list = polynomial.require_distinct_points(list(evaluation_set), "evaluation_set T")
    if not t_list:
        raise ValidationError("evaluation_set T must not be empty")
    if len(t_list) > MAX_EVALUATION_SET_SIZE:
        raise ValidationError(f"|T| must be <= {MAX_EVALUATION_SET_SIZE}")
    t_set = set(t_list)

    sets = [list(s) for s in point_sets]
    if polynomial_count < 1:
        raise ValidationError("at least one polynomial is required")
    if len(sets) != polynomial_count:
        raise ValidationError(
            f"expected {polynomial_count} point sets (one per polynomial), got {len(sets)}")
    result = []
    for i, s in enumerate(sets):
        name = f"point_sets[{i}]"
        if not s:
            raise ValidationError(f"{name} (S_{i}) must not be empty")
        if len(s) > MAX_POINT_SET_SIZE:
            raise ValidationError(f"|{name}| must be <= {MAX_POINT_SET_SIZE}")
        values = polynomial.require_distinct_points(s, name)
        missing = [v for v in values if v not in t_set]
        if missing:
            raise ValidationError(f"{name} is not a subset of T; points not in T: {missing}")
        if require_zero and 0 not in values:
            raise ValidationError(f"{name} must contain 0")
        result.append(tuple(values))
    return tuple(result), tuple(t_list)


def validate_challenge(x: int, y: int, evaluation_set: Sequence[int]) -> Tuple[int, int]:
    """Check the verifier's point x (x ∉ T) and challenge y (1 <= y < p)."""
    x = field.require_field_element(x, "x")
    y = field.require_field_element(y, "y")
    if x in set(evaluation_set):
        raise ValidationError(
            "x must not belong to T: Z_T(x) = 0 would make every witness pass verification")
    if y == 0:
        raise ValidationError(
            "challenge y must be non-zero: y = 0 gives weight 0 to every polynomial except the first")
    return x, y


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class PublicParameters:
    """Everything the verifier needs: S_i, T and the coefficients of r_i (low-to-high).

    Caution: if 0 ∈ S_i (legacy rule), r_i(0) = f_i(0) is the secret chunk, so
    these parameters reveal the secret and must only be given to a trusted
    verifier.  See README "Known limitations".
    """

    point_sets: Tuple[Tuple[int, ...], ...]
    evaluation_set: Tuple[int, ...]
    r_polynomials: Tuple[Tuple[int, ...], ...]


@dataclass(frozen=True)
class Opening:
    """Prover response for one (x, y): commitment values cm_i = f_i(x) and witness W."""

    x: int
    y: int
    commitments: Tuple[int, ...]
    witness: int


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    left: int    # W * Z_T(x)
    right: int   # sum_i (cm_i - r_i(x)) y^i Z_{T\S_i}(x)

    def __bool__(self) -> bool:  # allows ``if verifier.verify(...):``
        return self.valid


# --------------------------------------------------------------------------- #
# Prover / Verifier
# --------------------------------------------------------------------------- #

class Prover:
    """Holds the secret polynomials and answers (x, y) queries."""

    def __init__(self, polynomials: Sequence[Sequence[int]], point_sets: Sequence[Sequence[int]],
                 evaluation_set: Sequence[int], *, require_zero_in_point_sets: bool = False):
        polys = [polynomial.as_polynomial(f, f"polynomials[{i}]") for i, f in enumerate(polynomials)]
        self._point_sets, self._evaluation_set = validate_point_sets(
            point_sets, evaluation_set, len(polys), require_zero=require_zero_in_point_sets)
        self._polynomials = polys

        self._r: List[List[int]] = []
        self._quotients: List[List[int]] = []
        for i, (f, s) in enumerate(zip(polys, self._point_sets)):
            r = polynomial.interpolate([(pt, polynomial.evaluate(f, pt)) for pt in s])
            q, rem = polynomial.divmod_poly(polynomial.sub(f, r), polynomial.vanishing_polynomial(s))
            if rem:  # cannot happen if interpolation is correct; never ignore it silently
                raise ProtocolError(f"(f_{i} - r_{i}) is not divisible by Z_S{i}")
            self._r.append(r)
            self._quotients.append(q)

    @property
    def polynomial_count(self) -> int:
        return len(self._polynomials)

    def public_parameters(self) -> PublicParameters:
        return PublicParameters(point_sets=self._point_sets, evaluation_set=self._evaluation_set,
                                r_polynomials=tuple(tuple(r) for r in self._r))

    def commitments(self, x: int) -> Tuple[int, ...]:
        """cm_i = f_i(x) (the participant's share values when x is a share coordinate)."""
        x = field.require_field_element(x, "x")
        return tuple(polynomial.evaluate(f, x) for f in self._polynomials)

    def witness(self, x: int, y: int) -> int:
        """W = h(x) with h = sum_i y^i (f_i - r_i) / Z_{S_i}."""
        x, y = validate_challenge(x, y, self._evaluation_set)
        total, weight = 0, 1
        for q in self._quotients:
            total = (total + weight * polynomial.evaluate(q, x)) % P
            weight = (weight * y) % P
        return total

    def open(self, x: int, y: int) -> Opening:
        x, y = validate_challenge(x, y, self._evaluation_set)  # validate before evaluating anything
        return Opening(x=x, y=y, commitments=self.commitments(x), witness=self.witness(x, y))


class Verifier:
    """Checks W * Z_T(x) == sum_i (cm_i - r_i(x)) y^i Z_{T\\S_i}(x)."""

    def __init__(self, params: PublicParameters):
        r_polys = [list(r) for r in params.r_polynomials]
        self._point_sets, self._evaluation_set = validate_point_sets(
            params.point_sets, params.evaluation_set, len(r_polys))
        self._r = []
        for i, (r, s) in enumerate(zip(r_polys, self._point_sets)):
            r = polynomial.as_polynomial(r, f"r_polynomials[{i}]")
            if polynomial.degree(r) >= len(s):
                raise ValidationError(f"deg r_{i} must be < |S_{i}| = {len(s)}")
            self._r.append(r)
        self._complements = [tuple(v for v in self._evaluation_set if v not in set(s))
                             for s in self._point_sets]

    def verify(self, x: int, y: int, commitments: Sequence[int], witness: int) -> VerificationResult:
        x, y = validate_challenge(x, y, self._evaluation_set)
        cms = field.require_field_elements(commitments, "commitments")
        if len(cms) != len(self._r):
            raise ValidationError(f"expected {len(self._r)} commitment values, got {len(cms)}")
        w = field.require_field_element(witness, "witness")

        left = (w * polynomial.evaluate_vanishing(self._evaluation_set, x)) % P
        right, weight = 0, 1
        for cm, r, comp in zip(cms, self._r, self._complements):
            term = (cm - polynomial.evaluate(r, x)) * polynomial.evaluate_vanishing(comp, x)
            right = (right + weight * term) % P
            weight = (weight * y) % P
        return VerificationResult(valid=left == right, left=left, right=right)

    def verify_opening(self, opening: Opening) -> VerificationResult:
        return self.verify(opening.x, opening.y, opening.commitments, opening.witness)
