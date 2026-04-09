import asyncio
import json
import os
from typing import Any

import boto3

from shared.logging import get_logger

logger = get_logger(__name__)

_s3_client = None


def _get_client():
    """Lazy-init S3 client."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            region_name=os.getenv("AWS_REGION", "ap-south-1"),
        )
    return _s3_client


def _upload_json_sync(bucket: str, key: str, data: dict[str, Any]) -> str:
    body = json.dumps(data, default=str).encode()
    _get_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
    )
    return f"s3://{bucket}/{key}"


def _upload_bytes_sync(bucket: str, key: str, content: bytes, content_type: str) -> str:
    _get_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentType=content_type,
    )
    return f"s3://{bucket}/{key}"


def _download_json_sync(bucket: str, key: str) -> dict[str, Any]:
    resp = _get_client().get_object(Bucket=bucket, Key=key)
    body = resp["Body"].read()
    return json.loads(body)


async def upload_json(bucket: str, key: str, data: dict[str, Any]) -> str:
    """Upload a JSON object to S3. Non-blocking via thread executor."""
    result = await asyncio.to_thread(_upload_json_sync, bucket, key, data)
    logger.debug("Uploaded JSON to S3", extra={"x_bucket": bucket, "x_key": key})
    return result


async def upload_bytes(
    bucket: str, key: str, content: bytes, content_type: str
) -> str:
    """Upload binary content to S3. Non-blocking via thread executor."""
    result = await asyncio.to_thread(_upload_bytes_sync, bucket, key, content, content_type)
    logger.debug("Uploaded bytes to S3", extra={"x_bucket": bucket, "x_key": key})
    return result


async def download_json(bucket: str, key: str) -> dict[str, Any]:
    """Download a JSON object from S3. Non-blocking via thread executor."""
    return await asyncio.to_thread(_download_json_sync, bucket, key)
