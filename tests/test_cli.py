import io

import pytest

pytest.importorskip("sqlalchemy")

from app.cli import main, open_repository  # noqa: E402
from app.security.passwords import verify_password  # noqa: E402


def test_seed_demo_and_create_user(tmp_path, monkeypatch, capsys):
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    assert main(["--database-url", url, "seed-demo"]) == 0
    out = capsys.readouterr().out
    assert "dealer_a" in out and "user_005" in out
    main(["--database-url", url, "seed-demo"])                       # idempotent
    assert "already exists" in capsys.readouterr().out

    monkeypatch.setattr("sys.stdin", io.StringIO("correct-horse-battery\n"))
    main(["--database-url", url, "create-user", "carol", "--role", "dealer", "--password-stdin"])
    with open_repository(url) as repo:
        carol = repo.get_user("carol")
        assert carol.role == "dealer" and verify_password("correct-horse-battery", carol.password_hash)
        assert repo.get_user("user_001").role == "participant"

    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
    with pytest.raises(SystemExit):
        main(["--database-url", url, "create-user", "dave", "--role", "participant", "--password-stdin"])
    monkeypatch.setattr("sys.stdin", io.StringIO("long-enough-password\n"))
    with pytest.raises(ValueError):                                  # duplicate user id
        main(["--database-url", url, "create-user", "carol", "--role", "dealer", "--password-stdin"])
