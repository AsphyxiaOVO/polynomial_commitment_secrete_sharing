import pytest

from pcss import polynomial as poly
from pcss.config import FIELD_MODULUS, MAX_POLYNOMIAL_LENGTH
from pcss.errors import DuplicatePointError, FieldElementError, NonInvertibleError, ValidationError

P = FIELD_MODULUS


def naive_eval(coeffs, x):
    return sum(c * pow(x, i, P) for i, c in enumerate(coeffs)) % P


def rand_poly(rng, deg):
    c = [rng.randrange(P) for _ in range(deg)] + [rng.randrange(1, P)]
    return c


def test_coefficient_order_is_low_to_high():
    f = [1, 2, 3]  # 1 + 2X + 3X^2
    assert poly.evaluate(f, 10) == 321
    assert poly.to_high_to_low(f) == [3, 2, 1]
    assert poly.from_high_to_low([3, 2, 1]) == f
    assert poly.to_high_to_low([]) == [0]


def test_degree_ignores_leading_zeros():
    assert poly.degree([]) == -1
    assert poly.degree([0, 0]) == -1
    assert poly.degree([5, 0, 0]) == 0
    assert poly.degree([0, 0, 0, 0, 0, 0, 1]) == 6
    assert poly.degree([1, 2, P]) == 1  # P ≡ 0


def test_horner_matches_naive_for_255_bit_values(rng):
    for deg in (0, 1, 5, 31):
        f = rand_poly(rng, deg)
        for _ in range(5):
            x = rng.randrange(P)
            assert poly.evaluate(f, x) == naive_eval(f, x)


def test_mul_add_sub(rng):
    f, g = rand_poly(rng, 4), rand_poly(rng, 3)
    x = rng.randrange(P)
    assert poly.evaluate(poly.mul(f, g), x) == poly.evaluate(f, x) * poly.evaluate(g, x) % P
    assert poly.evaluate(poly.add(f, g), x) == (poly.evaluate(f, x) + poly.evaluate(g, x)) % P
    assert poly.evaluate(poly.sub(f, g), x) == (poly.evaluate(f, x) - poly.evaluate(g, x)) % P
    assert poly.sub(f, f) == []
    assert poly.mul(f, []) == []


@pytest.mark.parametrize("deg_a,deg_b", [(0, 0), (5, 2), (10, 10), (3, 7), (31, 6)])
def test_divmod_identity(rng, deg_a, deg_b):
    a, b = rand_poly(rng, deg_a), rand_poly(rng, deg_b)
    q, r = poly.divmod_poly(a, b)
    assert poly.add(poly.mul(q, b), r) == poly.trim(a)
    assert poly.degree(r) < poly.degree(b)


def test_divmod_exact_division():
    a = poly.mul([P - 1, 1], [P - 2, 1])  # (X-1)(X-2)
    q, r = poly.divmod_poly(a, [P - 1, 1])
    assert q == [P - 2, 1] and r == []


def test_divmod_rejects_zero_divisor():
    with pytest.raises(ValidationError):
        poly.divmod_poly([1, 2], [])
    with pytest.raises(ValidationError):
        poly.divmod_poly([1, 2], [0, 0, P])  # all coefficients ≡ 0


def test_divisor_with_leading_zero_entries_is_normalised():
    q, r = poly.divmod_poly([0, 0, 1], [0, 1, 0, 0])  # X^2 / X
    assert q == [0, 1] and r == []


def test_vanishing_polynomial():
    assert poly.vanishing_polynomial([]) == [1]  # empty product
    z = poly.vanishing_polynomial([0, 3, P - 1])
    for s in (0, 3, P - 1):
        assert poly.evaluate(z, s) == 0
    assert poly.evaluate(z, 5) == poly.evaluate_vanishing([0, 3, P - 1], 5) == 5 * 2 * 6 % P
    assert poly.evaluate_vanishing([], 123) == 1


def test_interpolation_round_trip_255_bit(rng):
    for deg in (0, 1, 4, 15):
        f = rand_poly(rng, deg)
        xs = rng.sample(range(1, 10**6), deg) + [P - 1]  # include a value close to p
        pts = [(x, poly.evaluate(f, x)) for x in xs]
        assert poly.interpolate(pts) == f
        assert poly.lagrange_evaluate(pts, 0) == f[0]
        z = rng.randrange(P)
        assert poly.lagrange_evaluate(pts, z) == poly.evaluate(f, z)


def test_interpolation_rejects_bad_points():
    with pytest.raises(ValidationError):
        poly.interpolate([])
    with pytest.raises(ValidationError):
        poly.lagrange_evaluate([])
    with pytest.raises(DuplicatePointError):
        poly.interpolate([(1, 2), (1, 3)])
    with pytest.raises(DuplicatePointError):
        poly.lagrange_evaluate([(4, 2), (4, 2)])
    with pytest.raises(FieldElementError):
        poly.interpolate([(P, 1), (1, 1)])  # x = p is not canonical (≡ 0)
    with pytest.raises(FieldElementError):
        poly.interpolate([(1, -1)])


def test_duplicate_detection_is_not_a_division_error():
    # Duplicate x must be reported as DuplicatePointError, never as a silent 0 inverse.
    with pytest.raises(DuplicatePointError):
        poly.interpolate([(2, 1), (3, 1), (2, 5)])
    assert not issubclass(DuplicatePointError, NonInvertibleError)


def test_as_polynomial_limits():
    assert poly.as_polynomial([1, 0, 0]) == [1]
    with pytest.raises(ValidationError):
        poly.as_polynomial([1] * (MAX_POLYNOMIAL_LENGTH + 1))
    with pytest.raises(FieldElementError):
        poly.as_polynomial([1, P])
