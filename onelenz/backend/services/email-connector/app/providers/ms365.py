import asyncio
import base64
from typing import Optional
from urllib.parse import urlencode

import httpx

from shared.logging import get_logger

from .base import BaseOAuthProvider, TokenResponse, UserProfile
from .base_email import (
    Attachment,
    AttachmentMeta,
    BaseEmailProvider,
    DeltaFetchResult,
    DeltaTokenExpiredError,
    EmailMessage,
    FetchResult,
    TokenExpiredError,
)

logger = get_logger(__name__)

MS_AUTH_BASE = "https://login.microsoftonline.com/common/oauth2/v2.0"
MS_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MS_SCOPES = "Mail.Read User.Read offline_access"

EMAIL_SELECT = (
    "id,subject,from,toRecipients,ccRecipients,bccRecipients,"
    "receivedDateTime,sentDateTime,bodyPreview,body,hasAttachments,"
    "internetMessageId,isRead,isDraft,importance,inferenceClassification,"
    "conversationId,parentFolderId,flag"
)


def _parse_email(msg: dict) -> EmailMessage:
    """Parse a Graph API message response into an EmailMessage."""
    from_data = msg.get("from", {}).get("emailAddress", {})
    return EmailMessage(
        id=msg.get("id", ""),
        internet_message_id=msg.get("internetMessageId", ""),
        subject=msg.get("subject", ""),
        from_address=from_data.get("address", ""),
        from_name=from_data.get("name", ""),
        to_recipients=[
            r["emailAddress"]["address"]
            for r in msg.get("toRecipients", [])
            if "emailAddress" in r
        ],
        cc_recipients=[
            r["emailAddress"]["address"]
            for r in msg.get("ccRecipients", [])
            if "emailAddress" in r
        ],
        bcc_recipients=[
            r["emailAddress"]["address"]
            for r in msg.get("bccRecipients", [])
            if "emailAddress" in r
        ],
        received_datetime=msg.get("receivedDateTime", ""),
        sent_datetime=msg.get("sentDateTime", ""),
        body_content=msg.get("body", {}).get("content", ""),
        body_content_type=msg.get("body", {}).get("contentType", "html"),
        body_preview=msg.get("bodyPreview", ""),
        has_attachments=msg.get("hasAttachments", False),
        is_read=msg.get("isRead", False),
        is_draft=msg.get("isDraft", False),
        importance=msg.get("importance", "normal"),
        inference_classification=msg.get("inferenceClassification", ""),
        conversation_id=msg.get("conversationId", ""),
        parent_folder_id=msg.get("parentFolderId", ""),
        flag_status=msg.get("flag", {}).get("flagStatus", "notFlagged"),
        raw_data=msg,
    )


def _check_status(resp: httpx.Response) -> None:
    """Check response status and raise specific exceptions for 401/410."""
    if resp.status_code == 401:
        raise TokenExpiredError("Access token expired")
    if resp.status_code == 410:
        raise DeltaTokenExpiredError("Delta token is stale")
    resp.raise_for_status()


async def _handle_rate_limit(resp: httpx.Response, max_wait: int = 300) -> None:
    """Handle 429 rate limiting with Retry-After header. Max wait 5 min."""
    retry_after = min(int(resp.headers.get("Retry-After", "30")), max_wait)
    logger.warning(
        "Graph API rate limited",
        extra={"x_retry_after": retry_after},
    )
    await asyncio.sleep(retry_after)


class MS365OAuthProvider(BaseOAuthProvider):
    """Microsoft 365 OAuth provider using Microsoft Graph API."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret

    def get_auth_url(self, state: str, redirect_uri: str) -> str:
        """Build OAuth authorization URL."""
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": MS_SCOPES,
            "state": state,
            "response_mode": "query",
        }
        return f"{MS_AUTH_BASE}/authorize?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> TokenResponse:
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{MS_AUTH_BASE}/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if not resp.is_success:
                logger.error(f"Token exchange failed: {resp.text}")
            resp.raise_for_status()
            body = resp.json()

        return TokenResponse(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token", ""),
            expires_in=body.get("expires_in", 3600),
            token_type=body.get("token_type", "Bearer"),
            scope=body.get("scope", ""),
        )

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": MS_SCOPES,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{MS_AUTH_BASE}/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            body = resp.json()

        return TokenResponse(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token", refresh_token),
            expires_in=body.get("expires_in", 3600),
            token_type=body.get("token_type", "Bearer"),
            scope=body.get("scope", ""),
        )

    async def get_user_profile(self, access_token: str) -> UserProfile:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{MS_GRAPH_BASE}/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            body = resp.json()

        return UserProfile(
            upn=body.get("userPrincipalName", body.get("mail", "")),
            tenant_id=body.get("id", ""),
            display_name=body.get("displayName"),
        )


class MS365EmailProvider(BaseEmailProvider):
    """Microsoft 365 email provider — fetches messages via Graph API."""

    async def fetch_messages(
        self,
        access_token: str,
        folder: str,
        filter_query: str,
        top: int = 1000,
    ) -> FetchResult:
        url = f"{MS_GRAPH_BASE}/me/mailFolders/{folder}/messages"
        params = {
            "$filter": filter_query,
            "$orderby": "receivedDateTime desc",
            "$top": str(top),
            "$select": EMAIL_SELECT,
        }
        return await self._fetch(access_token, url, params)

    async def fetch_next_page(
        self, access_token: str, next_link: str
    ) -> FetchResult:
        return await self._fetch(access_token, next_link)

    async def fetch_delta(
        self,
        access_token: str,
        folder: str,
        delta_token: Optional[str] = None,
        filter_query: Optional[str] = None,
    ) -> DeltaFetchResult:
        headers: dict[str, str] = {"Authorization": f"Bearer {access_token}"}

        if delta_token and delta_token.startswith("http"):
            # Follow a nextLink or saved deltaLink URL (params already encoded)
            url = delta_token
            params = None
        else:
            url = f"{MS_GRAPH_BASE}/me/mailFolders/{folder}/messages/delta"
            params = {"$select": EMAIL_SELECT}
            if filter_query:
                params["$filter"] = filter_query
                params["$orderby"] = "receivedDateTime desc"
            headers["Prefer"] = "odata.maxpagesize=200"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 429:
                await _handle_rate_limit(resp)
                resp = await client.get(url, params=params, headers=headers)
            elif resp.status_code >= 500:
                wait = int(resp.headers.get("Retry-After", "5"))
                logger.warning(f"Graph 5xx ({resp.status_code}), retrying in {wait}s")
                await asyncio.sleep(wait)
                resp = await client.get(url, params=params, headers=headers)
            _check_status(resp)
            body = resp.json()

        messages = [_parse_email(m) for m in body.get("value", [])]
        return DeltaFetchResult(
            messages=messages,
            next_link=body.get("@odata.nextLink"),
            delta_link=body.get("@odata.deltaLink"),
        )

    async def fetch_attachments(
        self, access_token: str, message_id: str
    ) -> list[Attachment]:
        url = f"{MS_GRAPH_BASE}/me/messages/{message_id}/attachments"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code == 429:
                await _handle_rate_limit(resp)
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            _check_status(resp)
            body = resp.json()

        attachments = []
        for att in body.get("value", []):
            # Skip inline attachments (embedded images in body, e.g. signature logos)
            if att.get("isInline", False):
                continue
            content_bytes = base64.b64decode(att.get("contentBytes", ""))
            if len(content_bytes) > 25 * 1024 * 1024:  # 25MB limit
                logger.warning(
                    "Skipping oversized attachment",
                    extra={"x_attachment_name": att.get("name"), "x_size": len(content_bytes)},
                )
                continue
            attachments.append(Attachment(
                id=att.get("id", ""),
                name=att.get("name", "unknown"),
                size=att.get("size", 0),
                content_type=att.get("contentType", "application/octet-stream"),
                content_bytes=content_bytes,
            ))
        return attachments

    async def fetch_attachments_metadata_batch(
        self, access_token: str, message_ids: list[str],
    ) -> dict[str, list[AttachmentMeta]]:
        """Fetch attachment metadata (no content) for multiple messages via $batch."""
        BATCH_LIMIT = 20
        ATT_META_SELECT = "id,name,size,contentType,isInline"
        MAX_SIZE = 25 * 1024 * 1024  # 25MB
        result: dict[str, list[AttachmentMeta]] = {}

        for chunk_start in range(0, len(message_ids), BATCH_LIMIT):
            chunk = message_ids[chunk_start:chunk_start + BATCH_LIMIT]
            requests = [
                {
                    "id": msg_id,
                    "method": "GET",
                    "url": f"/me/messages/{msg_id}/attachments?$select={ATT_META_SELECT}",
                }
                for msg_id in chunk
            ]

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{MS_GRAPH_BASE}/$batch",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json={"requests": requests},
                )
                if resp.status_code == 429:
                    await _handle_rate_limit(resp)
                    resp = await client.post(
                        f"{MS_GRAPH_BASE}/$batch",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                        },
                        json={"requests": requests},
                    )
                _check_status(resp)
                batch_body = resp.json()

            for response in batch_body.get("responses", []):
                msg_id = response["id"]
                status = response.get("status", 500)
                if status != 200:
                    logger.warning(
                        "Batch attachment metadata fetch failed",
                        extra={"x_msg_id": msg_id, "x_status": status},
                    )
                    result[msg_id] = []
                    continue

                attachments: list[AttachmentMeta] = []
                for att in response.get("body", {}).get("value", []):
                    if att.get("isInline", False):
                        continue
                    size = att.get("size", 0)
                    if size > MAX_SIZE:
                        logger.warning(
                            "Skipping oversized attachment",
                            extra={"x_att_name": att.get("name"), "x_size": size},
                        )
                        continue
                    attachments.append(AttachmentMeta(
                        id=att.get("id", ""),
                        name=att.get("name", "unknown"),
                        size=size,
                        content_type=att.get("contentType", "application/octet-stream"),
                    ))
                result[msg_id] = attachments

        return result

    async def download_attachment(
        self, access_token: str, message_id: str, attachment_id: str,
    ) -> bytes:
        """Download raw attachment content via /$value endpoint."""
        url = f"{MS_GRAPH_BASE}/me/messages/{message_id}/attachments/{attachment_id}/$value"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code == 429:
                await _handle_rate_limit(resp)
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            _check_status(resp)
            return resp.content

    async def _fetch(
        self,
        access_token: str,
        url: str,
        params: Optional[dict] = None,
    ) -> FetchResult:
        """Internal fetch with rate limit and 401/410 handling."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code == 429:
                await _handle_rate_limit(resp)
                resp = await client.get(
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            _check_status(resp)
            body = resp.json()

        messages = [_parse_email(m) for m in body.get("value", [])]
        return FetchResult(
            messages=messages,
            next_link=body.get("@odata.nextLink"),
        )
