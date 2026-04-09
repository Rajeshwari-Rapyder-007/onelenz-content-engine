import os
from datetime import datetime, timezone
from typing import Any

from shared.logging import get_logger
from shared.s3 import upload_bytes, upload_json

logger = get_logger(__name__)

BUCKET = os.getenv("S3_BUCKET_EMAILS", "onelenz-emails")


def _date_prefix(received_datetime: str) -> str:
    """Extract date prefix from ISO datetime string. Falls back to today."""
    try:
        dt = datetime.fromisoformat(received_datetime.replace("Z", "+00:00"))
        return dt.strftime("%Y/%m/%d")
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc).strftime("%Y/%m/%d")


async def store_email_body(
    entity_id: str,
    message_id: str,
    body_data: dict[str, Any],
    received_datetime: str = "",
) -> str:
    """Store full email body as JSON in S3. Returns S3 key."""
    date_prefix = _date_prefix(received_datetime)
    key = f"{entity_id}/{date_prefix}/{message_id}.json"
    return await upload_json(BUCKET, key, body_data)


async def store_attachment(
    entity_id: str,
    message_id: str,
    attachment_id: str,
    filename: str,
    content: bytes,
    content_type: str,
    received_datetime: str = "",
) -> str:
    """Store attachment binary in S3. Returns S3 key."""
    date_prefix = _date_prefix(received_datetime)
    safe_filename = filename.replace("/", "_").replace("\\", "_")
    key = f"{entity_id}/attachments/{date_prefix}/{message_id}/{attachment_id}_{safe_filename}"
    return await upload_bytes(BUCKET, key, content, content_type)
