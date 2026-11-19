"""Endpoint behaviour, validation and error mapping (real algorithms, no mocks of the core)."""

import json

import pytest

pytest.importorskip("fastapi")

from pcss.config import FIELD_MODULUS, MAX_MESSAGE_BYTES  # noqa: E402

P = FIELD_MODULUS


def _url(task, suffix=""):
    return f"/api/v1/sharing/{task['sharing_id']}{suffix}"


def _share(client, auth, task, user):
    s = client.get(_url(task, "/shares/me"), headers=auth(user)).json()
    return {"x": s["x"], "values": s["values"]}


def _proof(client, auth, task, participant="user_001", **extra):
    r = client.post(_url(task, "/proofs"), json={"participant_id": participant, **extra},
                    headers=auth("dealer_a"))
    assert r.status_code == 201, r.text
    return r.json()


def _inline(proof, **changes):
    data = {"x": proof["x"], "challenge": proof["challenge"], "commitments": proof["commitments"],
            "witness": proof["witness"]}
    data.update(changes)
    return {"proof": data}


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #

def test_create_response_is_non_sensitive(client, auth, app):
    r = client.post("/api/v1/sharing", headers=auth("dealer_a"), json={
        "message": "Hello World", "threshold": 3,
        "participant_ids": ["user_001", "user_002", "user_003", "user_004", "user_005"]})
    assert r.status_code == 201
    task = r.json()
    assert task["status"] == "created" and task["threshold"] == 3 and task["total_shares"] == 5
    assert [p["x"] for p in task["participants"]] == [1, 2, 3, 4, 5]
    assert set(task) == {"sharing_id", "dealer_id", "status", "threshold", "total_shares",
                         "chunk_count", "chunk_size", "original_length", "participants",
                         "public_parameters", "created_at", "distributed_at"}
    from app.storage.models import ShareRecord, TaskSecret, TaskVerificationKey
    with app.state.session_factory() as s:
        secret = s.get(TaskSecret, task["sharing_id"]).polynomials
        r_polys = s.get(TaskVerificationKey, task["sharing_id"]).r_polynomials
        values = [v for rec in s.query(ShareRecord).all() for v in json.loads(rec.share_values)]
    for row in json.loads(secret) + json.loads(r_polys):
        for coeff in row:
            assert coeff not in r.text                   # no polynomial coefficient leaks
    for v in values:
        assert v not in r.text                           # no share value in the create response
    assert "Hello World" not in r.text


@pytest.mark.parametrize("body,code", [
    ({"message": "m", "threshold": 2, "participant_ids": ["user_001", "user_001"]}, "invalid_request"),
    ({"message": "m", "threshold": 2, "participant_ids": ["user_001", "ghost"]}, "invalid_request"),
    ({"message": "m", "threshold": 3, "participant_ids": ["user_001", "user_002"]}, "invalid_input"),
    ({"message": "m", "threshold": 1, "participant_ids": ["user_001", "user_002"]}, "invalid_input"),
    ({"message": "中" * (MAX_MESSAGE_BYTES // 3 + 1), "threshold": 2,
      "participant_ids": ["user_001", "user_002"]}, "invalid_input"),            # byte limit
    ({"message": "m", "threshold": "2", "participant_ids": ["user_001", "user_002"]}, "validation_error"),
    ({"message": "m", "threshold": True, "participant_ids": ["user_001", "user_002"]}, "validation_error"),
    ({"message": "m", "threshold": 2, "participant_ids": ["user_001"]}, "validation_error"),
    ({"message": "m", "threshold": 2}, "validation_error"),
    ({"message": "m", "threshold": 2, "participant_ids": ["user_001", "user_002"],
      "coefficients": [[1]]}, "validation_error"),                               # no manual polynomials
])
def test_create_validation(client, auth, body, code):
    r = client.post("/api/v1/sharing", json=body, headers=auth("dealer_a"))
    assert r.status_code == 422 and r.json()["error"]["code"] == code


def test_validation_errors_do_not_echo_input(client, auth):
    secret = "TOP-SECRET-MESSAGE-123"
    r = client.post("/api/v1/sharing", headers=auth("dealer_a"),
                    json={"message": secret, "threshold": "two", "participant_ids": ["user_001"]})
    assert r.status_code == 422 and secret not in r.text and "input" not in r.json()["error"]["details"][0]


def test_dealer_can_be_a_recipient(client, auth, make_task):
    task = make_task(participants=["dealer_a", "user_001"], threshold=2)
    assert [p["participant_id"] for p in task["participants"]] == ["dealer_a", "user_001"]


# --------------------------------------------------------------------------- #
# Distribute / own share
# --------------------------------------------------------------------------- #

def test_share_unavailable_before_distribution(client, auth, make_task):
    task = make_task(distribute=False)
    r = client.get(_url(task, "/shares/me"), headers=auth("user_001"))
    assert r.status_code == 409


def test_distribute_is_not_repeatable_and_never_regenerates(client, auth, make_task):
    task = make_task(distribute=False)
    first = client.post(_url(task, "/distribute"), headers=auth("dealer_a"))
    assert first.status_code == 200 and first.json()["status"] == "distributed"
    before = client.get(_url(task, "/shares/me"), headers=auth("user_001")).json()
    second = client.post(_url(task, "/distribute"), headers=auth("dealer_a"))
    assert second.status_code == 409 and second.json()["error"]["code"] == "conflict"
    assert client.get(_url(task, "/shares/me"), headers=auth("user_001")).json() == before


def test_own_share_contains_public_metadata(client, auth, make_task):
    task = make_task(message="x" * 40)
    s = client.get(_url(task, "/shares/me"), headers=auth("user_003")).json()
    assert s["sharing_id"] == task["sharing_id"] and s["x"] == 3
    assert s["chunk_count"] == 2 == len(s["values"]) and s["threshold"] == 3
    assert all(0 <= int(v) < P for v in s["values"])


# --------------------------------------------------------------------------- #
# Proofs and verification
# --------------------------------------------------------------------------- #

def test_proof_structure(client, auth, make_task):
    task = make_task()
    proof = _proof(client, auth, task, "user_002", challenge="12345")
    share = _share(client, auth, task, "user_002")
    assert proof["x"] == share["x"] and proof["commitments"] == share["values"]
    assert proof["challenge"] == "12345"
    assert proof["public_parameters"]["evaluation_set"] == [str(P - 1)]
    assert "r_polynomials" not in json.dumps(proof)


def test_proof_requires_distribution(client, auth, make_task):
    task = make_task(distribute=False)
    r = client.post(_url(task, "/proofs"), json={"participant_id": "user_001"}, headers=auth("dealer_a"))
    assert r.status_code == 409


@pytest.mark.parametrize("challenge", ["0", str(P), str(P + 1), "-1", "abc", ""])
def test_invalid_challenge(client, auth, make_task, challenge):
    task = make_task()
    r = client.post(_url(task, "/proofs"), json={"participant_id": "user_001", "challenge": challenge},
                    headers=auth("dealer_a"))
    assert r.status_code == 422


def test_random_challenge_is_in_range(client, auth, make_task):
    task = make_task()
    ys = {int(_proof(client, auth, task)["challenge"]) for _ in range(3)}
    assert all(1 <= y < P for y in ys) and len(ys) == 3


def test_verify_stored_and_inline(client, auth, make_task):
    task = make_task()
    proof = _proof(client, auth, task)
    for body in ({"proof_id": proof["proof_id"]}, _inline(proof)):
        r = client.post(_url(task, "/verify"), json=body, headers=auth("user_001"))
        assert r.status_code == 200 and r.json()["verified"] is True


@pytest.mark.parametrize("field", ["witness", "commitment", "challenge", "x"])
def test_invalid_proof_returns_200_false(client, auth, make_task, field):
    task = make_task(message="m" * 40)                           # 2 chunks: y actually matters
    proof = _proof(client, auth, task)
    if field == "witness":
        body = _inline(proof, witness=str((int(proof["witness"]) + 1) % P))
    elif field == "commitment":
        body = _inline(proof, commitments=[str((int(proof["commitments"][0]) + 1) % P),
                                           *proof["commitments"][1:]])
    elif field == "challenge":
        body = _inline(proof, challenge=str(int(proof["challenge"]) % (P - 1) + 1))
    else:
        body = _inline(proof, x=proof["x"] + 1)                  # proof for x reused at another x
    for user in ("user_001", "dealer_a"):
        r = client.post(_url(task, "/verify"), json=body, headers=auth(user))
        assert r.status_code == 200 and r.json()["verified"] is False
    d = client.post(_url(task, "/verify"), json=body, headers=auth("dealer_a")).json()
    assert d["details"]["left_value"] != d["details"]["right_value"]


def test_single_chunk_challenge_has_no_effect(client, auth, make_task):
    """With one polynomial the only weight is y^0 = 1, so W does not depend on y (a property of the
    retained relation, not an API bug): a proof checked with another y still verifies."""
    task = make_task(message="short")                          # 1 chunk
    proof = _proof(client, auth, task)
    other_y = str(int(proof["challenge"]) % (P - 1) + 1)
    r = client.post(_url(task, "/verify"), json=_inline(proof, challenge=other_y), headers=auth("user_001"))
    assert r.json()["verified"] is True


@pytest.mark.parametrize("change,status", [
    ({"x": P - 1}, 422),                 # x ∈ T: degenerate point, rejected
    ({"challenge": "0"}, 422),           # y = 0 would ignore all but one polynomial
    ({"commitments": []}, 422),
    ({"commitments": ["1", "2"]}, 422),  # wrong count (1 chunk)
    ({"witness": str(P)}, 422),          # not a field element
    ({"x": "1"}, 422),                   # strict int
])
def test_malformed_or_degenerate_verification_input(client, auth, make_task, change, status):
    task = make_task()
    proof = _proof(client, auth, task)
    r = client.post(_url(task, "/verify"), json=_inline(proof, **change), headers=auth("user_001"))
    assert r.status_code == status


@pytest.mark.parametrize("body", [{}, {"proof_id": "a", "proof": {"x": 1, "challenge": "1",
                                                                   "commitments": ["1"], "witness": "1"}}])
def test_verify_requires_exactly_one_source(client, auth, make_task, body):
    task = make_task()
    assert client.post(_url(task, "/verify"), json=body, headers=auth("user_001")).status_code == 422


def test_verify_unknown_proof_id(client, auth, make_task):
    task = make_task()
    r = client.post(_url(task, "/verify"), json={"proof_id": "nope"}, headers=auth("dealer_a"))
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Recovery
# --------------------------------------------------------------------------- #

def test_recover_with_threshold_and_more(client, auth, make_task):
    task = make_task(message="Hello World")
    shares = [_share(client, auth, task, u) for u in ("user_001", "user_002", "user_003", "user_004")]
    for subset in (shares[:3], shares[1:], shares):
        r = client.post(_url(task, "/recover"), json={"shares": subset}, headers=auth("user_001"))
        assert r.status_code == 200 and r.json()["message"] == "Hello World"
        assert r.json()["shares_used"] == len(subset) and r.json()["threshold"] == 3


def test_recover_insufficient(client, auth, make_task):
    task = make_task()
    shares = [_share(client, auth, task, u) for u in ("user_001", "user_002")]
    r = client.post(_url(task, "/recover"), json={"shares": shares}, headers=auth("user_001"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "insufficient_shares"


def test_recover_invalid_shares(client, auth, make_task):
    task = make_task(message="abc")
    good = [_share(client, auth, task, u) for u in ("user_001", "user_002", "user_003")]
    cases = {
        "duplicate_x": [good[0], good[0], good[1]],
        "x_not_issued": [good[0], good[1], {"x": 99, "values": good[2]["values"]}],
        "x_zero": [good[0], good[1], {"x": 0, "values": good[2]["values"]}],
        "value_out_of_field": [good[0], good[1], {"x": good[2]["x"], "values": [str(P)]}],
        "non_decimal_value": [good[0], good[1], {"x": good[2]["x"], "values": ["0x10"]}],
        "wrong_value_count": [good[0], good[1], {"x": good[2]["x"], "values": ["1", "2"]}],
        "empty_values": [good[0], good[1], {"x": good[2]["x"], "values": []}],
    }
    for name, shares in cases.items():
        r = client.post(_url(task, "/recover"), json={"shares": shares}, headers=auth("user_001"))
        assert r.status_code == 422, name


def test_recover_with_modified_share(client, auth, make_task):
    """Well-formed but modified shares: honest outcomes only, never a false 'verified' claim."""
    task = make_task(message="abc")
    good = [_share(client, auth, task, u) for u in ("user_001", "user_002", "user_003", "user_004")]
    bad = dict(good[2], values=[str((int(good[2]["values"][0]) + 1) % P)])
    exactly_k = client.post(_url(task, "/recover"), json={"shares": [good[0], good[1], bad]},
                            headers=auth("user_001"))
    assert exactly_k.status_code == 422 and exactly_k.json()["error"]["code"] == "decoding_failed"
    assert "not a cryptographic" in exactly_k.json()["error"]["message"]
    redundant = client.post(_url(task, "/recover"), json={"shares": [good[0], good[1], good[3], bad]},
                            headers=auth("user_001"))
    assert redundant.status_code == 422 and redundant.json()["error"]["code"] == "inconsistent_shares"


# --------------------------------------------------------------------------- #
# Misc
# --------------------------------------------------------------------------- #

def test_unknown_task_is_404(client, auth):
    r = client.get("/api/v1/sharing/does-not-exist", headers=auth("dealer_a"))
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_unhandled_error_is_generic_500(app, auth, monkeypatch):
    from fastapi.testclient import TestClient

    from app.services import sharing_service

    def boom(*_a, **_k):
        raise RuntimeError("internal detail /secret/path")

    headers = auth("dealer_a")
    monkeypatch.setattr(sharing_service.SharingService, "get", boom)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/v1/sharing/x", headers=headers)
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "internal_error", "message": "Internal server error"}}
    assert "Traceback" not in r.text and "secret/path" not in r.text


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
