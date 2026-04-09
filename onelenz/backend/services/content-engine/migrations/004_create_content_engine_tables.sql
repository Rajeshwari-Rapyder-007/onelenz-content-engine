-- =============================================================================
--  Migration 004: Content Engine Tables
--  Tables: content_category · content_asset · content_chunk
--  Used by: content-engine service (document ingestion, chunking, embeddings)
-- =============================================================================


-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- 1. content_category
-- Lookup table for asset categories. Readable string PKs.
CREATE TABLE IF NOT EXISTS content_category (
    cc_category_id           VARCHAR(50)   NOT NULL,
    cc_category_name         VARCHAR(100)  NOT NULL,
    cc_description           VARCHAR(500),

    CONSTRAINT pk_content_category PRIMARY KEY (cc_category_id)
);

-- Seed: default categories
INSERT INTO content_category (cc_category_id, cc_category_name, cc_description)
VALUES
    ('MARKETING_COLLATERAL', 'Marketing Collaterals', NULL),
    ('SOW_PROJECT_DOC',      'SoWs or Project Documents', NULL),
    ('PRODUCT_WORKBOOK',     'Product Workbook or Catalog', NULL),
    ('CASE_STUDY',           'Case Studies', NULL),
    ('BLOG',                 'Blogs or Similar', NULL),
    ('PRESS_RELEASE',        'Press Release / Official News / Others', NULL),
    ('WEBSITE_PAGE',         'Homepage and Other Customer-Facing Websites', NULL),
    ('SOCIAL_MEDIA',         'Social Media Pages or Similar', NULL)
ON CONFLICT (cc_category_id) DO NOTHING;


-- 2. content_asset
-- One row per uploaded/ingested document or file.
CREATE TABLE IF NOT EXISTS content_asset (
    ca_asset_id              UUID          NOT NULL DEFAULT uuid_generate_v4(),
    ca_entity_id             UUID          NOT NULL,
    ca_category_id           VARCHAR(50),
    ca_source_type           VARCHAR(20)   NOT NULL,
    ca_file_name             VARCHAR(500)  NOT NULL,
    ca_file_type             VARCHAR(20),
    ca_file_size_bytes       BIGINT,
    ca_page_count            INTEGER,
    ca_s3_key                VARCHAR(1000),
    ca_status                VARCHAR(20)   NOT NULL DEFAULT 'PENDING',
    ca_error_message         TEXT,
    ca_chunk_count           INTEGER,
    ca_credits_consumed      DECIMAL(10,2),
    created_by               VARCHAR(100),
    created_on               TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    modified_by              VARCHAR(100),
    modified_on              TIMESTAMPTZ,

    CONSTRAINT pk_content_asset PRIMARY KEY (ca_asset_id)
);

CREATE INDEX IF NOT EXISTS idx_ca_entity_id       ON content_asset (ca_entity_id);
CREATE INDEX IF NOT EXISTS idx_ca_status          ON content_asset (ca_status);
CREATE INDEX IF NOT EXISTS idx_ca_entity_category ON content_asset (ca_entity_id, ca_category_id);


-- 3. content_chunk
-- One row per chunk extracted from an asset. Includes pgvector embedding.
CREATE TABLE IF NOT EXISTS content_chunk (
    ck_chunk_id              UUID          NOT NULL DEFAULT uuid_generate_v4(),
    ck_asset_id              UUID          NOT NULL,
    ck_entity_id             UUID          NOT NULL,
    ck_category_id           VARCHAR(50)   NULL,
    ck_chunk_index           INTEGER       NOT NULL,
    ck_content_text          TEXT          NOT NULL,
    ck_section_heading       VARCHAR(500),
    ck_source_page           INTEGER,
    ck_source_url            VARCHAR(2000),
    ck_token_count           INTEGER       NOT NULL,
    ck_data_origin           VARCHAR(30)   NOT NULL DEFAULT 'SUBSCRIBER_UPLOADED',
    ck_metadata              JSONB         NOT NULL DEFAULT '{}',
    ck_embedding             vector(1024),
    created_by               VARCHAR(100),
    created_on               TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    modified_by              VARCHAR(100),
    modified_on              TIMESTAMPTZ,

    CONSTRAINT pk_content_chunk PRIMARY KEY (ck_chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_ck_asset_id  ON content_chunk (ck_asset_id);
CREATE INDEX IF NOT EXISTS idx_ck_entity_id ON content_chunk (ck_entity_id);
CREATE INDEX IF NOT EXISTS idx_ck_embedding ON content_chunk
    USING hnsw (ck_embedding vector_cosine_ops);
