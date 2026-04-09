-- =============================================================================
--  Migration 002: Entity Table (Tenant)
--  Tables: subscriber_entity
--  Root tenant table — every user, integration, and data row belongs to an entity.
-- =============================================================================


CREATE TABLE IF NOT EXISTS subscriber_entity (
    ent_entity_id            UUID          NOT NULL DEFAULT uuid_generate_v4(),
    ent_entity_name          VARCHAR(200)  NOT NULL,
    ent_domain               VARCHAR(255),
    ent_is_active            SMALLINT      NOT NULL DEFAULT 1,
    ent_created_by           VARCHAR(100),
    ent_created_on           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    ent_modified_by          VARCHAR(100),
    ent_modified_on          TIMESTAMPTZ,

    CONSTRAINT pk_subscriber_entity PRIMARY KEY (ent_entity_id)
);

CREATE INDEX IF NOT EXISTS idx_ent_domain    ON subscriber_entity (ent_domain);
CREATE INDEX IF NOT EXISTS idx_ent_is_active ON subscriber_entity (ent_is_active);
