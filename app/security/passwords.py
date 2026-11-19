"""Password hashing with the standard library's scrypt (memory-hard KDF).

Stored format:  ``scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>``
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

N, R, P_PARAM, DKLEN, SALT_BYTES = 2**14, 8, 1, 32, 16
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 1024


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError(
            f"password must be a string of {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=N, r=R, p=P_PARAM, dklen=DKLEN)
    return f"scrypt${N}${R}${P_PARAM}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison; returns False for malformed hashes instead of raising."""
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(hash_b64)
        if len(password) > MAX_PASSWORD_LENGTH:
            return False
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p),
                                dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


#: Used to spend the same time when the user does not exist (reduces user enumeration by timing).
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
