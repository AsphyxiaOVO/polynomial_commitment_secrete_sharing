import itertools
from dataclasses import replace

import pytest

from pcss import DealerSession, polynomial
from pcss.config import FIELD_MODULUS, MAX_SHARE_COUNT, MAX_THRESHOLD
from pcss.errors import (DecodingError, DuplicatePointError, FieldElementError,
                         InconsistentSharesError, InsufficientSharesError, ValidationError)
from pcss.sharing import (Share, SharingMetadata, build_sharing_polynomial, default_x_coordinates,
                          random_sharing_polynomial, recover_constants, recover_message, split_secret,
                          split_secret_with_coefficients,
                          validate_sharing_parameters)

P = FIELD_MODULUS
MSG = "门限秘密分享 threshold secret sharing 🔑 " * 3


# --------------------------------------------------------------------------- #
# A.1 / A.2 parameter validation
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("k,n", [(2, 2), (2, 5), (5, 5), (MAX_THRESHOLD, MAX_SHARE_COUNT)])
def test_valid_parameters(k, n):
    validate_sharing_parameters(k, n)


@pytest.mark.parametrize("k,n", [
    (1, 5),                          # k >= 2
    (0, 5), (-3, 5),
    (4, 3),                          # n >= k
    (MAX_THRESHOLD + 1, 100),        # resource limit
    (2, MAX_SHARE_COUNT + 1),
    (2, P),                          # n < p
    (True, 5), (2.0, 5), ("3", 5),   # types
])
def test_invalid_parameters(k, n):
    with pytest.raises(ValidationError):
        validate_sharing_parameters(k, n)


# --------------------------------------------------------------------------- #
# A.1 degree is fixed to k - 1 by the system
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("k", [2, 3, 7, MAX_THRESHOLD])
def test_generated_polynomials_have_degree_exactly_k_minus_1(k):
    result = split_secret(MSG, k, k + 2)
    assert result.metadata.threshold == k and result.metadata.degree == k - 1
    assert len(result.polynomials) == result.metadata.chunk_count
    for f in result.polynomials:
        assert polynomial.degree(f) == k - 1


def test_default_sharing_uses_secrets_module(monkeypatch):
    """All coefficients come from secrets.randbelow; leading coefficient is forced into [1, p-1]."""
    import pcss.sharing as sharing_module
    calls = []

    def fake_randbelow(n):
        calls.append(n)
        return 0          # worst case: CSPRNG returns 0 for everything

    monkeypatch.setattr(sharing_module.secrets, "randbelow", fake_randbelow)
    f = random_sharing_polynomial(42, 4)
    assert f == [42, 0, 0, 1]                # leading coefficient still non-zero
    assert calls == [P, P, P - 1]            # k - 2 middle draws + 1 leading draw


def test_core_never_imports_random_module():
    import pathlib
    import pcss
    for path in pathlib.Path(pcss.__file__).parent.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "import random" not in text and "from random" not in text, path.name


def test_each_chunk_gets_an_independent_polynomial():
    result = split_secret("same" * 40, 3, 3)           # 160 bytes -> 6 chunks, identical content pattern
    non_constant = [f[1:] for f in result.polynomials]
    assert len(set(non_constant)) == len(non_constant)  # no coefficient vector reused


def test_user_coefficients_must_match_threshold():
    assert build_sharing_polynomial(7, 3, [1, 2]) == [7, 1, 2]
    with pytest.raises(ValidationError):
        build_sharing_polynomial(7, 3, [1])             # degree 1 != k - 1
    with pytest.raises(ValidationError):
        build_sharing_polynomial(7, 3, [1, 2, 3])       # degree 3 != k - 1
    with pytest.raises(ValidationError):
        build_sharing_polynomial(7, 3, [1, 0])          # leading 0 -> degree < k - 1
    with pytest.raises(FieldElementError):
        build_sharing_polynomial(7, 3, [1, P])
    with pytest.raises(ValidationError):
        split_secret_with_coefficients("abc", 3, 4, [[1, 2], [3, 4]])  # 1 chunk, 2 lists


def test_default_api_has_no_coefficient_parameter():
    import inspect
    assert "coefficients" not in inspect.signature(split_secret).parameters
    assert "coefficients" not in inspect.signature(DealerSession.create).parameters


def test_deterministic_coefficients_mode():
    result = split_secret_with_coefficients("abc", 3, 3, [[5, 9]])
    secret = result.polynomials[0][0]
    assert result.polynomials[0] == (secret, 5, 9)
    assert result.shares[0].values[0] == (secret + 5 * 1 + 9 * 1) % P


# --------------------------------------------------------------------------- #
# Recovery
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("k,n", [(2, 3), (3, 5), (4, 4)])
def test_any_k_shares_recover(k, n):
    result = split_secret(MSG, k, n)
    for subset in itertools.combinations(result.shares, k):
        assert recover_message(subset, result.metadata) == MSG
    assert recover_message(result.shares, result.metadata) == MSG   # all n (consistency checked)


def test_k_minus_1_shares_are_rejected():
    result = split_secret(MSG, 4, 6)
    with pytest.raises(InsufficientSharesError, match="Insufficient shares"):
        recover_message(result.shares[:3], result.metadata)
    with pytest.raises(InsufficientSharesError):
        recover_message([], result.metadata)


def test_threshold_comes_from_metadata_not_from_share_count():
    """k-1 shares interpolate *some* polynomial of degree k-2; its constant is not the secret.

    The legacy recovery silently returned such a wrong value.  Now recovery
    refuses, because the threshold stored at sharing time is 4.
    """
    result = split_secret("x", 4, 6)
    pts = [(s.x, s.values[0]) for s in result.shares[:3]]
    assert polynomial.lagrange_evaluate(pts, 0) != result.polynomials[0][0]
    with pytest.raises(InsufficientSharesError):
        recover_constants(result.shares[:3], result.metadata)


def test_duplicate_x_rejected():
    result = split_secret(MSG, 3, 5)
    s = result.shares
    with pytest.raises(DuplicatePointError):
        recover_message([s[0], s[1], s[0]], result.metadata)


def test_zero_x_rejected():
    result = split_secret(MSG, 2, 3)
    fake = Share(x=0, values=result.shares[0].values)
    with pytest.raises(ValidationError, match="0"):
        recover_message([fake, result.shares[1]], result.metadata)
    with pytest.raises(ValidationError):
        split_secret(MSG, 2, 2, x_coordinates=[0, 1])


@pytest.mark.parametrize("bad_value", [-1, P, P + 1, 1.5, True])
def test_share_values_must_be_field_elements(bad_value):
    result = split_secret("abc", 2, 3)
    bad = Share(x=result.shares[0].x, values=(bad_value,))
    with pytest.raises(ValidationError):
        recover_message([bad, result.shares[1]], result.metadata)


def test_share_x_must_be_field_element():
    result = split_secret("abc", 2, 3)
    bad = Share(x=P + 1, values=result.shares[0].values)  # P + 1 ≡ 1 would collide / wrap
    with pytest.raises(FieldElementError):
        recover_message([bad, result.shares[1]], result.metadata)


def test_share_must_have_chunk_count_values():
    result = split_secret("x" * 40, 2, 3)  # 2 chunks
    short = Share(x=result.shares[0].x, values=result.shares[0].values[:1])
    with pytest.raises(ValidationError, match="chunk_count"):
        recover_message([short, result.shares[1]], result.metadata)


def test_more_shares_than_issued_rejected():
    result = split_secret("abc", 2, 2)
    extra = Share(x=99, values=result.shares[0].values)
    with pytest.raises(ValidationError):
        recover_message([*result.shares, extra], result.metadata)


def test_inconsistent_extra_share_detected():
    result = split_secret(MSG, 3, 5)
    s = list(result.shares)
    v = list(s[4].values)
    v[1] = (v[1] + 1) % P
    s[4] = Share(x=s[4].x, values=tuple(v))
    with pytest.raises(InconsistentSharesError):
        recover_message(s, result.metadata)
    # Without the tampered share the remaining shares still recover correctly.
    assert recover_message(s[:4], result.metadata) == MSG


def test_tampering_with_exactly_k_shares_is_not_detected_by_recovery():
    """Documented limitation: with exactly k shares, recovery has no redundancy.

    A modified share yields a different constant.  Usually the decoder notices
    (out-of-range chunk / non-zero padding / invalid UTF-8), but recovery
    itself cannot *guarantee* detection.
    """
    result = split_secret("abc", 2, 3)
    s0, s1 = result.shares[:2]
    tampered = Share(x=s0.x, values=((s0.values[0] + 1) % P,))
    constants = recover_constants([tampered, s1], result.metadata)
    assert constants[0] != result.polynomials[0][0]
    with pytest.raises(DecodingError):
        recover_message([tampered, s1], result.metadata)


def test_metadata_validation_and_round_trip():
    result = split_secret(MSG, 3, 5)
    meta = result.metadata
    assert SharingMetadata.from_dict(meta.to_dict()) == meta
    assert Share.from_dict(result.shares[0].to_dict()) == result.shares[0]
    with pytest.raises(ValidationError, match="missing"):
        SharingMetadata.from_dict({"threshold": 3})
    for bad in ([], "meta", None):
        with pytest.raises(ValidationError):
            SharingMetadata.from_dict(bad)
        with pytest.raises(ValidationError):
            Share.from_dict(bad)
    with pytest.raises(ValidationError):
        Share.from_dict({"x": 1})
    with pytest.raises(ValidationError):
        Share.from_dict({"x": 1, "values": 5})
    with pytest.raises(ValidationError):
        recover_message(result.shares, replace(meta, chunk_count=meta.chunk_count + 1))
    with pytest.raises(ValidationError):
        recover_message(result.shares, replace(meta, threshold=1))
    with pytest.raises(ValidationError):
        recover_message(result.shares, replace(meta, threshold=6))  # n < k


def test_x_coordinate_selection():
    assert default_x_coordinates(3) == [1, 2, 3]
    assert default_x_coordinates(3, excluded=[0, 2, 5]) == [1, 3, 4]
    result = split_secret("abc", 2, 3, x_coordinates=[P - 1, 10, 2**200])
    assert [s.x for s in result.shares] == [P - 1, 10, 2**200]
    assert recover_message(result.shares[::2], result.metadata) == "abc"
    with pytest.raises(ValidationError):
        split_secret("abc", 2, 3, x_coordinates=[1, 2])          # count != n
    with pytest.raises(DuplicatePointError):
        split_secret("abc", 2, 2, x_coordinates=[5, 5])
    with pytest.raises(ValidationError):
        split_secret("abc", 2, 2, x_coordinates=[5, 6], excluded_x=[6])


def test_empty_message_sharing():
    result = split_secret("", 2, 3)
    assert result.metadata.chunk_count == 1 and result.metadata.original_length == 0
    assert recover_message(result.shares[1:], result.metadata) == ""


def test_chunk_count_share_count_threshold_are_independent():
    msg = "x" * 100                     # 4 chunks
    result = split_secret(msg, 3, 7)
    meta = result.metadata
    assert (meta.chunk_count, meta.share_count, meta.threshold) == (4, 7, 3)
    assert len(result.shares) == 7
    assert all(len(s.values) == 4 for s in result.shares)
