from datetime import datetime

from sqlalchemy import delete, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.base_repository import BaseRepository
from shared.logging import get_logger

from ..models.chunk import ContentChunk

logger = get_logger(__name__)


class ChunkRepository(BaseRepository[ContentChunk]):
    def __init__(self, session: AsyncSession):
        super().__init__(ContentChunk, session)

    async def bulk_insert(
        self, chunks: list[ContentChunk]
    ) -> None:
        """Batch insert chunks."""
        self.session.add_all(chunks)
        await self.session.flush()

    async def update_embeddings(
        self,
        chunk_updates: list[dict],
    ) -> None:
        """Batch update embeddings.

        chunk_updates: [{"chunk_id": ..., "embedding": [...]}]
        """
        for item in chunk_updates:
            stmt = (
                update(ContentChunk)
                .where(
                    ContentChunk.ck_chunk_id == item["chunk_id"]
                )
                .values(ck_embedding=item["embedding"])
            )
            await self.session.execute(stmt)

    async def delete_by_asset_id(
        self, asset_id: str
    ) -> int:
        """Delete all chunks for an asset.

        Returns count deleted.
        """
        stmt = (
            delete(ContentChunk)
            .where(ContentChunk.ck_asset_id == asset_id)
        )
        result = await self.session.execute(stmt)
        return result.rowcount

    async def delete_old_chunks(
        self, asset_id: str, before: datetime
    ) -> int:
        """Delete chunks created before timestamp.

        Used for replacement flows.
        Returns count deleted.
        """
        stmt = (
            delete(ContentChunk)
            .where(
                ContentChunk.ck_asset_id == asset_id,
                ContentChunk.created_on < before,
            )
        )
        result = await self.session.execute(stmt)
        return result.rowcount

    async def find_similar_chunks(
        self,
        entity_id: str,
        embedding: list[float],
        threshold: float,
        limit: int,
    ) -> list[dict]:
        """Vector similarity search using pgvector.

        Only returns chunks from INDEXED assets.
        Uses raw SQL with pgvector <=> operator.
        """
        sql = text("""
            SELECT ck_chunk_id, ck_content_text,
                   ck_section_heading, ck_category_id,
                   ck_source_url, ck_asset_id,
                   1 - (ck_embedding <=> :embedding)
                       AS similarity
            FROM content_chunk
            WHERE ck_entity_id = :entity_id
              AND ck_asset_id IN (
                  SELECT ca_asset_id FROM content_asset
                  WHERE ca_status = 'INDEXED'
              )
              AND 1 - (ck_embedding <=> :embedding)
                  > :threshold
            ORDER BY ck_embedding <=> :embedding
            LIMIT :limit
        """)

        result = await self.session.execute(
            sql,
            {
                "entity_id": entity_id,
                "embedding": str(embedding),
                "threshold": threshold,
                "limit": limit,
            },
        )

        return [
            {
                "chunk_id": str(row.ck_chunk_id),
                "content_text": row.ck_content_text,
                "section_heading": row.ck_section_heading,
                "category_id": row.ck_category_id,
                "source_url": row.ck_source_url,
                "asset_id": str(row.ck_asset_id),
                "similarity": float(row.similarity),
            }
            for row in result
        ]
