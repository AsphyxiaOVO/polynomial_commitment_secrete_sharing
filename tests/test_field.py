import pytest

from pcss import field
from pcss.config import CHUNK_SIZE, FIELD_MODULUS
from pcss.errors import FieldElementError, NonInvertibleError, ValidationError

P = FIELD_MODULUS


def test_modulus_is_the_fixed_prime():
    assert P == 2**255 - 19
    assert P.bit_length() == 255
    # Fermat check with a few bases (P is a well-known prime).
    for a in (2, 3, 5, 7, 2**200 + 1):
        assert pow(a, P - 1, P) == 1
    assert 256**CHUNK_SIZE == 2**248 < P


@pytest.mark.parametrize("a", [1, 2, P - 1, 2**254 + 12345, (P + 1) // 2])
def test_inverse(a):
    assert field.mul(a, field.inv(a)) == 1


@pytest.mark.parametrize("a", [0, P, 2 * P, -P])
def test_inverse_of_zero_raises(a):
    with pytest.raises(NonInvertibleError):
        field.inv(a)
    with pytest.raises(ZeroDivisionError):  # NonInvertibleError is a ZeroDivisionError too
        field.div(1, a)


def test_255_bit_arithmetic_matches_python_reference(rng):
    for _ in range(200):
        a, b = rng.randrange(P), rng.randrange(P)
        assert field.add(a, b) == (a + b) % P
        assert field.sub(a, b) == (a - b) % P
        assert field.mul(a, b) == (a * b) % P
        assert field.neg(a) == (-a) % P
        if b:
            assert field.mul(field.div(a, b), b) == a
    assert field.power(3, P - 1) == 1
    assert field.power(5, -1) == field.inv(5)


@pytest.mark.parametrize("value", [0, 1, P - 1])
def test_valid_field_elements(value):
    assert field.require_field_element(value) == value
    assert field.is_field_element(value)


@pytest.mark.parametrize("value", [-1, P, P + 5, 2**300])
def test_out_of_range_values_rejected(value):
    assert not field.is_field_element(value)
    with pytest.raises(FieldElementError):
        field.require_field_element(value)


@pytest.mark.parametrize("value", [True, False, 1.0, "3", None, [1]])
def test_non_integers_rejected(value):
    with pytest.raises(FieldElementError):
        field.require_field_element(value)
    assert isinstance(FieldElementError("x"), ValueError)


def test_reduce_requires_int():
    assert field.reduce(-1) == P - 1
    with pytest.raises(ValidationError):
        field.reduce("5")
