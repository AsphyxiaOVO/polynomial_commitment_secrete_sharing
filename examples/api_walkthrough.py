"""In-process walkthrough of the REST API (no server needed).

    pip install -r requirements-dev.txt
    python examples/api_walkthrough.py

Uses a throw-away SQLite file and random passwords / JWT secret; prints every
request and the (truncated) JSON response.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from fastapi.testclient import TestClient  # noqa: E402

from app.cli import create_user, open_repository  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.security.authorization import Role  # noqa: E402

USERS = {"dealer_a": Role.DEALER, **{f"user_{i:03d}": Role.PARTICIPANT for i in range(1, 6)}}


def show(label, response):
    text = json.dumps(response.json(), ensure_ascii=False)
    print(f"\n### {label} -> HTTP {response.status_code}\n{text[:400]}{'...' if len(text) > 400 else ''}")
    return response.json()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(jwt_secret=secrets.token_urlsafe(48),
                            database_url=f"sqlite:///{os.path.join(tmp, 'demo.db')}")
        passwords = {u: secrets.token_urlsafe(12) for u in USERS}
        with open_repository(settings.database_url) as repo:
            for user, role in USERS.items():
                create_user(repo, user, role, passwords[user])

        with TestClient(create_app(settings)) as c:
            def login(user):
                r = c.post("/api/v1/auth/login", data={"username": user, "password": passwords[user]})
                return {"Authorization": f"Bearer {r.json()['access_token']}"}

            dealer, alice = login("dealer_a"), login("user_001")
            task = show("Dealer creates 3-of-5 sharing", c.post(
                "/api/v1/sharing", headers=dealer,
                json={"message": "Hello World 你好", "threshold": 3,
                      "participant_ids": list(USERS)[1:]}))
            base = f"/api/v1/sharing/{task['sharing_id']}"
            show("Participant tries to create", c.post("/api/v1/sharing", headers=alice, json={
                "message": "x", "threshold": 2, "participant_ids": ["user_001", "user_002"]}))
            show("Dealer distributes", c.post(f"{base}/distribute", headers=dealer))
            show("Dealer distributes again", c.post(f"{base}/distribute", headers=dealer))
            mine = show("Alice reads her own share", c.get(f"{base}/shares/me", headers=alice))
            proof = show("Dealer generates proof for Alice", c.post(
                f"{base}/proofs", headers=dealer, json={"participant_id": "user_001"}))
            show("Alice verifies (stored proof)", c.post(
                f"{base}/verify", headers=alice, json={"proof_id": proof["proof_id"]}))
            show("Dealer verifies (detailed)", c.post(
                f"{base}/verify", headers=dealer, json={"proof_id": proof["proof_id"]}))
            bad = {k: proof[k] for k in ("x", "challenge", "commitments", "witness")}
            bad["witness"] = str(int(bad["witness"]) + 1)
            show("Alice verifies a tampered witness", c.post(
                f"{base}/verify", headers=alice, json={"proof": bad}))
            shares = [{"x": mine["x"], "values": mine["values"]}]
            for user in ("user_002", "user_003"):        # handed to Alice out of band
                s = c.get(f"{base}/shares/me", headers=login(user)).json()
                shares.append({"x": s["x"], "values": s["values"]})
            show("Alice recovers with 2 shares", c.post(
                f"{base}/recover", headers=alice, json={"shares": shares[:2]}))
            show("Alice recovers with 3 shares", c.post(
                f"{base}/recover", headers=alice, json={"shares": shares}))


if __name__ == "__main__":
    main()
