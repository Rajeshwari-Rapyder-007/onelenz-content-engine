import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger

from ..config import settings
from ..providers.base_email import (
    AttachmentMeta,
    DeltaTokenExpiredError,
    EmailMessage,
    TokenExpiredError,
)
from ..providers.ms365 import MS365EmailProvider
from ..repositories.audit_repository import AuditRepository
from ..repositories.ingest_repository import IngestRepository
from ..repositories.integration_repository import IntegrationRepository
from ..workers.sync_lock import extend_lock
from .consent_service import check_consent
from .storage_service import store_attachment, store_email_body
from .token_service import ensure_fresh_token

logger = get_logger(__name__)

_email_provider = MS365EmailProvider()

BATCH_SIZE = 100
PROGRESS_LOG_INTERVAL = 500
CONCURRENT_GRAPH_LIMIT = 10
CONCURRENT_S3_LIMIT = 20


# ---------------------------------------------------------------------------
#  Public API — called by Celery tasks
# ---------------------------------------------------------------------------


async def full_fetch(config_id: int, session: AsyncSession) -> None:
    """Run initial full fetch for a newly connected integration."""
    integration_repo = IntegrationRepository(session)
    audit_repo = AuditRepository(session)
    ingest_repo = IngestRepository(session)

    # 1. Load config
    integration = await integration_repo.get_by_id("inc_config_id", config_id)
    if not integration:
        logger.error("Integration not found", extra={"x_config_id": config_id})
        return

    entity_id = integration.inc_entity_id
    config_json = integration.inc_config_json or {}

    # 2. Consent check
    has_consent = await check_consent(entity_id, "EMAIL_SCAN", session)
    if not has_consent:
        logger.warning("Consent not granted, skipping sync", extra={"x_config_id": config_id})
        return

    # 3. Ensure token freshness
    access_token = await ensure_fresh_token(config_id, session)

    # 4. Start audit (commit immediately so IN_PROGRESS is visible)
    audit = await audit_repo.start_audit(entity_id, config_id, "FULL_FETCH")
    await session.commit()

    # 5. Calculate date range
    days = min(settings.initial_fetch_days, settings.max_fetch_days)
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    filter_query = f"receivedDateTime ge {start_date}"

    counts = {"fetched": 0, "new": 0, "changed": 0, "pages": 0, "skipped": 0}

    try:
        # 6. Fetch inbox via delta endpoint (gets emails + delta token)
        access_token, inbox_delta = await _fetch_delta_folder_with_retry(
            access_token, config_id, "inbox", None,
            entity_id, ingest_repo, counts, session,
            filter_query=filter_query,
        )

        # 7. Fetch sent items via delta endpoint
        access_token, sent_delta = await _fetch_delta_folder_with_retry(
            access_token, config_id, "sentitems", None,
            entity_id, ingest_repo, counts, session,
            filter_query=filter_query,
        )

        # 8. Save delta tokens + mark complete
        config_json["inbox_delta_token"] = inbox_delta
        config_json["sent_delta_token"] = sent_delta
        config_json["delta_token_updated_at"] = datetime.now(timezone.utc).isoformat()
        config_json["sync_mode"] = "incremental"
        config_json["initial_sync_complete"] = True
        config_json["total_emails_synced"] = (
            config_json.get("total_emails_synced", 0) + counts["new"]
        )
        await integration_repo.update_tokens(config_id, config_json)
        await integration_repo.update_status(config_id, "CONNECTED")

        # 9. Complete audit
        await audit_repo.complete_audit(
            audit.esa_sync_id, "SUCCESS",
            emails_fetched=counts["fetched"],
            emails_new=counts["new"],
            emails_changed=counts["changed"],
            pages_fetched=counts["pages"],
        )

        logger.info(
            "Full fetch completed",
            extra={"x_config_id": config_id, "x_new": counts["new"], "x_pages": counts["pages"]},
        )

    except Exception as e:
        logger.error("Full fetch failed", exc_info=True, extra={"x_config_id": config_id})
        await audit_repo.complete_audit(
            audit.esa_sync_id, "FAILED", error_detail=str(e),
            emails_fetched=counts["fetched"], emails_new=counts["new"],
            emails_changed=counts["changed"], pages_fetched=counts["pages"],
        )
        raise


async def incremental_sync(config_id: int, session: AsyncSession) -> None:
    """Run incremental delta sync for an active integration."""
    integration_repo = IntegrationRepository(session)
    audit_repo = AuditRepository(session)
    ingest_repo = IngestRepository(session)

    # 1. Load config
    integration = await integration_repo.get_by_id("inc_config_id", config_id)
    if not integration:
        return

    entity_id = integration.inc_entity_id
    config_json = integration.inc_config_json or {}

    # 2. Consent check
    has_consent = await check_consent(entity_id, "EMAIL_SCAN", session)
    if not has_consent:
        logger.warning("Consent not granted, skipping sync", extra={"x_config_id": config_id})
        return

    # 3. Ensure token freshness
    access_token = await ensure_fresh_token(config_id, session)

    # 4. Start audit (commit immediately so IN_PROGRESS is visible)
    audit = await audit_repo.start_audit(entity_id, config_id, "INCREMENTAL")
    await session.commit()

    counts = {"fetched": 0, "new": 0, "changed": 0, "pages": 0, "skipped": 0}

    try:
        inbox_delta = config_json.get("inbox_delta_token")
        sent_delta = config_json.get("sent_delta_token")

        if inbox_delta and sent_delta:
            # 5a. Delta sync — have tokens, fetch only changes
            access_token, new_inbox_delta = await _fetch_delta_folder_with_retry(
                access_token, config_id, "inbox", inbox_delta,
                entity_id, ingest_repo, counts, session,
            )
            access_token, new_sent_delta = await _fetch_delta_folder_with_retry(
                access_token, config_id, "sentitems", sent_delta,
                entity_id, ingest_repo, counts, session,
            )
        else:
            # 5b. No delta tokens — use delta endpoint with date filter
            last_sync = integration.inc_last_sync_at
            if last_sync:
                since = (last_sync - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
            fallback_filter = f"receivedDateTime ge {since}"
            logger.info(
                "No delta tokens, using delta with date filter",
                extra={"x_config_id": config_id, "x_since": since},
            )
            access_token, new_inbox_delta = await _fetch_delta_folder_with_retry(
                access_token, config_id, "inbox", None,
                entity_id, ingest_repo, counts, session,
                filter_query=fallback_filter,
            )
            access_token, new_sent_delta = await _fetch_delta_folder_with_retry(
                access_token, config_id, "sentitems", None,
                entity_id, ingest_repo, counts, session,
                filter_query=fallback_filter,
            )

        # 7. Save state
        config_json["inbox_delta_token"] = new_inbox_delta or inbox_delta
        config_json["sent_delta_token"] = new_sent_delta or sent_delta
        config_json["delta_token_updated_at"] = datetime.now(timezone.utc).isoformat()
        config_json["total_emails_synced"] = (
            config_json.get("total_emails_synced", 0) + counts["new"]
        )
        await integration_repo.update_tokens(config_id, config_json)
        await integration_repo.update_by_id("inc_config_id", config_id, {
            "inc_last_sync_at": datetime.now(timezone.utc),
        })

        # 8. Complete audit
        await audit_repo.complete_audit(
            audit.esa_sync_id, "SUCCESS",
            emails_fetched=counts["fetched"],
            emails_new=counts["new"],
            emails_changed=counts["changed"],
            pages_fetched=counts["pages"],
        )

        logger.info(
            "Incremental sync completed",
            extra={"x_config_id": config_id, "x_new": counts["new"], "x_changed": counts["changed"]},
        )

    except Exception as e:
        logger.error("Incremental sync failed", exc_info=True, extra={"x_config_id": config_id})
        await audit_repo.complete_audit(
            audit.esa_sync_id, "FAILED", error_detail=str(e),
            emails_fetched=counts["fetched"], emails_new=counts["new"],
            emails_changed=counts["changed"], pages_fetched=counts["pages"],
        )
        raise


# ---------------------------------------------------------------------------
#  Fix 1: 401 retry wrappers — refresh token and retry on TokenExpiredError
# ---------------------------------------------------------------------------


async def _fetch_delta_folder_with_retry(
    access_token: str,
    config_id: int,
    folder: str,
    delta_token: str | None,
    entity_id: str,
    ingest_repo: IngestRepository,
    counts: dict[str, int],
    session: AsyncSession,
    filter_query: str | None = None,
) -> tuple[str, str | None]:
    """Fetch delta folder with 401 retry + 410 fallback. Returns (access_token, new_delta_link)."""
    try:
        new_delta = await _fetch_delta_folder(
            access_token, folder, delta_token, entity_id, config_id,
            ingest_repo, counts, session, filter_query=filter_query,
        )
        return access_token, new_delta
    except TokenExpiredError:
        logger.info("Token expired mid-delta, refreshing", extra={"x_config_id": config_id, "x_folder": folder})
        access_token = await ensure_fresh_token(config_id, session)
        new_delta = await _fetch_delta_folder(
            access_token, folder, delta_token, entity_id, config_id,
            ingest_repo, counts, session, filter_query=filter_query,
        )
        return access_token, new_delta
    except DeltaTokenExpiredError:
        # Stale delta — fall back to delta with date filter to get fresh token
        logger.warning(
            "Delta token expired, falling back to date-filtered delta",
            extra={"x_config_id": config_id, "x_folder": folder},
        )
        days = min(settings.initial_fetch_days, settings.max_fetch_days)
        start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
        fallback_filter = f"receivedDateTime ge {start_date}"
        new_delta = await _fetch_delta_folder(
            access_token, folder, None, entity_id, config_id,
            ingest_repo, counts, session, filter_query=fallback_filter,
        )
        return access_token, new_delta


# ---------------------------------------------------------------------------
#  Internal — folder fetching
# ---------------------------------------------------------------------------


async def _fetch_delta_folder(
    access_token: str,
    folder: str,
    delta_token: str | None,
    entity_id: str,
    config_id: int,
    ingest_repo: IngestRepository,
    counts: dict[str, int],
    session: AsyncSession,
    filter_query: str | None = None,
) -> str | None:
    """Fetch delta changes from a folder. Returns new delta link.

    When delta_token is provided: incremental sync using saved token.
    When filter_query is provided: initial fetch via delta with date filter.
    """
    result = await _email_provider.fetch_delta(
        access_token, folder, delta_token, filter_query=filter_query,
    )
    await _process_emails(result.messages, access_token, entity_id, config_id, ingest_repo, counts, session)
    counts["pages"] += 1

    while result.next_link:
        result = await _email_provider.fetch_delta(access_token, folder, result.next_link)
        await _process_emails(result.messages, access_token, entity_id, config_id, ingest_repo, counts, session)
        counts["pages"] += 1

    return result.delta_link


# ---------------------------------------------------------------------------
#  Fix 3, 4, 6: Process emails with S3 error handling, attachment error
#  handling, and batch commits
# ---------------------------------------------------------------------------


async def _process_emails(
    messages: list[EmailMessage],
    access_token: str,
    entity_id: str,
    config_id: int,
    ingest_repo: IngestRepository,
    counts: dict[str, int],
    session: AsyncSession,
) -> None:
    """Process a batch of emails with concurrent I/O.

    Phase 1: Filter — remove drafts, missing IDs, in-page duplicates
    Phase 2: Batch dedup — one IN query instead of N
    Phase 3: Batch attachment metadata — Graph $batch API (chunks of 20)
    Phase 4: Concurrent downloads + S3 uploads — asyncio.gather with semaphores
    Phase 5: Sequential DB writes — shared session, batch commit every BATCH_SIZE
    """
    # --- Phase 1: Filter ---
    seen: set[str] = set()
    valid_emails: list[EmailMessage] = []
    for email in messages:
        counts["fetched"] += 1
        if not email.internet_message_id:
            counts["skipped"] += 1
            continue
        if email.is_draft:
            continue
        if email.internet_message_id in seen:
            continue
        seen.add(email.internet_message_id)
        valid_emails.append(email)

    if not valid_emails:
        return

    # --- Phase 2: Batch dedup ---
    all_refs = [e.internet_message_id for e in valid_emails]
    existing_refs = await ingest_repo.exists_by_refs_batch(entity_id, all_refs)

    # --- Phase 3: Batch attachment metadata via $batch API ---
    emails_with_atts = [e for e in valid_emails if e.has_attachments]
    msg_ids_for_batch = [e.id for e in emails_with_atts]

    meta_map: dict[str, list[AttachmentMeta]] = {}
    if msg_ids_for_batch:
        try:
            meta_map = await _email_provider.fetch_attachments_metadata_batch(
                access_token, msg_ids_for_batch,
            )
        except Exception:
            logger.warning(
                "Batch attachment metadata fetch failed, skipping attachments",
                exc_info=True,
            )

    # --- Phase 4: Concurrent /$value downloads + S3 uploads ---
    graph_sem = asyncio.Semaphore(CONCURRENT_GRAPH_LIMIT)
    s3_sem = asyncio.Semaphore(CONCURRENT_S3_LIMIT)

    async def _process_one_email(
        email: EmailMessage,
    ) -> tuple[EmailMessage, str | None, list[dict[str, Any]]]:
        """Download attachments + upload to S3 for one email. Returns
        (email, s3_body_key_or_None, attachment_metadata)."""
        attachment_metadata: list[dict[str, Any]] = []
        att_metas = meta_map.get(email.id, [])

        # Download + upload each attachment concurrently
        async def _handle_attachment(
            att: AttachmentMeta,
        ) -> dict[str, Any] | None:
            try:
                async with graph_sem:
                    content = await _email_provider.download_attachment(
                        access_token, email.id, att.id,
                    )
                async with s3_sem:
                    s3_key = await store_attachment(
                        entity_id, email.internet_message_id,
                        att.id, att.name, content, att.content_type,
                        email.received_datetime or email.sent_datetime,
                    )
                return {
                    "id": att.id, "name": att.name,
                    "size": att.size, "contentType": att.content_type,
                    "s3_key": s3_key,
                }
            except Exception:
                logger.warning(
                    "Failed to download/store attachment, skipping",
                    exc_info=True,
                    extra={
                        "x_msg_id": email.internet_message_id,
                        "x_att_name": att.name,
                    },
                )
                return None

        if att_metas:
            att_results = await asyncio.gather(
                *[_handle_attachment(a) for a in att_metas],
            )
            attachment_metadata = [r for r in att_results if r is not None]

        # Build and upload body JSON to S3
        body_data = _build_body_data(email, attachment_metadata)
        try:
            async with s3_sem:
                s3_key = await store_email_body(
                    entity_id, email.internet_message_id, body_data,
                    email.received_datetime or email.sent_datetime,
                )
            return (email, s3_key, attachment_metadata)
        except Exception:
            logger.error(
                "Failed to store email body in S3, skipping email",
                exc_info=True,
                extra={"x_msg_id": email.internet_message_id},
            )
            return (email, None, attachment_metadata)

    upload_results = await asyncio.gather(
        *[_process_one_email(e) for e in valid_emails],
    )

    # --- Phase 5: Sequential DB writes ---
    batch_counter = 0
    for email, s3_body_key, attachment_metadata in upload_results:
        if s3_body_key is None:
            counts["skipped"] += 1
            continue

        metadata_payload = _build_metadata_payload(
            email, s3_body_key, attachment_metadata,
        )

        if email.internet_message_id in existing_refs:
            await ingest_repo.upsert_email(
                entity_id, email.internet_message_id, metadata_payload,
            )
            counts["changed"] += 1
        else:
            await ingest_repo.insert_email(
                entity_id, config_id, email.internet_message_id,
                email.conversation_id, metadata_payload,
            )
            counts["new"] += 1

        batch_counter += 1
        if batch_counter >= BATCH_SIZE:
            await session.commit()
            await extend_lock(config_id)
            batch_counter = 0

    if batch_counter > 0:
        await session.commit()


def _build_body_data(
    email: EmailMessage, attachment_metadata: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the S3 body JSON for an email."""
    data: dict[str, Any] = {
        "id": email.id,
        "internetMessageId": email.internet_message_id,
        "subject": email.subject,
        "from": {"name": email.from_name, "address": email.from_address},
        "toRecipients": email.to_recipients,
        "ccRecipients": email.cc_recipients,
        "bccRecipients": email.bcc_recipients,
        "body": {"contentType": email.body_content_type, "content": email.body_content},
        "receivedDateTime": email.received_datetime,
        "sentDateTime": email.sent_datetime,
        "isRead": email.is_read,
        "isDraft": email.is_draft,
        "importance": email.importance,
        "inferenceClassification": email.inference_classification,
        "flagStatus": email.flag_status,
        "hasAttachments": email.has_attachments,
    }
    if email.has_attachments:
        data["attachments"] = attachment_metadata
    return data


def _build_metadata_payload(
    email: EmailMessage,
    s3_body_key: str,
    attachment_metadata: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the Postgres metadata payload."""
    return {
        "internetMessageId": email.internet_message_id,
        "subject": email.subject,
        "from": email.from_address,
        "to": email.to_recipients,
        "cc": email.cc_recipients,
        "bcc": email.bcc_recipients,
        "receivedDateTime": email.received_datetime,
        "sentDateTime": email.sent_datetime,
        "hasAttachments": email.has_attachments,
        "attachmentCount": len(attachment_metadata),
        "s3_body_key": s3_body_key,
        "isRead": email.is_read,
        "importance": email.importance,
        "inferenceClassification": email.inference_classification,
        "flagStatus": email.flag_status,
        "conversationId": email.conversation_id,
        "parentFolderId": email.parent_folder_id,
    }
