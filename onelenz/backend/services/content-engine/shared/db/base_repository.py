from typing import Any, Generic, Optional, Sequence, Type, TypeVar

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .base_model import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic CRUD repository. Service-specific repositories extend this."""

    def __init__(self, model: Type[ModelT], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(self, id_column: str, id_value: Any) -> Optional[ModelT]:
        """Fetch a single row by its primary key column."""
        col = getattr(self.model, id_column)
        stmt = select(self.model).where(col == id_value)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_field(
        self, field_name: str, value: Any
    ) -> Optional[ModelT]:
        """Fetch a single row by any column."""
        col = getattr(self.model, field_name)
        stmt = select(self.model).where(col == value)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_field(
        self,
        field_name: str,
        value: Any,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ModelT]:
        """Fetch multiple rows matching a field value."""
        col = getattr(self.model, field_name)
        stmt = (
            select(self.model)
            .where(col == value)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create(self, entity: ModelT) -> ModelT:
        """Insert a new row."""
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update_by_id(
        self, id_column: str, id_value: Any, values: dict[str, Any]
    ) -> None:
        """Update a row by its primary key column."""
        col = getattr(self.model, id_column)
        stmt = update(self.model).where(col == id_value).values(**values)
        await self.session.execute(stmt)

    async def delete_by_id(self, id_column: str, id_value: Any) -> None:
        """Delete a row by its primary key column."""
        col = getattr(self.model, id_column)
        stmt = delete(self.model).where(col == id_value)
        await self.session.execute(stmt)
