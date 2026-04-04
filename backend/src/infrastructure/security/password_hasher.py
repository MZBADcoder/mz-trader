"""Password hashing using stdlib PBKDF2."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os


class PBKDF2PasswordHasher:
    """Hash and verify passwords without extra third-party dependencies."""

    def __init__(self, *, iterations: int = 600_000, salt_bytes: int = 16) -> None:
        self._iterations = iterations
        self._salt_bytes = salt_bytes

    def hash_password(self, password: str) -> str:
        """Hash a password with a random salt."""
        salt = os.urandom(self._salt_bytes)
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, self._iterations)
        salt_b64 = base64.b64encode(salt).decode("ascii")
        digest_b64 = base64.b64encode(derived).decode("ascii")
        return f"pbkdf2_sha256${self._iterations}${salt_b64}${digest_b64}"

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a candidate password."""
        try:
            algorithm, iterations_text, salt_b64, digest_b64 = password_hash.split("$", 3)
        except ValueError:
            return False

        if algorithm != "pbkdf2_sha256":
            return False

        iterations = int(iterations_text)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
