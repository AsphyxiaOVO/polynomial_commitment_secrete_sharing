import random
import secrets

import pytest

from pcss.config import FIELD_MODULUS


@pytest.fixture
def rng():
    """Seeded generator for *test data only* (never used to build sharing polynomials)."""
    return random.Random(20250318)


@pytest.fixture
def p():
    return FIELD_MODULUS


# --------------------------------------------------------------------------- #
# API fixtures (imports are local so the core tests run without FastAPI installed)
# --------------------------------------------------------------------------- #

DEMO_USERS = {
    "dealer_a": "dealer",
    "dealer_b": "dealer",
    "user_001": "participant",
    "user_002": "participant",
    "user_003": "participant",
    "user_004": "participant",
    "user_005": "participant",
    "user_006": "participant",     # never part of dealer_a's tasks (outsider)
}


@pytest.fixture
def api_settings(tmp_path):
    from app.config import Settings
    return Settings(jwt_secret=secrets.token_urlsafe(48),
                    database_url=f"sqlite:///{tmp_path / 'test.db'}")


@pytest.fixture
def passwords(api_settings):
    """Create the test users (random passwords, generated per test run)."""
    from app.cli import create_user, open_repository
    from app.security.authorization import Role
    pw = {}
    with open_repository(api_settings.database_url) as repo:
        for user_id, role in DEMO_USERS.items():
            pw[user_id] = secrets.token_urlsafe(16)
            create_user(repo, user_id, Role(role), pw[user_id])
    return pw


@pytest.fixture
def app(api_settings, passwords):
    from app.main import create_app
    return create_app(api_settings)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth(client, passwords):
    """auth("user_001") -> Authorization header (token cached per user)."""
    cache = {}

    def _headers(user_id):
        if user_id not in cache:
            r = client.post("/api/v1/auth/login",
                            data={"username": user_id, "password": passwords[user_id]})
            assert r.status_code == 200, r.text
            cache[user_id] = {"Authorization": f"Bearer {r.json()['access_token']}"}
        return cache[user_id]
    return _headers


PARTICIPANTS_5 = ["user_001", "user_002", "user_003", "user_004", "user_005"]


@pytest.fixture
def make_task(client, auth):
    """Create (and optionally distribute) a task as ``dealer``; returns the response JSON."""
    def _make(message="Hello World", threshold=3, participants=None, dealer="dealer_a",
              distribute=True):
        body = {"message": message, "threshold": threshold,
                "participant_ids": participants or PARTICIPANTS_5}
        r = client.post("/api/v1/sharing", json=body, headers=auth(dealer))
        assert r.status_code == 201, r.text
        task = r.json()
        if distribute:
            d = client.post(f"/api/v1/sharing/{task['sharing_id']}/distribute", headers=auth(dealer))
            assert d.status_code == 200, d.text
            task = d.json()
        return task
    return _make
