from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from shared.encryption import decrypt_token, encrypt_token
from shared.errors import AppError
from shared.errors.codes import MS365_AUTH_FAILED
from shared.logging import get_logger

from ..config import settings
from ..providers.ms365 import MS365OAuthProvider
from ..repositories.integration_repository import IntegrationRepository

logger = get_logger(__name__)


def _get_provider() -> MS365OAuthProvider:
    return MS365OAuthProvider(
        client_id=settings.ms_oauth_client_id,
        client_secret=settings.ms_oauth_client_secret,
    )


async def ensure_fresh_token(config_id: int, session: AsyncSession) -> str:
    """Ensure access token is fresh. Refresh if expired/expiring. Returns decrypted access token."""
    repo = IntegrationRepository(session)
    integration = await repo.get_by_id("inc_config_id", config_id)
    if not integration:
        raise AppError(MS365_AUTH_FAILED, detail="Integration not found")

    config_json = integration.inc_config_json or {}
    expiry_str = config_json.get("access_token_expiry", "")
    buffer_minutes = settings.token_refresh_buffer_minutes

    # Check if token needs refresh
    needs_refresh = True
    if expiry_str:
        expiry = datetime.fromisoformat(expiry_str)
        if expiry > datetime.now(timezone.utc) + timedelta(minutes=buffer_minutes):
            needs_refresh = False

    if not needs_refresh:
        # Token is fresh — decrypt and return
        return decrypt_token(config_json["access_token"])

    # Token expired or expiring — refresh
    encrypted_refresh = config_json.get("refresh_token", "")
    if not encrypted_refresh:
        raise AppError(MS365_AUTH_FAILED, detail="No refresh token stored")

    decrypted_refresh = decrypt_token(encrypted_refresh)
    provider = _get_provider()

    try:
        token_resp = await provider.refresh_access_token(decrypted_refresh)
    except Exception:
        logger.error("Token refresh failed", exc_info=True, extra={"x_config_id": config_id})
        # Mark AUTH_FAILED
        config_json["auth_failed_at"] = datetime.now(timezone.utc).isoformat()
        config_json["auth_fail_reason"] = "Refresh token invalid or expired"
        await repo.update_tokens(config_id, config_json)
        await repo.update_status(config_id, "AUTH_FAILED")
        raise AppError(MS365_AUTH_FAILED, detail="Token refresh failed")

    # Update stored tokens
    now = datetime.now(timezone.utc)
    config_json["access_token"] = encrypt_token(token_resp.access_token)
    config_json["access_token_expiry"] = (now + timedelta(seconds=token_resp.expires_in)).isoformat()
    config_json["refresh_token"] = encrypt_token(token_resp.refresh_token)
    config_json["auth_failed_at"] = None
    config_json["auth_fail_reason"] = None
    await repo.update_tokens(config_id, config_json)

    logger.info("Token refreshed", extra={"x_config_id": config_id})
    return token_resp.access_token
