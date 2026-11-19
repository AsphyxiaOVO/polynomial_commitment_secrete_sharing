"""End-to-end flows through the HTTP API with the real algorithms (no mocks)."""

import logging

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

PARTICIPANTS = ["user_001", "user_002", "user_003", "user_004", "user_005"]


def _login(client, user, password):
    r = client.post("/api/v1/auth/login", data={"username": user, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _full_flow(client, passwords, message):
    # 2. dealer login
    dealer = _login(client, "dealer_a", passwords["dealer_a"])
    # 3. dealer creates a 3-of-5 sharing
    r = client.post("/api/v1/sharing", headers=dealer,
                    json={"message": message, "threshold": 3, "participant_ids": PARTICIPANTS})
    assert r.status_code == 201
    sid = r.json()["sharing_id"]
    base = f"/api/v1/sharing/{sid}"
    # 4. distribute
    assert client.post(f"{base}/distribute", headers=dealer).json()["status"] == "distributed"
    # 5. participant A logs in and reads their own share
    a = _login(client, "user_001", passwords["user_001"])
    share_a = client.get(f"{base}/shares/me", headers=a).json()
    assert share_a["participant_id"] == "user_001"
    # 6. dealer generates a proof for A's share
    proof = client.post(f"{base}/proofs", headers=dealer, json={"participant_id": "user_001"}).json()
    assert proof["commitments"] == share_a["values"]
    # 7. A verifies it (stored proof and inline data give the same real result)
    assert client.post(f"{base}/verify", headers=a, json={"proof_id": proof["proof_id"]}).json() == \
        {"verified": True, "message": "Verification successful"}
    inline = {k: proof[k] for k in ("x", "challenge", "commitments", "witness")}
    assert client.post(f"{base}/verify", headers=a, json={"proof": inline}).json()["verified"] is True
    # 8. shares are collected out of band: B and C each read their OWN share and hand it to A
    collected = [share_a]
    for user in ("user_002", "user_003"):
        headers = _login(client, user, passwords[user])
        collected.append(client.get(f"{base}/shares/me", headers=headers).json())
    # 9-10. A submits three shares and recovers the secret
    r = client.post(f"{base}/recover", headers=a,
                    json={"shares": [{"x": s["x"], "values": s["values"]} for s in collected]})
    assert r.status_code == 200
    # 11. compare
    assert r.json()["message"] == message
    return sid, proof


def test_end_to_end_3_of_5(client, passwords):
    _full_flow(client, passwords, "Hello World")


def test_end_to_end_multilingual_multichunk(client, passwords):
    _full_flow(client, passwords, "多项式承诺与秘密分享 / 秘密分散 / secret sharing 🔐 " * 3)


def test_end_to_end_invalid_proof_and_insufficient_shares(client, passwords):
    sid, proof = _full_flow(client, passwords, "中文消息恢复测试")
    base = f"/api/v1/sharing/{sid}"
    a = _login(client, "user_001", passwords["user_001"])
    forged = {k: proof[k] for k in ("x", "challenge", "commitments", "witness")}
    forged["witness"] = str(int(forged["witness"]) ^ 1)
    assert client.post(f"{base}/verify", headers=a, json={"proof": forged}).json()["verified"] is False
    share_a = client.get(f"{base}/shares/me", headers=a).json()
    single = [{"x": share_a["x"], "values": share_a["values"]}]
    r = client.post(f"{base}/recover", headers=a, json={"shares": single})
    assert r.status_code == 422


def test_state_survives_restart(api_settings, passwords):
    from app.main import create_app
    with TestClient(create_app(api_settings)) as c1:
        sid, proof = _full_flow(c1, passwords, "persisted secret")
        a_token = _login(c1, "user_001", passwords["user_001"])
        share_before = c1.get(f"/api/v1/sharing/{sid}/shares/me", headers=a_token).json()

    # "Restart": brand-new app, engine and sessions on the same SQLite file.
    with TestClient(create_app(api_settings)) as c2:
        base = f"/api/v1/sharing/{sid}"
        assert c2.get(f"{base}/shares/me", headers=a_token).json() == share_before  # token still valid
        dealer = _login(c2, "dealer_a", passwords["dealer_a"])
        assert c2.get(base, headers=dealer).json()["status"] == "distributed"
        assert c2.post(f"{base}/distribute", headers=dealer).status_code == 409
        assert c2.post(f"{base}/verify", headers=a_token,
                       json={"proof_id": proof["proof_id"]}).json()["verified"] is True
        shares = []
        for user in ("user_003", "user_004", "user_005"):
            s = c2.get(f"{base}/shares/me", headers=_login(c2, user, passwords[user])).json()
            shares.append({"x": s["x"], "values": s["values"]})
        assert c2.post(f"{base}/recover", headers=dealer, json={"shares": shares}).json()["message"] \
            == "persisted secret"


def test_logs_contain_no_secrets(client, passwords, app, caplog):
    caplog.set_level(logging.DEBUG)
    message = "LOG-HYGIENE-SECRET-消息"
    sid, proof = _full_flow(client, passwords, message)
    a = _login(client, "user_001", passwords["user_001"])
    share = client.get(f"/api/v1/sharing/{sid}/shares/me", headers=a).json()

    from app.storage.repository import Repository
    with app.state.session_factory() as s:
        coeffs = [c for row in Repository(s).get_task_polynomials(sid) for c in row]
        r_coeffs = [c for row in Repository(s).get_r_polynomials(sid) for c in row]

    text = caplog.text
    assert "sharing task created" in text and "secret recovered" in text   # logging is active
    forbidden = [message, *passwords.values(), a["Authorization"].split()[1], proof["witness"],
                 *share["values"], *(str(c) for c in coeffs + r_coeffs if c > 10**6)]
    for item in forbidden:
        assert item not in text


def test_finding_proof_given_to_participant_lowers_threshold(client, passwords):
    """Documented limitation, demonstrated through the real API.

    With k = 2 and one chunk, a single participant who receives the inline proof for
    their own share learns f(t) for t = p - 1 (the API's S = T = {t}) and, together with
    their own share, reconstructs the secret alone.  Verifying by ``proof_id`` avoids
    handing W to the participant.
    """
    from pcss import polynomial
    from pcss.config import FIELD_MODULUS as P
    from pcss.encoding import decode_message

    dealer = _login(client, "dealer_a", passwords["dealer_a"])
    a = _login(client, "user_001", passwords["user_001"])
    r = client.post("/api/v1/sharing", headers=dealer,
                    json={"message": "k=2 leak", "threshold": 2, "participant_ids": PARTICIPANTS})
    task = r.json()
    base = f"/api/v1/sharing/{task['sharing_id']}"
    client.post(f"{base}/distribute", headers=dealer)
    proof = client.post(f"{base}/proofs", headers=dealer, json={"participant_id": "user_001"}).json()
    share = client.get(f"{base}/shares/me", headers=a).json()

    t = int(task["public_parameters"]["evaluation_set"][0])
    x, cm, w = share["x"], int(share["values"][0]), int(proof["witness"])
    f_t = (cm - w * (x - t)) % P                       # W = (f(x) - f(t)) / (x - t)
    secret = polynomial.lagrange_evaluate([(x, cm), (t, f_t)], 0)
    assert decode_message([secret], task["original_length"]) == "k=2 leak"
