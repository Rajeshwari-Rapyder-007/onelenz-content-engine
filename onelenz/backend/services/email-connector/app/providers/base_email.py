from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class EmailMessage:
    """Normalized email message from any provider."""

    id: str
    internet_message_id: str
    subject: str
    from_address: str
    from_name: str
    to_recipients: list[str]
    cc_recipients: list[str]
    bcc_recipients: list[str]
    received_datetime: str
    sent_datetime: str
    body_content: str
    body_content_type: str
    body_preview: str
    has_attachments: bool
    is_read: bool
    is_draft: bool
    importance: str
    inference_classification: str
    conversation_id: str
    parent_folder_id: str
    flag_status: str
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AttachmentMeta:
    """Attachment metadata without content (from $batch metadata fetch)."""

    id: str
    name: str
    size: int
    content_type: str


@dataclass
class Attachment:
    """Email attachment metadata + content."""

    id: str
    name: str
    size: int
    content_type: str
    content_bytes: bytes


@dataclass
class FetchResult:
    """Result of a message fetch — messages + pagination link."""

    messages: list[EmailMessage]
    next_link: Optional[str] = None


@dataclass
class DeltaFetchResult:
    """Result of a delta fetch — messages + delta/next links."""

    messages: list[EmailMessage]
    next_link: Optional[str] = None
    delta_link: Optional[str] = None


class TokenExpiredError(Exception):
    """Raised when access token is expired (401). Caller should refresh and retry."""


class DeltaTokenExpiredError(Exception):
    """Raised when delta token is stale (410). Caller should fall back to full fetch."""


class BaseEmailProvider(ABC):
    """Abstract interface for fetching emails. Implement for each provider."""

    @abstractmethod
    async def fetch_messages(
        self,
        access_token: str,
        folder: str,
        filter_query: str,
        top: int = 50,
    ) -> FetchResult:
        """Fetch messages from a folder with a filter."""

    @abstractmethod
    async def fetch_next_page(
        self, access_token: str, next_link: str
    ) -> FetchResult:
        """Fetch the next page of results."""

    @abstractmethod
    async def fetch_delta(
        self,
        access_token: str,
        folder: str,
        delta_token: Optional[str] = None,
    ) -> DeltaFetchResult:
        """Fetch new/changed messages since last delta token."""

    @abstractmethod
    async def fetch_attachments(
        self, access_token: str, message_id: str
    ) -> list[Attachment]:
        """Fetch all attachments for a message."""

    async def fetch_attachments_metadata_batch(
        self, access_token: str, message_ids: list[str],
    ) -> dict[str, list[AttachmentMeta]]:
        """Fetch attachment metadata (no content) for multiple messages.

        Default implementation falls back to individual fetch_attachments calls.
        Override for provider-specific batch support (e.g. Graph $batch API).
        """
        result: dict[str, list[AttachmentMeta]] = {}
        for msg_id in message_ids:
            atts = await self.fetch_attachments(access_token, msg_id)
            result[msg_id] = [
                AttachmentMeta(id=a.id, name=a.name, size=a.size, content_type=a.content_type)
                for a in atts
            ]
        return result

    async def download_attachment(
        self, access_token: str, message_id: str, attachment_id: str,
    ) -> bytes:
        """Download raw attachment content.

        Default implementation fetches all attachments and finds the matching one.
        Override for provider-specific streaming (e.g. /$value endpoint).
        """
        atts = await self.fetch_attachments(access_token, message_id)
        for a in atts:
            if a.id == attachment_id:
                return a.content_bytes
        return b""
