"""RBAC + resource-level authorization, including IDOR attempts."""

import pytest

pytest.importorskip("fastapi")

from app.security.authorization import (POLICY, Action, Actor, Role, TaskRelation,  # noqa: E402
                                        ensure_allowed, is_allowed)
from app.errors import NotFoundError, PermissionDeniedError  # noqa: E402

DEALER, PART = Actor("d", Role.DEALER), Actor("u", Role.PARTICIPANT)
OWNER = TaskRelation(is_owner=True, is_recipient=False)
OWNER_RECIPIENT = TaskRelation(is_owner=True, is_recipient=True)
RECIPIENT = TaskRelation(is_owner=False, is_recipient=True)
OUTSIDER = TaskRelation(is_owner=False, is_recipient=False)


# --------------------------------------------------------------------------- #
# Policy unit tests (no HTTP)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("action,actor,relation,allowed", [
    (Action.CREATE_SHARING, DEALER, None, True),
    (Action.CREATE_SHARING, PART, None, False),
    (Action.DISTRIBUTE_SHARES, DEALER, OWNER, True),
    (Action.DISTRIBUTE_SHARES, DEALER, RECIPIENT, False),      # dealer B as a recipient of A's task
    (Action.DISTRIBUTE_SHARES, PART, RECIPIENT, False),
    (Action.VIEW_OWN_SHARE, DEALER, OWNER, False),             # owner but not a recipient
    (Action.VIEW_OWN_SHARE, DEALER, OWNER_RECIPIENT, True),
    (Action.VIEW_OWN_SHARE, PART, RECIPIENT, True),
    (Action.VIEW_OWN_SHARE, PART, OUTSIDER, False),
    (Action.GENERATE_PROOF, DEALER, OWNER, True),
    (Action.GENERATE_PROOF, PART, RECIPIENT, False),
    (Action.GENERATE_PROOF, DEALER, OUTSIDER, False),
    (Action.VERIFY_PROOF, DEALER, OWNER, True),
    (Action.VERIFY_PROOF, PART, RECIPIENT, True),
    (Action.VERIFY_PROOF, PART, OUTSIDER, False),
    (Action.RECOVER_SECRET, DEALER, OWNER, True),
    (Action.RECOVER_SECRET, PART, RECIPIENT, True),
    (Action.RECOVER_SECRET, DEALER, OUTSIDER, False),
])
def test_policy_matrix(action, actor, relation, allowed):
    assert is_allowed(action, actor, relation) is allowed


def test_every_action_has_a_rule():
    assert set(POLICY) == set(Action)


def test_outsiders_get_not_found_members_get_forbidden():
    with pytest.raises(NotFoundError):
        ensure_allowed(Action.VERIFY_PROOF, PART, OUTSIDER)
    with pytest.raises(PermissionDeniedError):
        ensure_allowed(Action.GENERATE_PROOF, PART, RECIPIENT)
    with pytest.raises(PermissionDeniedError):
        ensure_allowed(Action.CREATE_SHARING, PART)


# --------------------------------------------------------------------------- #
# API: role checks
# --------------------------------------------------------------------------- #

def _url(task, suffix=""):
    return f"/api/v1/sharing/{task['sharing_id']}{suffix}"


def test_dealer_can_create_participant_cannot(client, auth):
    body = {"message": "m", "threshold": 2, "participant_ids": ["user_001", "user_002"]}
    assert client.post("/api/v1/sharing", json=body, headers=auth("dealer_a")).status_code == 201
    r = client.post("/api/v1/sharing", json=body, headers=auth("user_001"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "permission_denied"


def test_distribute_permissions(client, auth, make_task):
    task = make_task(distribute=False)
    assert client.post(_url(task, "/distribute"), headers=auth("user_001")).status_code == 403
    assert client.post(_url(task, "/distribute"), headers=auth("dealer_b")).status_code == 404
    assert client.post(_url(task, "/distribute"), headers=auth("user_006")).status_code == 404
    assert client.post(_url(task, "/distribute"), headers=auth("dealer_a")).status_code == 200


def test_participant_sees_only_own_share(client, auth, make_task):
    task = make_task()
    xs = {p["participant_id"]: p["x"] for p in task["participants"]}
    for user in ("user_001", "user_002"):
        r = client.get(_url(task, "/shares/me"), headers=auth(user))
        assert r.status_code == 200
        assert r.json()["participant_id"] == user and r.json()["x"] == xs[user]
    assert (client.get(_url(task, "/shares/me"), headers=auth("user_001")).json()["values"]
            != client.get(_url(task, "/shares/me"), headers=auth("user_002")).json()["values"])


def test_outsider_cannot_see_task_or_share(client, auth, make_task):
    task = make_task()
    for path in ("", "/shares/me"):
        assert client.get(_url(task, path), headers=auth("user_006")).status_code == 404
    assert client.get(_url(task, "/shares/me"), headers=auth("dealer_b")).status_code == 404


def test_dealer_share_only_if_recipient(client, auth, make_task):
    not_recipient = make_task()
    r = client.get(_url(not_recipient, "/shares/me"), headers=auth("dealer_a"))
    assert r.status_code == 403                       # owner, but no share was generated for them
    assert len(not_recipient["participants"]) == 5    # no extra share created for the dealer

    recipient = make_task(participants=["dealer_a", "user_001", "user_002"], threshold=2)
    r = client.get(_url(recipient, "/shares/me"), headers=auth("dealer_a"))
    assert r.status_code == 200 and r.json()["participant_id"] == "dealer_a"


def test_dealer_b_as_recipient_has_participant_rights_only(client, auth, make_task):
    task = make_task(participants=["dealer_b", "user_001", "user_002"], threshold=2)
    assert client.get(_url(task, "/shares/me"), headers=auth("dealer_b")).status_code == 200
    assert client.post(_url(task, "/proofs"), json={"participant_id": "user_001"},
                       headers=auth("dealer_b")).status_code == 403
    assert client.post(_url(task, "/distribute"), headers=auth("dealer_b")).status_code == 403


def test_proof_generation_permissions(client, auth, make_task):
    task = make_task()
    body = {"participant_id": "user_001"}
    assert client.post(_url(task, "/proofs"), json=body, headers=auth("dealer_a")).status_code == 201
    assert client.post(_url(task, "/proofs"), json=body, headers=auth("user_001")).status_code == 403
    assert client.post(_url(task, "/proofs"), json=body, headers=auth("dealer_b")).status_code == 404


def test_verify_permissions_and_role_specific_response(client, auth, make_task):
    task = make_task()
    proof = client.post(_url(task, "/proofs"), json={"participant_id": "user_001"},
                        headers=auth("dealer_a")).json()
    body = {"proof_id": proof["proof_id"]}
    d = client.post(_url(task, "/verify"), json=body, headers=auth("dealer_a"))
    u = client.post(_url(task, "/verify"), json=body, headers=auth("user_001"))
    assert d.status_code == u.status_code == 200
    assert d.json()["verified"] is u.json()["verified"] is True        # same mathematical result
    assert d.json()["details"]["left_value"] == d.json()["details"]["right_value"]
    assert u.json() == {"verified": True, "message": "Verification successful"}
    assert client.post(_url(task, "/verify"), json=body, headers=auth("user_006")).status_code == 404


def test_recover_permissions(client, auth, make_task):
    task = make_task(message="who may recover?")
    shares = []
    for user in ("user_001", "user_002", "user_003"):
        s = client.get(_url(task, "/shares/me"), headers=auth(user)).json()
        shares.append({"x": s["x"], "values": s["values"]})
    for caller in ("dealer_a", "user_004"):
        r = client.post(_url(task, "/recover"), json={"shares": shares}, headers=auth(caller))
        assert r.status_code == 200 and r.json()["message"] == "who may recover?"
    for outsider in ("user_006", "dealer_b"):
        r = client.post(_url(task, "/recover"), json={"shares": shares}, headers=auth(outsider))
        assert r.status_code == 404


# --------------------------------------------------------------------------- #
# IDOR attempts
# --------------------------------------------------------------------------- #

def test_idor_share_lookup_ignores_client_supplied_identity(client, auth, make_task):
    task = make_task()
    own = client.get(_url(task, "/shares/me"), headers=auth("user_001")).json()
    for query in ("?participant_id=user_002", "?user_id=user_002", "?x=2"):
        r = client.get(_url(task, "/shares/me") + query, headers=auth("user_001"))
        assert r.status_code == 200 and r.json() == own


def test_idor_other_task_id(client, auth, make_task):
    mine = make_task(participants=["user_001", "user_002"], threshold=2)
    theirs = make_task(participants=["user_003", "user_004"], threshold=2, dealer="dealer_b")
    # user_001 swaps in a task id they are not part of
    assert client.get(_url(theirs, "/shares/me"), headers=auth("user_001")).status_code == 404
    # dealer_a swaps in dealer_b's task id
    for method, path, body in [("post", "/distribute", None),
                               ("post", "/proofs", {"participant_id": "user_003"}),
                               ("get", "", None)]:
        r = getattr(client, method)(_url(theirs, path), headers=auth("dealer_a"),
                                    **({"json": body} if body else {}))
        assert r.status_code == 404
    # nonexistent id looks exactly like a forbidden one
    ghost = {"sharing_id": "0" * 32}
    assert client.get(_url(ghost, "/shares/me"), headers=auth("user_001")).status_code == 404
    assert mine["sharing_id"] != theirs["sharing_id"]


def test_idor_proof_of_another_participant(client, auth, make_task):
    task = make_task()
    proof_b = client.post(_url(task, "/proofs"), json={"participant_id": "user_002"},
                          headers=auth("dealer_a")).json()
    r = client.post(_url(task, "/verify"), json={"proof_id": proof_b["proof_id"]},
                    headers=auth("user_001"))
    assert r.status_code == 404                       # cannot use (or probe) B's stored proof


def test_idor_proof_id_from_other_task(client, auth, make_task):
    t1, t2 = make_task(), make_task()
    proof = client.post(_url(t1, "/proofs"), json={"participant_id": "user_001"},
                        headers=auth("dealer_a")).json()
    r = client.post(_url(t2, "/verify"), json={"proof_id": proof["proof_id"]}, headers=auth("dealer_a"))
    assert r.status_code == 404


def test_dealer_cannot_prove_for_non_recipient(client, auth, make_task):
    task = make_task(participants=["user_001", "user_002"], threshold=2)
    r = client.post(_url(task, "/proofs"), json={"participant_id": "user_003"}, headers=auth("dealer_a"))
    assert r.status_code == 422
