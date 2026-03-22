"""Password hasher tests."""

from __future__ import annotations

from infrastructure.external.password_hasher import PBKDF2PasswordHasher


def test_password_hasher_round_trip() -> None:
    hasher = PBKDF2PasswordHasher(iterations=1_000)

    password_hash = hasher.hash_password("secret")

    assert password_hash != "secret"
    assert hasher.verify_password("secret", password_hash) is True
    assert hasher.verify_password("wrong", password_hash) is False
