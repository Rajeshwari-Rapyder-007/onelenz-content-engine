-- =============================================================================
--  Migration 003: Email Connector Tables
--  Tables: integration_config · consent_management · email_sync_audit · raw_ingest_log
--  Used by: email-connector service (M365 + future Gmail)
-- =============================================================================


-- 1. integration_config
-- One row per user per provider. Stores OAuth tokens and sync state.
CREATE TABLE IF NOT EXISTS integration_config (
    inc_config_id            SERIAL        NOT NULL,
    inc_entity_id            VARCHAR(50)   NOT NULL,
    inc_user_id              VARCHAR(50)   NOT NULL,
    inc_integration_type     VARCHAR(20)   NOT NULL,
    inc_provider             VARCHAR(20)   NOT NULL,
    inc_auth_status          VARCHAR(20)   NOT NULL DEFAULT 'PENDING',
    inc_sync_frequency       VARCHAR(20),
    inc_last_sync_at         TIMESTAMPTZ,
    inc_is_active            BOOLEAN       NOT NULL DEFAULT TRUE,
    inc_config_json          JSONB,
    inc_created_by           VARCHAR(50),
    inc_created_on           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    inc_modified_by          VARCHAR(50),
    inc_modified_on          TIMESTAMPTZ,

    CONSTRAINT pk_integration_config PRIMARY KEY (inc_config_id)
);

CREATE INDEX IF NOT EXISTS idx_inc_entity_id     ON integration_config (inc_entity_id);
CREATE INDEX IF NOT EXISTS idx_inc_user_id       ON integration_config (inc_user_id);
CREATE INDEX IF NOT EXISTS idx_inc_type_provider ON integration_config (inc_integration_type, inc_provider);
CREATE INDEX IF NOT EXISTS idx_inc_is_active     ON integration_config (inc_is_active);
CREATE INDEX IF NOT EXISTS idx_inc_config_json   ON integration_config USING GIN (inc_config_json);


-- 2. consent_management
-- Per-entity per-type scanning consent. Checked before every sync run.
CREATE TABLE IF NOT EXISTS consent_management (
    cm_id                    SERIAL        NOT NULL,
    cm_entity_id             VARCHAR(50)   NOT NULL,
    cm_user_id               VARCHAR(50)   NOT NULL,
    cm_consent_type          VARCHAR(20)   NOT NULL,
    cm_domain_scope          VARCHAR(100),
    cm_is_granted            BOOLEAN       NOT NULL DEFAULT TRUE,
    cm_granted_by            VARCHAR(50),
    cm_granted_at            TIMESTAMPTZ,
    cm_revoked_at            TIMESTAMPTZ,
    cm_created_on            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_consent_management PRIMARY KEY (cm_id)
);

CREATE INDEX IF NOT EXISTS idx_cm_entity_type ON consent_management (cm_entity_id, cm_consent_type);
CREATE INDEX IF NOT EXISTS idx_cm_is_granted  ON consent_management (cm_is_granted);


-- 3. raw_ingest_log
-- Shared staging table for all ingested signal candidates (email, meeting, CRM).
CREATE TABLE IF NOT EXISTS raw_ingest_log (
    ril_id                   BIGSERIAL     NOT NULL,
    ril_entity_id            VARCHAR(50)   NOT NULL,
    ril_source_tag           VARCHAR(20)   NOT NULL,
    ril_integration_cfg_id   INT,
    ril_source_ref_id        VARCHAR(500),
    ril_conversation_id      VARCHAR(255),
    ril_raw_payload          JSONB,
    ril_meeting_ref_id       BIGINT,
    ril_source_id            VARCHAR(500),
    ril_dedup_hash           VARCHAR(64),
    ril_signals_generated    INT,
    ril_ingest_status        VARCHAR(30)   NOT NULL DEFAULT 'QUEUED',
    ril_queued_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    ril_processed_at         TIMESTAMPTZ,
    ril_error_msg            TEXT,
    ril_created_on           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    ril_modified_on          TIMESTAMPTZ,

    CONSTRAINT pk_raw_ingest_log PRIMARY KEY (ril_id)
);

CREATE INDEX IF NOT EXISTS idx_ril_entity_id       ON raw_ingest_log (ril_entity_id);
CREATE INDEX IF NOT EXISTS idx_ril_source_tag      ON raw_ingest_log (ril_source_tag);
CREATE INDEX IF NOT EXISTS idx_ril_ingest_status   ON raw_ingest_log (ril_ingest_status);
CREATE INDEX IF NOT EXISTS idx_ril_source_ref_id   ON raw_ingest_log (ril_source_ref_id);
CREATE INDEX IF NOT EXISTS idx_ril_conversation_id ON raw_ingest_log (ril_conversation_id);
CREATE INDEX IF NOT EXISTS idx_ril_meeting_ref     ON raw_ingest_log (ril_meeting_ref_id);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_ril_dedup_hash ON raw_ingest_log (ril_dedup_hash)
    WHERE ril_dedup_hash IS NOT NULL;


-- 4. email_sync_audit
-- One row per sync run. Tracks every full fetch and incremental sync.
CREATE TABLE IF NOT EXISTS email_sync_audit (
    esa_sync_id              BIGSERIAL     NOT NULL,
    esa_entity_id            VARCHAR(50)   NOT NULL,
    esa_config_id            INT           NOT NULL,
    esa_sync_type            VARCHAR(20)   NOT NULL,
    esa_started_at           TIMESTAMPTZ   NOT NULL,
    esa_ended_at             TIMESTAMPTZ,
    esa_emails_fetched       INT           NOT NULL DEFAULT 0,
    esa_emails_new           INT           NOT NULL DEFAULT 0,
    esa_emails_changed       INT           NOT NULL DEFAULT 0,
    esa_pages_fetched        INT           NOT NULL DEFAULT 0,
    esa_status               VARCHAR(20)   NOT NULL DEFAULT 'SUCCESS',
    esa_error_detail         TEXT,
    esa_created_on           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_email_sync_audit PRIMARY KEY (esa_sync_id)
);

CREATE INDEX IF NOT EXISTS idx_esa_entity_id  ON email_sync_audit (esa_entity_id);
CREATE INDEX IF NOT EXISTS idx_esa_config_id  ON email_sync_audit (esa_config_id);
CREATE INDEX IF NOT EXISTS idx_esa_created_on ON email_sync_audit (esa_created_on);
