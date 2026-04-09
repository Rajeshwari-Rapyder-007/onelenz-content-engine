from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.base_repository import BaseRepository

from ..models.consent import ConsentManagement


class ConsentRepository(BaseRepository[ConsentManagement]):
    def __init__(self, session: AsyncSession):
        super().__init__(ConsentManagement, session)

    async def find_active_consent(
        self, entity_id: str, consent_type: str
    ) -> Optional[ConsentManagement]:
        """Find an active, non-revoked consent for an entity + type."""
        stmt = select(ConsentManagement).where(
            ConsentManagement.cm_entity_id == entity_id,
            ConsentManagement.cm_consent_type == consent_type,
            ConsentManagement.cm_is_granted == True,  # noqa: E712
            ConsentManagement.cm_revoked_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def find_any_consent(
        self, entity_id: str, consent_type: str
    ) -> Optional[ConsentManagement]:
        """Find any consent row for entity + type (active or revoked)."""
        stmt = select(ConsentManagement).where(
            ConsentManagement.cm_entity_id == entity_id,
            ConsentManagement.cm_consent_type == consent_type,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def grant(
        self,
        entity_id: str,
        user_id: str,
        consent_type: str,
        domain_scope: str,
    ) -> ConsentManagement:
        """Grant consent. If revoked row exists, reactivate it."""
        now = datetime.now(timezone.utc)
        existing = await self.find_any_consent(entity_id, consent_type)

        if existing and existing.cm_is_granted:
            return existing

        if existing:
            # Reactivate revoked consent
            existing.cm_is_granted = True
            existing.cm_revoked_at = None
            existing.cm_granted_at = now
            existing.cm_granted_by = user_id
            await self.session.flush()
            return existing

        # Create new consent
        consent = ConsentManagement(
            cm_entity_id=entity_id,
            cm_user_id=user_id,
            cm_consent_type=consent_type,
            cm_domain_scope=domain_scope,
            cm_is_granted=True,
            cm_granted_by=user_id,
            cm_granted_at=now,
        )
        self.session.add(consent)
        await self.session.flush()
        return consent

    async def revoke(self, entity_id: str, consent_type: str) -> None:
        """Revoke active consent for entity + type."""
        consent = await self.find_active_consent(entity_id, consent_type)
        if consent:
            consent.cm_is_granted = False
            consent.cm_revoked_at = datetime.now(timezone.utc)
            await self.session.flush()
