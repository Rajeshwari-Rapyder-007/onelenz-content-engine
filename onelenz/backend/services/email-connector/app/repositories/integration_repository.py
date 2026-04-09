from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.base_repository import BaseRepository

from ..models.integration_config import IntegrationConfig


class IntegrationRepository(BaseRepository[IntegrationConfig]):
    def __init__(self, session: AsyncSession):
        super().__init__(IntegrationConfig, session)

    async def find_by_user_and_type(
        self,
        user_id: str,
        entity_id: str,
        integration_type: str,
        provider: str,
    ) -> Optional[IntegrationConfig]:
        """Find an active integration for a user + type + provider."""
        stmt = select(IntegrationConfig).where(
            IntegrationConfig.inc_user_id == user_id,
            IntegrationConfig.inc_entity_id == entity_id,
            IntegrationConfig.inc_integration_type == integration_type,
            IntegrationConfig.inc_provider == provider,
            IntegrationConfig.inc_is_active == True,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def find_disconnected(
        self,
        user_id: str,
        entity_id: str,
        integration_type: str,
        provider: str,
    ) -> Optional[IntegrationConfig]:
        """Find a disconnected integration for re-connect flow."""
        stmt = select(IntegrationConfig).where(
            IntegrationConfig.inc_user_id == user_id,
            IntegrationConfig.inc_entity_id == entity_id,
            IntegrationConfig.inc_integration_type == integration_type,
            IntegrationConfig.inc_provider == provider,
            IntegrationConfig.inc_auth_status == "DISCONNECTED",
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def find_active_by_entity(
        self, entity_id: str, integration_type: str
    ) -> Sequence[IntegrationConfig]:
        """Find all active integrations for an entity."""
        stmt = select(IntegrationConfig).where(
            IntegrationConfig.inc_entity_id == entity_id,
            IntegrationConfig.inc_integration_type == integration_type,
            IntegrationConfig.inc_is_active == True,  # noqa: E712
            IntegrationConfig.inc_auth_status == "CONNECTED",
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def find_all_connected(
        self, integration_type: str,
    ) -> Sequence[IntegrationConfig]:
        """Find all active + connected integrations across all entities."""
        stmt = select(IntegrationConfig).where(
            IntegrationConfig.inc_integration_type == integration_type,
            IntegrationConfig.inc_is_active == True,  # noqa: E712
            IntegrationConfig.inc_auth_status == "CONNECTED",
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_tokens(
        self, config_id: int, config_json: dict[str, Any]
    ) -> None:
        """Update encrypted tokens and sync state in config_json."""
        await self.update_by_id("inc_config_id", config_id, {
            "inc_config_json": config_json,
            "inc_modified_on": datetime.now(timezone.utc),
        })

    async def update_status(self, config_id: int, status: str) -> None:
        """Update the auth status of an integration."""
        await self.update_by_id("inc_config_id", config_id, {
            "inc_auth_status": status,
            "inc_modified_on": datetime.now(timezone.utc),
        })

    async def reactivate(self, config_id: int) -> None:
        """Reactivate a disconnected integration for re-connect flow."""
        await self.update_by_id("inc_config_id", config_id, {
            "inc_is_active": True,
            "inc_auth_status": "PENDING",
            "inc_config_json": {},
            "inc_modified_on": datetime.now(timezone.utc),
        })
