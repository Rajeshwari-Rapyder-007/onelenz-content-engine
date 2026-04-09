import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt

from shared.logging import get_logger

logger = get_logger(__name__)

ISS = "onelenz"
AUD = "www.onelenz.ai"
ALGORITHM = "RS256"


def _private_key() -> str:
    """Get RS256 private key from env var (PEM content, not file path)."""
    key = os.getenv("JWT_PRIVATE_KEY", "")
    if not key:
        raise RuntimeError("JWT_PRIVATE_KEY env var is not set")
    return key


def _public_key() -> str:
    """Get RS256 public key from env var (PEM content, not file path)."""
    key = os.getenv("JWT_PUBLIC_KEY", "")
    if not key:
        raise RuntimeError("JWT_PUBLIC_KEY env var is not set")
    return key


def _build_claims(
    user_id: str,
    session_id: str,
    expire_minutes: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "iss": ISS,
        "sub": str(user_id),
        "aud": AUD,
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
        "jti": session_id,
    }


def create_access_token(user_id: str, session_id: str) -> tuple[str, datetime]:
    """Create a signed access token. Returns (token, expires_at)."""
    expire_minutes = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "2"))
    claims = _build_claims(user_id, session_id, expire_minutes)
    token = jwt.encode(claims, _private_key(), algorithm=ALGORITHM)
    return token, claims["exp"]


def create_refresh_token(user_id: str, session_id: str) -> tuple[str, datetime]:
    """Create a signed refresh token. Returns (token, expires_at)."""
    expire_minutes = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_MINUTES", "15"))
    claims = _build_claims(user_id, session_id, expire_minutes)
    token = jwt.encode(claims, _private_key(), algorithm=ALGORITHM)
    return token, claims["exp"]


def decode_token(token: str, verify_exp: bool = True) -> Optional[dict[str, Any]]:
    """Decode and verify a JWT. Returns claims dict or None on failure."""
    try:
        options = {"verify_exp": verify_exp}
        claims = jwt.decode(
            token,
            _public_key(),
            algorithms=[ALGORITHM],
            audience=AUD,
            issuer=ISS,
            options=options,
        )
        return claims
    except JWTError as e:
        logger.warning("JWT decode failed", extra={"x_error": str(e)})
        return None
