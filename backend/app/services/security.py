"""Password hashing and session-token primitives (stdlib only).

- Passwords: PBKDF2-HMAC-SHA256, 600k iterations (OWASP 2023 guidance), format
  ``pbkdf2_sha256$iterations$salt_hex$dk_hex`` — no external dependency needed
  and portable across runtimes.
- Sessions: opaque random tokens (secrets.token_urlsafe); only the SHA-256
  hash is persisted, so a database leak does not leak usable sessions. Opaque
  tokens over JWTs keep revocation trivial (delete/hash lookup) which suits
  the "human-in-the-loop" security posture (§14).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 600_000
_ALGORITHM = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode(), PBKDF2_ITERATIONS
    )
    return f"{_ALGORITHM}${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, iterations, salt, expected_hex = stored.split("$", 3)
    except ValueError:
        return False
    if algorithm != _ALGORITHM:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), int(iterations))
    return hmac.compare_digest(digest.hex(), expected_hex)


def new_session_token() -> str:
    """Generate a fresh opaque session token (url-safe, 256-bit entropy)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Deterministic hash for storing/looking up session tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
