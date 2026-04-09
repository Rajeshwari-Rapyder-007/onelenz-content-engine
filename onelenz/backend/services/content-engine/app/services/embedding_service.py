import asyncio
import json
from typing import Any

import boto3

from shared.logging import get_logger

from ..config import settings

logger = get_logger(__name__)

_client: Any = None


def _get_client() -> Any:
    """Lazy-init Bedrock client."""
    global _client
    if _client is None:
        _client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
        )
    return _client


def _invoke_model_sync(text: str) -> list[float]:
    """Synchronous boto3 call — always run via to_thread."""
    client = _get_client()
    response = client.invoke_model(
        modelId=settings.bedrock_embedding_model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "inputText": text,
            "dimensions": (
                settings.bedrock_embedding_dimensions
            ),
        }),
    )
    result = json.loads(response["body"].read())
    return result["embedding"]


async def embed_text(text: str) -> list[float]:
    """Embed a single text string."""
    return await asyncio.to_thread(
        _invoke_model_sync, text
    )


async def embed_batch(
    texts: list[str],
) -> list[list[float]]:
    """Embed multiple texts in batches.

    Processes up to bedrock_max_batch_size texts
    concurrently per batch using asyncio.gather.
    """
    all_embeddings: list[list[float]] = []
    batch_size = settings.bedrock_max_batch_size

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        results = await asyncio.gather(
            *(
                asyncio.to_thread(
                    _invoke_model_sync, t
                )
                for t in batch
            )
        )
        all_embeddings.extend(results)
        logger.info(
            "Embedded batch %d-%d of %d",
            i,
            min(i + batch_size, len(texts)),
            len(texts),
        )

    return all_embeddings
