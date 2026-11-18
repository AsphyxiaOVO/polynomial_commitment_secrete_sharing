import pytest

from pcss import fri, polynomial
from pcss.config import FIELD_MODULUS, MAX_POLYNOMIAL_LENGTH
from pcss.errors import FieldElementError, ValidationError
from pcss.sharing import split_secret

P = FIELD_MODULUS


def test_split_even_odd():
    even, odd = fri.split_even_odd([1, 2, 3, 4, 5])
    assert even == [1, 3, 5] and odd == [2, 4]


def test_fold_definition():
    # f = 1 + 2X + 3X^2 + 4X^3 -> g(Y) = (1 + 3Y) + a(2 + 4Y)
    assert fri.fold([1, 2, 3, 4], 6) == [13, 27]


@pytest.mark.parametrize("deg", [1, 2, 5, 6, 11, 40])
def test_fold_consistency_relation(rng, deg):
    f = [rng.randrange(P) for _ in range(deg)] + [rng.randrange(1, P)]
    alpha = rng.randrange(P)
    g = fri.fold(f, alpha)
    assert polynomial.degree(g) <= deg // 2
    for _ in range(5):
        assert fri.fold_consistency_holds(f, g, alpha, rng.randrange(1, P))


def test_reduce_degree_stops_at_max_degree(rng):
    f = [rng.randrange(1, P) for _ in range(30)]       # degree 29
    red = fri.reduce_degree(f, alpha=6, max_degree=5)
    assert red.degrees == [29, 14, 7, 3]
    assert polynomial.degree(red.result) <= 5
    assert len(red.rounds) == 3
    # A polynomial already within the bound is unchanged.
    small = fri.reduce_degree([1, 2, 3, 4, 5, 6], max_degree=5)
    assert small.rounds == () and small.result == (1, 2, 3, 4, 5, 6)


def test_degree_6_polynomial_is_folded():
    """Legacy bug: high-to-low list + appended constant made a degree-6 polynomial look like degree 5."""
    red = fri.reduce_degree([0, 6, 5, 4, 3, 2, 1], max_degree=5)
    assert red.degrees[0] == 6 and len(red.rounds) == 1


def test_reduce_degree_terminates_for_max_input(rng):
    f = [rng.randrange(1, P) for _ in range(MAX_POLYNOMIAL_LENGTH)]
    red = fri.reduce_degree(f, max_degree=0)
    assert polynomial.degree(red.result) <= 0
    assert len(red.rounds) <= 10


def test_reduce_degree_input_validation():
    with pytest.raises(ValidationError):
        fri.reduce_degree([1] * (MAX_POLYNOMIAL_LENGTH + 1))
    with pytest.raises(FieldElementError):
        fri.reduce_degree([1, 2], alpha=P)
    with pytest.raises(ValidationError):
        fri.reduce_degree([1, 2], max_degree=-1)
    with pytest.raises(ValidationError):
        fri.fold_consistency_holds([1, 2], [1], 3, 0)


def test_fri_breaks_shamir_threshold(randbelow):
    """Documents why FRI is NOT applied to the sharing polynomials.

    For k = 8 the sharing polynomial has degree 7.  After one fold:
    degree 3 (only 4 points determine it) and the constant term changes.
    """
    result = split_secret("FRI vs threshold", 8, 8, randbelow=randbelow)
    f = list(result.polynomials[0])
    assert polynomial.degree(f) == 7
    g = fri.fold(f, fri.FRI_DEFAULT_ALPHA)
    assert polynomial.degree(g) == 3 < result.metadata.threshold - 1
    assert g[0] == (f[0] + 6 * f[1]) % P != f[0]
