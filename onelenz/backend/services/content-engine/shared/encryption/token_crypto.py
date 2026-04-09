import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from shared.logging import get_logger

logger = get_logger(__name__)

_NONCE_SIZE = 12  # 96-bit nonce for AES-GCM


def _get_key() -> bytes:
    """Load AES-256 encryption key from env var."""
    key_b64 = os.getenv("TOKEN_ENCRYPTION_KEY", "")
    if not key_b64:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY env var is not set")
    return base64.b64decode(key_b64)


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string using AES-256-GCM.

    Returns base64-encoded string: nonce + ciphertext + tag.
    """
    key = _get_key()
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt an AES-256-GCM encrypted token string.

    Expects base64-encoded string: nonce + ciphertext + tag.
    """
    key = _get_key()
    raw = base64.b64decode(encrypted)
    nonce = raw[:_NONCE_SIZE]
    ciphertext = raw[_NONCE_SIZE:]
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode()
