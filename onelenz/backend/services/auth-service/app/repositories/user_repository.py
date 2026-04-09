from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.base_repository import BaseRepository
from shared.logging import get_logger

from ..models.auth_history import UserAuthenticationHistory
from ..models.entity import SubscriberEntity
from ..models.role_mapping import UserRoleMapping
from ..models.user import UserMaster
from ..models.user_security import UserSecurityDetails

logger = get_logger(__name__)


class UserRepository(BaseRepository[UserMaster]):
    def __init__(self, session: AsyncSession):
        super().__init__(UserMaster, session)

    async def find_entity_by_domain(self, domain: str) -> Optional[SubscriberEntity]:
        """Find an active entity by email domain."""
        stmt = select(SubscriberEntity).where(
            SubscriberEntity.ent_domain == domain,
            SubscriberEntity.ent_is_active == 1,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_entity(self, entity: SubscriberEntity) -> SubscriberEntity:
        """Insert a new subscriber entity (tenant)."""
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def find_by_email(self, email: str) -> Optional[UserMaster]:
        """Find an active user by email. Email is globally unique across entities."""
        stmt = select(UserMaster).where(
            UserMaster.usm_user_email_id == email,
            UserMaster.usm_user_status == 1,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_user_with_security(
        self,
        user: UserMaster,
        security: UserSecurityDetails,
    ) -> UserMaster:
        """Insert user_master and user_security_details in one transaction."""
        self.session.add(user)
        self.session.add(security)
        await self.session.flush()
        return user

    async def create_auth_history(
        self, history: UserAuthenticationHistory
    ) -> UserAuthenticationHistory:
        self.session.add(history)
        await self.session.flush()
        return history

    async def get_security_details(
        self, user_id: UUID, entity_id: str
    ) -> Optional[UserSecurityDetails]:
        """Get security details (password hash, 2FA config) for a user within an entity."""
        stmt = (
            select(UserSecurityDetails)
            .join(UserMaster, UserMaster.usm_user_id == UserSecurityDetails.usd_user_id)
            .where(
                UserSecurityDetails.usd_user_id == user_id,
                UserMaster.usm_entity_id == entity_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def increment_failed_login(
        self, user_id: UUID, entity_id: str, lockout_threshold: int, lockout_minutes: int
    ) -> None:
        """Increment failed login count. Lock account if threshold reached."""
        stmt = select(UserMaster).where(
            UserMaster.usm_user_id == user_id,
            UserMaster.usm_entity_id == entity_id,
        )
        result = await self.session.execute(stmt)
        user = result.scalars().first()
        if not user:
            logger.warning(
                "Attempted to increment failed login for non-existent user",
                extra={"x_user_id": str(user_id), "x_entity_id": entity_id},
            )
            return
        new_count = user.usm_failed_login_count + 1
        values: dict[str, Any] = {
            "usm_failed_login_count": new_count,
            "usm_modified_on": datetime.now(timezone.utc),
        }
        if new_count >= lockout_threshold:
            values["usm_locked_until"] = datetime.now(timezone.utc) + timedelta(
                minutes=lockout_minutes
            )
        await self.update_by_id("usm_user_id", user_id, values)

    async def reset_failed_login(self, user_id: UUID, entity_id: str) -> None:
        """Reset failed login count and lockout after successful login."""
        stmt = select(UserMaster).where(
            UserMaster.usm_user_id == user_id,
            UserMaster.usm_entity_id == entity_id,
        )
        result = await self.session.execute(stmt)
        user = result.scalars().first()
        if not user:
            return
        await self.update_by_id("usm_user_id", user_id, {
            "usm_failed_login_count": 0,
            "usm_locked_until": None,
            "usm_modified_on": datetime.now(timezone.utc),
        })

    async def update_logout_time(
        self, user_id: UUID, session_id: str, entity_id: str
    ) -> None:
        """Set logout time on auth history row, scoped to entity."""
        stmt = (
            update(UserAuthenticationHistory)
            .where(
                UserAuthenticationHistory.uah_user_id == user_id,
                UserAuthenticationHistory.uah_session_id == session_id,
            )
            .values(uah_logout_time=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)

    async def update_password(self, user_id: UUID, entity_id: str, hashed_pwd: str) -> None:
        """Update password hash for a user."""
        stmt = select(UserMaster).where(
            UserMaster.usm_user_id == user_id,
            UserMaster.usm_entity_id == entity_id,
        )
        result = await self.session.execute(stmt)
        user = result.scalars().first()
        if not user:
            return
        stmt_update = (
            update(UserSecurityDetails)
            .where(UserSecurityDetails.usd_user_id == user_id)
            .values(
                usd_hashed_pwd=hashed_pwd,
                usd_modified_on=datetime.now(timezone.utc),
            )
        )
        await self.session.execute(stmt_update)

    async def create_role_mapping(self, mapping: UserRoleMapping) -> UserRoleMapping:
        """Insert a user-role mapping record."""
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def get_user_role(self, user_id: UUID, entity_id: str) -> Optional[str]:
        """Get the active role_id for a user within an entity."""
        stmt = select(UserRoleMapping.urm_role_id).where(
            UserRoleMapping.urm_mapped_user_id == user_id,
            UserRoleMapping.urm_record_status == 1,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
