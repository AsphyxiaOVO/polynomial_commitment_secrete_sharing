"""Admin CLI: database initialisation and user provisioning.

There is intentionally no self-registration endpoint: roles are assigned here
by whoever runs the server, so no client can grant itself the dealer role.

    python -m app.cli init-db
    python -m app.cli create-user dealer_a --role dealer          # prompts for the password
    python -m app.cli seed-demo                                   # demo users, random passwords

The database is taken from PCSS_DATABASE_URL (default sqlite:///./pcss_demo.db).
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys
from contextlib import contextmanager
from typing import Iterator, List, Optional, Sequence, Tuple

from app.config import database_url_from_env
from app.security.authorization import Role
from app.security.passwords import MIN_PASSWORD_LENGTH, hash_password
from app.storage.database import init_db, make_engine, make_session_factory
from app.storage.models import User
from app.storage.repository import Repository

DEMO_USERS: List[Tuple[str, Role]] = [
    ("dealer_a", Role.DEALER), ("dealer_b", Role.DEALER),
    *[(f"user_{i:03d}", Role.PARTICIPANT) for i in range(1, 6)],
]


def create_user(repo: Repository, user_id: str, role: Role, password: str) -> User:
    if repo.get_user(user_id) is not None:
        raise ValueError(f"user {user_id!r} already exists")
    user = User(id=user_id, role=role.value, password_hash=hash_password(password), is_active=True)
    repo.add_user(user)
    repo.commit()
    return user


@contextmanager
def open_repository(database_url: str) -> Iterator[Repository]:
    """Repository on a fresh engine; session and engine are closed afterwards."""
    engine = make_engine(database_url)
    init_db(engine)
    session = make_session_factory(engine)()
    try:
        yield Repository(session)
    finally:
        session.close()
        engine.dispose()


def _prompt_password() -> str:
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise SystemExit("passwords do not match")
    return first


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=None, help="overrides PCSS_DATABASE_URL")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="create tables")
    cu = sub.add_parser("create-user", help="create one user (password via prompt or stdin)")
    cu.add_argument("user_id")
    cu.add_argument("--role", choices=[r.value for r in Role], required=True)
    cu.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
    sub.add_parser("seed-demo", help="create demo users with random passwords (printed once)")
    args = parser.parse_args(argv)

    with open_repository(args.database_url or database_url_from_env()) as repo:
        if args.command == "init-db":
            print("database initialised")
        elif args.command == "create-user":
            password = sys.stdin.readline().rstrip("\n") if args.password_stdin else _prompt_password()
            if len(password) < MIN_PASSWORD_LENGTH:
                raise SystemExit(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
            create_user(repo, args.user_id, Role(args.role), password)
            print(f"created {args.role} {args.user_id}")
        elif args.command == "seed-demo":
            print("Demo credentials (shown once, not stored in plain text):")
            for user_id, role in DEMO_USERS:
                if repo.get_user(user_id) is not None:
                    print(f"  {user_id:10s} {role.value:12s} (already exists, unchanged)")
                    continue
                password = secrets.token_urlsafe(12)
                create_user(repo, user_id, role, password)
                print(f"  {user_id:10s} {role.value:12s} {password}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
