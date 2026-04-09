# Manual JSON serialization for Redis string storage (set/get with TTL).
import json
import uuid
from datetime import datetime, timedelta, timezone

# Catch httpx.HTTPStatusError to log exact status codes from Microsoft.
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth.middleware import CurrentUser
from shared.encryption import encrypt_token
from shared.errors import AppError
from shared.errors.codes import (
    MS365_CONSENT_REQUIRED,
    MS365_INTEGRATION_EXISTS,
    MS365_NOT_CONNECTED,
    MS365_OAUTH_DECLINED,
    MS365_OAUTH_FAILED,
    MS365_STATE_EXPIRED,
    UNAUTHORIZED,
)
from shared.logging import get_logger

# Plain string keys with per-key TTL (vs hash fields which can't have individual TTLs).
from shared.redis.client import redis_client

from ..config import settings
from ..models.integration_config import IntegrationConfig
from ..providers.ms365 import MS365OAuthProvider
from ..repositories.integration_repository import IntegrationRepository
from ..schemas.email import CallbackResponse, ConnectResponse, DisconnectResponse, StatusResponse
from .consent_service import check_consent

logger = get_logger(__name__)

INTEGRATION_TYPE = "EMAIL"
PROVIDER = "o365"


def _get_provider() -> MS365OAuthProvider:
    return MS365OAuthProvider(
        client_id=settings.ms_oauth_client_id,
        client_secret=settings.ms_oauth_client_secret,
    )


# Namespaced Redis key: {env}:onelenz:email:oauth_state:{state_uuid}
def _state_key(state: str) -> str:
    return f"{settings.environment}:onelenz:email:oauth_state:{state}"


async def initiate_connect(
    user: CurrentUser,
    session: AsyncSession,
) -> ConnectResponse:
    """Start OAuth flow. Returns Microsoft authorization URL."""
    repo = IntegrationRepository(session)

    has_consent = await check_consent(user.entity_id, "EMAIL_SCAN", session)
    if not has_consent:
        raise AppError(MS365_CONSENT_REQUIRED)

    existing = await repo.find_by_user_and_type(
        user.user_id, user.entity_id, INTEGRATION_TYPE, PROVIDER
    )
    if existing:
        raise AppError(MS365_INTEGRATION_EXISTS)

    # Only reactivate explicitly disconnected integrations (not AUTH_FAILED ones).
    disconnected = await repo.find_disconnected(
        user.user_id, user.entity_id, INTEGRATION_TYPE, PROVIDER
    )
    if disconnected:
        await repo.reactivate(disconnected.inc_config_id)

    state = str(uuid.uuid4())

    # Store state in Redis with 10-min TTL — auto-expires if user doesn't finish.
    state_payload = json.dumps({
        "user_id": user.user_id,
        "entity_id": user.entity_id,
        "config_id": disconnected.inc_config_id if disconnected else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await redis_client.set(_state_key(state), state_payload, ex=600)

    provider = _get_provider()
    auth_url = provider.get_auth_url(state, settings.ms_oauth_redirect_uri)

    logger.info(
        "OAuth connect initiated",
        extra={"x_user_id": user.user_id, "x_entity_id": user.entity_id},
    )

    return ConnectResponse(auth_url=auth_url, state=state)


async def handle_callback(
    code: str,
    state: str,
    session: AsyncSession,
) -> CallbackResponse:
    """Handle OAuth callback from UI. Exchange code for tokens, store integration."""

    # Fetch and delete state atomically to prevent replay attacks.
    raw = await redis_client.get(_state_key(state))
    if not raw:
        raise AppError(MS365_STATE_EXPIRED)

    await redis_client.delete(_state_key(state))
    state_data = json.loads(raw)

    user_id = state_data["user_id"]
    entity_id = state_data["entity_id"]
    config_id = state_data.get("config_id")

    provider = _get_provider()

    try:
        token_resp = await provider.exchange_code(code, settings.ms_oauth_redirect_uri)
    except httpx.HTTPStatusError as exc:
        logger.error("OAuth token exchange failed", extra={"x_status": exc.response.status_code})
        raise AppError(MS365_OAUTH_FAILED)
    except Exception:
        logger.error("OAuth token exchange failed", exc_info=True)
        raise AppError(MS365_OAUTH_FAILED)

    if not token_resp.access_token:
        raise AppError(MS365_OAUTH_DECLINED)

    try:
        profile = await provider.get_user_profile(token_resp.access_token)
    except Exception:
        logger.error("Failed to fetch user profile", exc_info=True)
        raise AppError(MS365_OAUTH_FAILED)

    now = datetime.now(timezone.utc)
    config_json = {
        "access_token": encrypt_token(token_resp.access_token),
        "access_token_expiry": (now + timedelta(seconds=token_resp.expires_in)).isoformat(),
        "refresh_token": encrypt_token(token_resp.refresh_token),
        "user_upn": profile.upn,
        "tenant_id": profile.tenant_id,
        "sync_mode": "full_fetch",
        "days_to_fetch": settings.initial_fetch_days,
        "inbox_delta_token": None,
        "sent_delta_token": None,
        "delta_token_updated_at": None,
        "initial_sync_complete": False,
        "total_emails_synced": 0,
        "auth_failed_at": None,
        "auth_fail_reason": None,
    }

    repo = IntegrationRepository(session)

    if config_id:
        # Reconnecting a previously disconnected integration.
        await repo.update_tokens(config_id, config_json)
        await repo.update_status(config_id, "CONNECTED")
        config_id_to_fetch = config_id
    else:
        # First-time connection — create new integration record.
        integration = IntegrationConfig(
            inc_entity_id=entity_id,
            inc_user_id=user_id,
            inc_integration_type=INTEGRATION_TYPE,
            inc_provider=PROVIDER,
            inc_auth_status="CONNECTED",
            inc_sync_frequency=f"every_{settings.sync_frequency_minutes}min",
            inc_is_active=True,
            inc_config_json=config_json,
            inc_created_by=user_id,
            inc_created_on=now,
        )
        await repo.create(integration)
        config_id_to_fetch = integration.inc_config_id

    from ..workers.sync_tasks import initial_full_fetch
    initial_full_fetch.delay(config_id_to_fetch)

    logger.info(
        "OAuth callback successful, full fetch dispatched",
        extra={"x_user_id": user_id, "x_entity_id": entity_id, "x_upn": profile.upn},
    )

    return CallbackResponse(
        status="CONNECTED",
        message="Email integration connected successfully",
    )


async def get_status(
    user: CurrentUser,
    session: AsyncSession,
) -> StatusResponse:
    """Get current integration status."""
    repo = IntegrationRepository(session)

    integration = await repo.find_by_user_and_type(
        user.user_id, user.entity_id, INTEGRATION_TYPE, PROVIDER
    )

    # Fall back to disconnected record so the UI can offer reconnect vs fresh connect.
    if not integration:
        integration = await repo.find_disconnected(
            user.user_id, user.entity_id, INTEGRATION_TYPE, PROVIDER
        )

    if not integration:
        return StatusResponse(status="NOT_CONNECTED")

    config = integration.inc_config_json or {}
    return StatusResponse(
        status=integration.inc_auth_status,
        provider=PROVIDER,
        user_email=config.get("user_upn"),
        total_emails_synced=config.get("total_emails_synced"),
        last_sync_at=integration.inc_last_sync_at,
        sync_frequency=integration.inc_sync_frequency,
        initial_sync_complete=config.get("initial_sync_complete"),
        connected_at=integration.inc_created_on,
    )


async def disconnect(
    user: CurrentUser,
    session: AsyncSession,
) -> DisconnectResponse:
    """Disconnect integration. Data is retained."""
    repo = IntegrationRepository(session)
    integration = await repo.find_by_user_and_type(
        user.user_id, user.entity_id, INTEGRATION_TYPE, PROVIDER
    )

    if not integration:
        raise AppError(MS365_NOT_CONNECTED)

    await repo.update_status(integration.inc_config_id, "DISCONNECTED")
    await repo.update_by_id("inc_config_id", integration.inc_config_id, {
        "inc_is_active": False,
        "inc_modified_on": datetime.now(timezone.utc),
    })

    logger.info(
        "Integration disconnected",
        extra={"x_user_id": user.user_id, "x_entity_id": user.entity_id},
    )

    return DisconnectResponse(message="Disconnected. Synced data has been retained.")


async def trigger_manual_sync(
    user: CurrentUser,
    session: AsyncSession,
) -> dict:
    """Trigger an incremental sync on demand (admin only)."""
    if user.role_id != "ADMIN":
        raise AppError(UNAUTHORIZED, detail="Admin role required")

    repo = IntegrationRepository(session)
    integration = await repo.find_by_user_and_type(
        user.user_id, user.entity_id, INTEGRATION_TYPE, PROVIDER
    )

    if not integration or integration.inc_auth_status != "CONNECTED":
        raise AppError(MS365_NOT_CONNECTED)

    has_consent = await check_consent(user.entity_id, "EMAIL_SCAN", session)
    if not has_consent:
        raise AppError(MS365_CONSENT_REQUIRED)

    from ..workers.sync_tasks import sync_single
    sync_single.delay(integration.inc_config_id)

    logger.info(
        "Manual sync triggered",
        extra={"x_user_id": user.user_id, "x_config_id": integration.inc_config_id},
    )

    return {"message": "Sync triggered", "config_id": integration.inc_config_id}
