"""Authentication: login, JWT validation, role taken from the database."""

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")

import jwt  # noqa: E402

from app.security.passwords import hash_password, verify_password  # noqa: E402

PROTECTED = [
    ("get", "/api/v1/auth/me", None),
    ("post", "/api/v1/sharing", {"message": "x", "threshold": 2,
                                 "participant_ids": ["user_001", "user_002"]}),
    ("get", "/api/v1/sharing/abc", None),
    ("post", "/api/v1/sharing/abc/distribute", None),
    ("get", "/api/v1/sharing/abc/shares/me", None),
    ("post", "/api/v1/sharing/abc/proofs", {"participant_id": "user_001"}),
    ("post", "/api/v1/sharing/abc/verify", {"proof_id": "p"}),
    ("post", "/api/v1/sharing/abc/recover", {"shares": [{"x": 1, "values": ["1"]}]}),
]


def test_login_returns_jwt_with_role_from_database(client, passwords, api_settings):
    r = client.post("/api/v1/auth/login", data={"username": "dealer_a", "password": passwords["dealer_a"]})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["user"] == {"user_id": "dealer_a", "role": "dealer"}
    assert body["expires_in"] == api_settings.access_token_expire_minutes * 60
    claims = jwt.decode(body["access_token"], api_settings.jwt_secret, algorithms=["HS256"],
                        issuer=api_settings.jwt_issuer)
    assert claims["sub"] == "dealer_a" and "role" not in claims       # role is not trusted from tokens


@pytest.mark.parametrize("username,password", [
    ("dealer_a", "wrong-password"), ("nobody", "whatever-123"), ("dealer_a", "")])
def test_login_failure_is_401_with_generic_message(client, username, password):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code in (401, 422)
    if r.status_code == 401:
        assert r.json()["error"]["message"] == "Incorrect username or password"


def test_inactive_user_cannot_login(client, passwords, app):
    from app.storage.models import User
    with app.state.session_factory() as s:
        s.get(User, "user_001").is_active = False
        s.commit()
    r = client.post("/api/v1/auth/login", data={"username": "user_001", "password": passwords["user_001"]})
    assert r.status_code == 401


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_protected_endpoints_require_token(client, method, path, body):
    r = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert r.json()["error"]["code"] == "not_authenticated"


def _token(settings, **overrides):
    now = datetime.now(timezone.utc)
    claims = {"sub": "dealer_a", "iat": now, "exp": now + timedelta(minutes=5),
              "iss": settings.jwt_issuer, "type": "access"}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


@pytest.mark.parametrize("case", ["garbage", "wrong_key", "expired", "wrong_issuer", "wrong_type",
                                  "no_sub", "unknown_user", "alg_none"])
def test_invalid_tokens_are_rejected(client, api_settings, case):
    now = datetime.now(timezone.utc)
    if case == "garbage":
        token = "not.a.jwt"
    elif case == "wrong_key":
        token = jwt.encode({"sub": "dealer_a", "iat": now, "exp": now + timedelta(minutes=5),
                            "iss": api_settings.jwt_issuer, "type": "access"},
                           "another-secret-that-is-long-enough-123456", algorithm="HS256")
    elif case == "expired":
        token = _token(api_settings, iat=now - timedelta(hours=2), exp=now - timedelta(hours=1))
    elif case == "wrong_issuer":
        token = _token(api_settings, iss="someone-else")
    elif case == "wrong_type":
        token = _token(api_settings, type="refresh")
    elif case == "no_sub":
        token = _token(api_settings, sub=None)
    elif case == "unknown_user":
        token = _token(api_settings, sub="ghost")
    else:  # unsigned token claiming to be a dealer
        token = jwt.encode({"sub": "dealer_a", "iat": now, "exp": now + timedelta(minutes=5),
                            "iss": api_settings.jwt_issuer, "type": "access"}, None, algorithm="none")
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401, case


def test_role_is_re_read_from_database_on_every_request(client, auth, app):
    from app.storage.models import User
    headers = auth("dealer_a")
    assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == "dealer"
    with app.state.session_factory() as s:
        s.get(User, "dealer_a").role = "participant"        # demoted by an admin
        s.commit()
    r = client.post("/api/v1/sharing", headers=headers,
                    json={"message": "x", "threshold": 2, "participant_ids": ["user_001", "user_002"]})
    assert r.status_code == 403                                 # old token, new role


def test_client_supplied_role_is_never_trusted(client, auth):
    body = {"message": "x", "threshold": 2, "participant_ids": ["user_001", "user_002"], "role": "dealer"}
    assert client.post("/api/v1/sharing", json=body, headers=auth("user_001")).status_code == 403
    # Even for a dealer, an unknown "role" field is rejected rather than silently used.
    assert client.post("/api/v1/sharing", json=body, headers=auth("dealer_a")).status_code == 422


def test_there_is_no_self_registration_endpoint(client):
    r = client.post("/api/v1/auth/register", json={"username": "evil", "password": "x" * 10,
                                                   "role": "dealer"})
    assert r.status_code in (404, 405)


def test_passwords_are_hashed_not_stored(app, passwords):
    from app.storage.models import User
    with app.state.session_factory() as s:
        stored = s.get(User, "user_001").password_hash
    assert passwords["user_001"] not in stored and stored.startswith("scrypt$")
    assert verify_password(passwords["user_001"], stored)
    assert not verify_password(passwords["user_001"] + "x", stored)
    assert not verify_password("anything", "not-a-hash")
    h1, h2 = hash_password("same-password"), hash_password("same-password")
    assert h1 != h2                                              # random salt
    with pytest.raises(ValueError):
        hash_password("short")


def test_settings_reject_weak_secret_and_hide_it():
    from app.config import ConfigurationError, Settings
    with pytest.raises(ConfigurationError):
        Settings(jwt_secret="too-short")
    s = Settings(jwt_secret="s" * 40)
    assert "s" * 40 not in repr(s)


def test_settings_from_env_requires_secret(monkeypatch):
    from app.config import ConfigurationError, Settings
    monkeypatch.delenv("PCSS_JWT_SECRET", raising=False)
    with pytest.raises(ConfigurationError):
        Settings.from_env()
    monkeypatch.setenv("PCSS_JWT_SECRET", "k" * 48)
    monkeypatch.setenv("PCSS_ACCESS_TOKEN_EXPIRE_MINUTES", "5")
    assert Settings.from_env().access_token_expire_minutes == 5
