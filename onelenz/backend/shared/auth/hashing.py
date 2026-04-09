from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password using Argon2id. Salt is auto-generated and embedded in the hash."""
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against an Argon2id hash. Returns True if match."""
    try:
        return _hasher.verify(hashed, password)
    except VerifyMismatchError:
        return False
