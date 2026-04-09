-- =============================================================================
--  Migration 001: Auth Tables
--  Tables: user_master · user_security_details · user_authentication_history
--          role_master · user_role_mapping
--  Applied fixes: TIMESTAMPTZ everywhere, UUID for user_id, lowercase columns,
--                 lockout fields on user_master
-- =============================================================================


-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- 1. user_master
CREATE TABLE IF NOT EXISTS user_master (
    usm_user_id              UUID          NOT NULL DEFAULT uuid_generate_v4(),
    usm_user_display_name    VARCHAR(200),
    usm_user_first_name      VARCHAR(100),
    usm_user_last_name       VARCHAR(100),
    usm_entity_id            VARCHAR(100),
    usm_user_email_id        VARCHAR(255),
    usm_user_mobile_no       VARCHAR(30),
    usm_title_tag            VARCHAR(100),
    usm_department_tag       VARCHAR(100),
    usm_user_status          SMALLINT      NOT NULL DEFAULT 1,
    usm_failed_login_count   SMALLINT      NOT NULL DEFAULT 0,
    usm_locked_until         TIMESTAMPTZ,
    usm_created_by           VARCHAR(100),
    usm_created_on           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    usm_modified_by          VARCHAR(100),
    usm_modified_on          TIMESTAMPTZ,

    CONSTRAINT pk_user_master PRIMARY KEY (usm_user_id)
);

CREATE INDEX IF NOT EXISTS idx_usm_entity_id ON user_master (usm_entity_id);
CREATE INDEX IF NOT EXISTS idx_usm_email     ON user_master (usm_user_email_id);
CREATE INDEX IF NOT EXISTS idx_usm_status    ON user_master (usm_user_status);


-- 2. user_security_details
CREATE TABLE IF NOT EXISTS user_security_details (
    usd_user_id              UUID          NOT NULL,
    usd_hashed_pwd           VARCHAR(255),
    usd_hashed_pin           VARCHAR(255),
    usd_2fa_option           SMALLINT,
    usd_mobile_app_access    SMALLINT      NOT NULL DEFAULT 0,
    usd_api_access           SMALLINT      NOT NULL DEFAULT 0,
    usd_created_by           VARCHAR(100),
    usd_created_on           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    usd_modified_by          VARCHAR(100),
    usd_modified_on          TIMESTAMPTZ,

    CONSTRAINT pk_user_security_details PRIMARY KEY (usd_user_id)
);


-- 3. user_authentication_history
CREATE TABLE IF NOT EXISTS user_authentication_history (
    uah_user_id                      UUID          NOT NULL,
    uah_session_id                   VARCHAR(255)  NOT NULL,
    uah_ip_address                   VARCHAR(100),
    uah_invalid_login_attempt_count  SMALLINT      NOT NULL DEFAULT 0,
    uah_login_time                   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    uah_logout_time                  TIMESTAMPTZ,

    CONSTRAINT pk_user_auth_history PRIMARY KEY (uah_user_id, uah_session_id)
);

CREATE INDEX IF NOT EXISTS idx_uah_user_id    ON user_authentication_history (uah_user_id);
CREATE INDEX IF NOT EXISTS idx_uah_login_time ON user_authentication_history (uah_login_time);


-- 4. role_master
CREATE TABLE IF NOT EXISTS role_master (
    rom_role_id              VARCHAR(100)  NOT NULL,
    rom_role_name            VARCHAR(200)  NOT NULL,
    rom_role_description     TEXT,
    rom_is_active            SMALLINT      NOT NULL DEFAULT 1,
    rom_created_by           VARCHAR(100),
    rom_created_on           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    rom_modified_by          VARCHAR(100),
    rom_modified_on          TIMESTAMPTZ,

    CONSTRAINT pk_role_master PRIMARY KEY (rom_role_id)
);

-- Seed: default admin role
INSERT INTO role_master (rom_role_id, rom_role_name, rom_role_description, rom_created_by)
VALUES ('ADMIN', 'Administrator', 'Full platform access', 'system')
ON CONFLICT (rom_role_id) DO NOTHING;


-- 5. user_role_mapping
CREATE TABLE IF NOT EXISTS user_role_mapping (
    urm_mapping_id           SERIAL        NOT NULL,
    urm_mapped_user_id       UUID          NOT NULL,
    urm_role_id              VARCHAR(100)  NOT NULL,
    urm_record_status        SMALLINT      NOT NULL DEFAULT 1,
    urm_created_by           VARCHAR(100),
    urm_created_on           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    urm_modified_by          VARCHAR(100),
    urm_modified_on          TIMESTAMPTZ,

    CONSTRAINT pk_user_role_mapping PRIMARY KEY (urm_mapping_id)
);

CREATE INDEX IF NOT EXISTS idx_urm_user_id ON user_role_mapping (urm_mapped_user_id, urm_record_status);
