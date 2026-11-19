"""Phase 1 findings about the retained verification relation.

    W(x, y) * Z_T(x) == sum_i (cm_i - r_i(x)) * y^i * Z_{T \\ S_i}(x)

1. The verifier never needs the secret polynomial coefficients: a Verifier
   built only from (S_i, T, r_i) checks openings.
2. BUT the "public" verification parameter r_i is itself derived from f_i:
   r_i = f_i on S_i.  With the legacy rule 0 ∈ S_i, r_i(0) IS the secret.
3. The witness W also leaks: r_i(x) = cm_i - W * Z_{S_i}(x) (one chunk).
   Proof holders therefore learn extra evaluations of f_i, which lowers the
   effective collusion threshold from k to k - |S_i| (or to |S_i| proof
   holders when 0 ∈ S_i).

All values below come from the real algorithms; nothing is mocked.
"""


from pcss import field, polynomial
from pcss.commitment import Prover, PublicParameters, Verifier
from pcss.config import FIELD_MODULUS
from pcss.encoding import decode_message
from pcss.sharing import split_secret
from pcss.vss import DealerSession

P = FIELD_MODULUS


def test_verifier_needs_only_public_parameters():
    session = DealerSession.create("independent verifier", 3, 5, point_sets=[[0, 7]])
    params = session.public_parameters()
    # Simulate sending the parameters over the wire as plain data (no Prover object, no f_i).
    wire = {"point_sets": [list(s) for s in params.point_sets],
            "evaluation_set": list(params.evaluation_set),
            "r_polynomials": [list(r) for r in params.r_polynomials]}
    verifier = Verifier(PublicParameters(point_sets=tuple(map(tuple, wire["point_sets"])),
                                         evaluation_set=tuple(wire["evaluation_set"]),
                                         r_polynomials=tuple(map(tuple, wire["r_polynomials"]))))
    for share in session.shares:
        _, opening = session.open_share(share.x, 424242)
        result = verifier.verify(opening.x, opening.y, list(opening.commitments), opening.witness)
        assert result.valid and result.left == result.right
    assert set(vars(verifier)) == {"_point_sets", "_evaluation_set", "_r", "_complements"}


def test_invalid_proof_fails_with_real_computation():
    session = DealerSession.create("invalid proof", 3, 5, point_sets=[[0, 7]])
    verifier = Verifier(session.public_parameters())
    _, op = session.open_share(2, 99)
    bad = verifier.verify(op.x, op.y, op.commitments, (op.witness + 1) % P)
    assert not bad.valid and bad.left != bad.right


def test_finding_public_r_reveals_secret_when_zero_in_point_set():
    message = "r_i(0) is the secret"
    session = DealerSession.create(message, 4, 6, point_sets=[[0, 7]])   # legacy rule 0 ∈ S_i
    params = session.public_parameters()
    leaked = [polynomial.evaluate(r, 0) for r in params.r_polynomials]
    meta = session.metadata
    assert decode_message(leaked, meta.original_length, meta.chunk_size, meta.chunk_count) == message


def test_finding_witness_reveals_r_at_share_point():
    session = DealerSession.create("w leaks r(x)", 3, 5, point_sets=[[0, 7]])
    share, op = session.open_share(3, 5)
    r = session.public_parameters().r_polynomials[0]
    z_s = polynomial.evaluate_vanishing([0, 7], share.x)
    assert (share.values[0] - op.witness * z_s) % P == polynomial.evaluate(r, share.x)


def test_finding_two_proof_holders_recover_secret_below_threshold_with_zero_rule():
    """k = 4 but only 2 participants (shares + proofs, no r_i) recover the secret when S = {0, 7}."""
    message = "below threshold"
    session = DealerSession.create(message, 4, 6, point_sets=[[0, 7]])
    s = session.metadata
    points = []
    for x in (1, 2):                                   # two colluding participants
        share, op = session.open_share(x, 12345)
        r_at_x = (share.values[0] - op.witness * polynomial.evaluate_vanishing([0, 7], x)) % P
        points.append((x, r_at_x))
    r = polynomial.interpolate(points)                 # deg r < |S| = 2
    assert decode_message([polynomial.evaluate(r, 0)], s.original_length) == message


def test_finding_proofs_lower_threshold_without_zero_rule():
    """S = {t} with t ∉ shares: each proof leaks f(t), an extra share -> k - 1 colluders suffice."""
    t = P - 1
    message = "k-1 suffice"
    session = DealerSession.create(message, 3, 5, point_sets=[[t]], require_zero_in_point_sets=False)
    pts = []
    for x in (1, 2):                                   # only 2 < k = 3 participants
        share, op = session.open_share(x, 777)
        pts.append((x, share.values[0]))
        f_t = (share.values[0] - op.witness * (x - t)) % P
    pts.append((t, f_t))
    secret = polynomial.lagrange_evaluate(pts, 0)
    assert decode_message([secret], session.metadata.original_length) == message


def test_finding_multiple_challenges_separate_chunks():
    """Two proofs at the same x with different y reveal each r_i(x) individually (2 chunks)."""
    session = DealerSession.create("y" * 40, 3, 5, point_sets=[[0, 7]])   # 2 chunks
    x = 4
    share = session.share_for(x)
    zx = polynomial.evaluate_vanishing([0, 7], x)
    eqs = []
    for y in (3, 10):
        _, op = session.open_share(x, y)
        # W * Z_S(x) = sum_i y^i (f_i(x) - r_i(x))  ->  sum_i y^i r_i(x) = sum_i y^i f_i(x) - W Z_S(x)
        rhs = (share.values[0] + y * share.values[1] - op.witness * zx) % P
        eqs.append((y, rhs))
    (y1, b1), (y2, b2) = eqs                            # r0 + y r1 = b
    r1 = (b1 - b2) * field.inv(y1 - y2) % P
    r0 = (b1 - y1 * r1) % P
    params = session.public_parameters()
    assert r0 == polynomial.evaluate(params.r_polynomials[0], x)
    assert r1 == polynomial.evaluate(params.r_polynomials[1], x)


def test_evaluation_consistency_is_not_share_validity():
    """A pass only says (cm, W) fit r_i; it does not prove cm is a point of a degree-(k-1) polynomial."""
    result = split_secret("abc", 3, 5)
    f = list(result.polynomials[0])
    prover = Prover([f], [[0, 7]], [0, 7])
    params = prover.public_parameters()
    x, y = 1, 9
    fake_cm = (result.shares[0].values[0] + 1) % P           # NOT the real share value
    w = (fake_cm - polynomial.evaluate(params.r_polynomials[0], x)) * \
        field.inv(polynomial.evaluate_vanishing([0, 7], x)) % P
    assert Verifier(params).verify(x, y, [fake_cm], w).valid
