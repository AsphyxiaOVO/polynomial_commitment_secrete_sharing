import pytest

from pcss import field, polynomial
from pcss.commitment import Prover, PublicParameters, Verifier, validate_point_sets
from pcss.config import FIELD_MODULUS, MAX_POINT_SET_SIZE
from pcss.errors import DuplicatePointError, FieldElementError, ValidationError

P = FIELD_MODULUS


def rand_poly(rng, deg):
    return [rng.randrange(P) for _ in range(deg)] + [rng.randrange(1, P)]


@pytest.fixture
def setup(rng):
    """Three polynomials of different degrees with overlapping point sets."""
    polys = [rand_poly(rng, 4), rand_poly(rng, 2), rand_poly(rng, 7)]
    point_sets = [[0, 3], [0, 3, 8], [0, 8, 11, 12]]
    T = [0, 3, 8, 11, 12]
    prover = Prover(polys, point_sets, T, require_zero_in_point_sets=True)
    verifier = Verifier(prover.public_parameters())
    return polys, point_sets, T, prover, verifier


# --------------------------------------------------------------------------- #
# Correctness
# --------------------------------------------------------------------------- #

def test_honest_openings_verify(setup, rng):
    *_, prover, verifier = setup
    for _ in range(20):
        x = rng.randrange(13, P)
        y = rng.randrange(1, P)
        result = verifier.verify_opening(prover.open(x, y))
        assert result.valid and result.left == result.right


def test_r_polynomials_interpolate_f_on_S(setup):
    polys, point_sets, _, prover, _ = setup
    params = prover.public_parameters()
    for f, s, r in zip(polys, point_sets, params.r_polynomials):
        assert polynomial.degree(r) < len(s)
        for pt in s:
            assert polynomial.evaluate(r, pt) == polynomial.evaluate(f, pt)


def test_commitments_are_evaluations(setup):
    polys, *_, prover, _ = setup
    assert prover.commitments(99) == tuple(polynomial.evaluate(f, 99) for f in polys)


def test_witness_matches_explicit_formula(setup):
    polys, point_sets, _, prover, _ = setup
    x, y = 1234567, 89
    h = []
    for i, (f, s) in enumerate(zip(polys, point_sets)):
        r = polynomial.interpolate([(pt, polynomial.evaluate(f, pt)) for pt in s])
        q, rem = polynomial.divmod_poly(polynomial.sub(f, r), polynomial.vanishing_polynomial(s))
        assert rem == []
        h = polynomial.add(h, polynomial.scale(q, pow(y, i, P)))
    assert prover.witness(x, y) == polynomial.evaluate(h, x)


def test_point_set_equal_to_T_gives_empty_complement():
    # S_0 == T -> Z_{T\S_0} = 1 (legacy code raised IndexError on the empty product).
    f = [5, 6, 7, 8]
    prover = Prover([f], [[0, 1, 2]], [0, 1, 2])
    verifier = Verifier(prover.public_parameters())
    assert verifier.verify_opening(prover.open(10, 3)).valid


def test_point_set_larger_than_degree_gives_zero_witness():
    f = [1, 2]                         # degree 1, |S| = 3 -> r = f, quotient 0
    prover = Prover([f], [[0, 4, 5]], [0, 4, 5])
    assert prover.public_parameters().r_polynomials[0] == (1, 2)
    assert prover.witness(9, 2) == 0
    assert Verifier(prover.public_parameters()).verify_opening(prover.open(9, 2)).valid


# --------------------------------------------------------------------------- #
# Wrong witnesses / commitments are rejected
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("delta", [1, 2, P - 1, 2**200])
def test_wrong_witness_rejected(setup, delta):
    *_, prover, verifier = setup
    x, y = 1000, 77
    op = prover.open(x, y)
    assert not verifier.verify(x, y, op.commitments, (op.witness + delta) % P).valid


@pytest.mark.parametrize("index", [0, 1, 2])
def test_wrong_commitment_with_honest_witness_rejected(setup, index):
    """Every polynomial participates: y != 0 and x ∉ T make each weight non-zero."""
    *_, prover, verifier = setup
    x, y = 1000, 77
    op = prover.open(x, y)
    cms = list(op.commitments)
    cms[index] = (cms[index] + 1) % P
    assert not verifier.verify(x, y, cms, op.witness).valid


def test_witness_for_other_challenge_rejected(setup):
    *_, prover, verifier = setup
    x = 1000
    w_other_y = prover.witness(x, 78)
    assert not verifier.verify(x, 77, prover.commitments(x), w_other_y).valid
    w_other_x = prover.witness(1001, 77)
    assert not verifier.verify(x, 77, prover.commitments(x), w_other_x).valid


def test_forged_consistent_pair_is_accepted_documented_limitation(setup):
    """The scheme is NOT a binding commitment.

    Anyone who knows the public r_i can pick arbitrary cm' and solve
    W' = RHS / Z_T(x).  The pair passes.  This test pins down that limitation
    so that the README does not over-claim tamper detection.
    """
    _, point_sets, T, prover, verifier = setup
    params = prover.public_parameters()
    x, y = 1000, 77
    fake_cms = [111, 222, 333]
    rhs = 0
    for i, (cm, r, s) in enumerate(zip(fake_cms, params.r_polynomials, point_sets)):
        comp = [t for t in T if t not in s]
        rhs += (cm - polynomial.evaluate(r, x)) * pow(y, i, P) * polynomial.evaluate_vanishing(comp, x)
    fake_w = rhs * field.inv(polynomial.evaluate_vanishing(T, x)) % P
    assert verifier.verify(x, y, fake_cms, fake_w).valid
    assert tuple(fake_cms) != prover.commitments(x)


# --------------------------------------------------------------------------- #
# Degenerate challenges
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("x", [0, 3, 8, 11, 12])
def test_x_in_T_rejected(setup, x):
    """For x ∈ T both sides are 0 for ANY witness, so verification would be meaningless."""
    *_, prover, verifier = setup
    with pytest.raises(ValidationError, match="T"):
        prover.witness(x, 5)
    with pytest.raises(ValidationError, match="T"):
        verifier.verify(x, 5, [1, 2, 3], 123456)


def test_why_x_in_T_is_degenerate(setup):
    """Show the legacy behaviour: at x ∈ T the equation holds for a random witness."""
    polys, point_sets, T, prover, _ = setup
    x, y, bogus_w = 8, 5, 987654321
    params = prover.public_parameters()
    left = bogus_w * polynomial.evaluate_vanishing(T, x) % P
    right = sum((polynomial.evaluate(f, x) - polynomial.evaluate(r, x)) * pow(y, i, P)
                * polynomial.evaluate_vanishing([t for t in T if t not in s], x)
                for i, (f, r, s) in enumerate(zip(polys, params.r_polynomials, point_sets))) % P
    assert left == right == 0


@pytest.mark.parametrize("y", [0, P, -1])
def test_bad_challenge_rejected(setup, y):
    *_, prover, verifier = setup
    with pytest.raises(ValidationError):
        prover.witness(1000, y)
    with pytest.raises(ValidationError):
        verifier.verify(1000, y, [1, 2, 3], 1)


def test_why_y_zero_is_degenerate(setup):
    """With y = 0 a wrong commitment for polynomial i >= 1 would go unnoticed."""
    polys, point_sets, T, prover, _ = setup
    x = 1000
    params = prover.public_parameters()
    cms = list(prover.commitments(x))
    cms[2] = (cms[2] + 1) % P
    # Recompute both sides by hand with y = 0: only i = 0 contributes (0^0 = 1, 0^i = 0).
    q0 = polynomial.divmod_poly(polynomial.sub(polys[0], list(params.r_polynomials[0])),
                                polynomial.vanishing_polynomial(point_sets[0]))[0]
    w0 = polynomial.evaluate(q0, x)
    left = w0 * polynomial.evaluate_vanishing(T, x) % P
    right = (cms[0] - polynomial.evaluate(params.r_polynomials[0], x)) * \
        polynomial.evaluate_vanishing([t for t in T if t not in point_sets[0]], x) % P
    assert left == right  # tampered cms[2] is invisible when y = 0


def test_commitment_count_and_range(setup):
    *_, prover, verifier = setup
    op = prover.open(1000, 7)
    with pytest.raises(ValidationError):
        verifier.verify(1000, 7, op.commitments[:2], op.witness)
    with pytest.raises(FieldElementError):
        verifier.verify(1000, 7, [*op.commitments[:2], P], op.witness)
    with pytest.raises(FieldElementError):
        verifier.verify(1000, 7, op.commitments, P)


# --------------------------------------------------------------------------- #
# Point-set validation
# --------------------------------------------------------------------------- #

def test_point_set_must_be_subset_of_T():
    with pytest.raises(ValidationError, match="subset"):
        Prover([[1, 2]], [[0, 5]], [0, 1])


def test_empty_sets_rejected():
    with pytest.raises(ValidationError):
        Prover([[1, 2]], [[]], [0])
    with pytest.raises(ValidationError):
        Prover([[1, 2]], [[0]], [])
    with pytest.raises(ValidationError):
        Prover([], [], [0])


def test_duplicate_points_rejected():
    with pytest.raises(DuplicatePointError):
        Prover([[1, 2]], [[0, 0]], [0, 1])
    with pytest.raises(DuplicatePointError):
        Prover([[1, 2]], [[0]], [0, 1, 1])


def test_point_set_count_must_match_polynomials():
    with pytest.raises(ValidationError):
        Prover([[1], [2]], [[0]], [0])


def test_point_set_size_limit_and_zero_rule():
    big = list(range(MAX_POINT_SET_SIZE + 1))
    with pytest.raises(ValidationError):
        validate_point_sets([big], big, 1)
    with pytest.raises(ValidationError, match="contain 0"):
        validate_point_sets([[1, 2]], [1, 2], 1, require_zero=True)
    validate_point_sets([[1, 2]], [1, 2], 1)  # allowed when the legacy rule is off


def test_verifier_rejects_inconsistent_public_parameters():
    with pytest.raises(ValidationError):
        Verifier(PublicParameters(point_sets=((0, 1),), evaluation_set=(0, 1),
                                  r_polynomials=((1, 2, 3),)))  # deg r >= |S|
    with pytest.raises(ValidationError):
        Verifier(PublicParameters(point_sets=((0, 2),), evaluation_set=(0, 1),
                                  r_polynomials=((1,),)))       # S ⊄ T
