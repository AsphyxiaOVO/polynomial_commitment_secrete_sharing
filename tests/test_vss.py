import itertools

import pytest

from pcss import DealerSession, Verifier, recover_message
from pcss.config import FIELD_MODULUS
from pcss.errors import ValidationError

P = FIELD_MODULUS

MESSAGES = ["", "a", "x" * 31, "多项式承诺 🌸 ポリノミアル " * 4, "\x00lead\x00"]


@pytest.mark.parametrize("message", MESSAGES)
def test_end_to_end(message):
    session = DealerSession.create(message, threshold=3, share_count=5,
                                   point_sets=[[0, 7, 9]])
    verifier = Verifier(session.public_parameters())
    for share in session.shares:
        assert share.x not in (0, 7, 9)                       # shares avoid T
        got, opening = session.open_share(share.x, y=31337)
        assert got == share and opening.commitments == share.values
        assert verifier.verify_opening(opening).valid
    for subset in itertools.combinations(session.shares, 3):
        assert recover_message(subset, session.metadata) == message


def test_point_set_broadcast_and_default_T():
    session = DealerSession.create("y" * 70, 2, 3, point_sets=[[0, 4]])
    params = session.public_parameters()
    assert session.metadata.chunk_count == 3
    assert params.point_sets == ((0, 4),) * 3
    assert params.evaluation_set == (0, 4)


def test_per_chunk_point_sets_and_explicit_T():
    session = DealerSession.create("y" * 40, 2, 3, point_sets=[[0, 4], [0, 5, 6]],
                                   evaluation_set=[0, 4, 5, 6, 20])
    assert [s.x for s in session.shares] == [1, 2, 3]
    verifier = Verifier(session.public_parameters())
    assert verifier.verify_opening(session.open_share(2, 9)[1]).valid


def test_wrong_number_of_point_sets():
    with pytest.raises(ValidationError):
        DealerSession.create("y" * 70, 2, 3, point_sets=[[0, 4], [0, 5]])


def test_legacy_zero_rule_is_enforced_by_default():
    with pytest.raises(ValidationError, match="contain 0"):
        DealerSession.create("abc", 2, 3, point_sets=[[4, 5]])
    s = DealerSession.create("abc", 2, 3, point_sets=[[4, 5]],
                             require_zero_in_point_sets=False)
    assert Verifier(s.public_parameters()).verify_opening(s.open_share(1, 3)[1]).valid


def test_share_x_in_T_rejected():
    with pytest.raises(ValidationError, match="excluded"):
        DealerSession.create("abc", 2, 2, point_sets=[[0, 7]], x_coordinates=[1, 7])


def test_open_unknown_share_and_random_y():
    session = DealerSession.create("abc", 2, 2, point_sets=[[0]])
    with pytest.raises(ValidationError):
        session.open_share(99)
    _, opening = session.open_share(1)        # y drawn from [1, p-1]
    assert 1 <= opening.y < P
    assert Verifier(session.public_parameters()).verify_opening(opening).valid


def test_threshold_parameters_validated_before_work():
    with pytest.raises(ValidationError):
        DealerSession.create("abc", 1, 3, point_sets=[[0]])
    with pytest.raises(ValidationError):
        DealerSession.create("abc", 4, 3, point_sets=[[0]])


def test_tampered_share_value_fails_verification_with_honest_witness():
    session = DealerSession.create("verify me", 3, 4, point_sets=[[0, 7]])
    verifier = Verifier(session.public_parameters())
    share, opening = session.open_share(3, 5)
    tampered = [(share.values[0] + 1) % P]
    assert not verifier.verify(3, 5, tampered, opening.witness).valid
