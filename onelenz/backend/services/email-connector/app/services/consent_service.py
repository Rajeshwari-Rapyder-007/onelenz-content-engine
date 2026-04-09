from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth.middleware import CurrentUser
from shared.logging import get_logger

from ..repositories.consent_repository import ConsentRepository
from ..schemas.consent import ConsentGrantResponse, ConsentStatusResponse

logger = get_logger(__name__)


async def grant_consent(
    user: CurrentUser,
    consent_type: str,
    domain_scope: str,
    session: AsyncSession,
) -> ConsentGrantResponse:
    """Grant consent for an entity."""
    repo = ConsentRepository(session)
    consent = await repo.grant(
        entity_id=user.entity_id,
        user_id=user.user_id,
        consent_type=consent_type,
        domain_scope=domain_scope,
    )
    logger.info(
        "Consent granted",
        extra={"x_entity_id": user.entity_id, "x_consent_type": consent_type},
    )
    return ConsentGrantResponse(
        consent_id=consent.cm_id,
        consent_type=consent.cm_consent_type,
        is_granted=consent.cm_is_granted,
        granted_at=consent.cm_granted_at,
    )


async def revoke_consent(
    user: CurrentUser,
    consent_type: str,
    session: AsyncSession,
) -> None:
    """Revoke consent for an entity."""
    repo = ConsentRepository(session)
    await repo.revoke(entity_id=user.entity_id, consent_type=consent_type)
    logger.info(
        "Consent revoked",
        extra={"x_entity_id": user.entity_id, "x_consent_type": consent_type},
    )


async def check_consent(
    entity_id: str,
    consent_type: str,
    session: AsyncSession,
) -> bool:
    """Check if active consent exists for entity + type."""
    repo = ConsentRepository(session)
    consent = await repo.find_active_consent(entity_id, consent_type)
    return consent is not None


async def get_consent_status(
    user: CurrentUser,
    consent_type: str,
    session: AsyncSession,
) -> ConsentStatusResponse:
    """Get consent status for display."""
    repo = ConsentRepository(session)
    consent = await repo.find_any_consent(user.entity_id, consent_type)
    if not consent:
        return ConsentStatusResponse(
            consent_type=consent_type,
            is_granted=False,
        )
    return ConsentStatusResponse(
        consent_type=consent.cm_consent_type,
        is_granted=consent.cm_is_granted,
        granted_at=consent.cm_granted_at,
        revoked_at=consent.cm_revoked_at,
    )
