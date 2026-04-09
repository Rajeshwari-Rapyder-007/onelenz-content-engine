-- =============================================================================
--  Setup Script: Database + App User
--  Run ONCE as the RDS master user before any other migrations.
--
--  Usage:
--    psql -h <rds-host> -U <master_user> -d postgres -f 000_setup_database.sql
--
--  This script:
--    1. Creates the onelenz database
--    2. Creates the dev_app user (data-only, no schema permissions)
--    3. Grants SELECT, INSERT, UPDATE, DELETE on all current and future tables
--    4. Grants sequence usage for SERIAL/BIGSERIAL columns
-- =============================================================================

-- 1. Create database (run connected to 'postgres' default DB)
CREATE DATABASE onelenz;

-- 2. Create app user (change password before running in production)
CREATE USER dev_app WITH PASSWORD 'change-me-strong-password';

-- 3. Connect to onelenz database and set up permissions
\c onelenz

-- Enable UUID extension (needed by migrations)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Grant schema usage (can use public schema, but cannot create/alter objects)
GRANT USAGE ON SCHEMA public TO dev_app;

-- Grant data-only permissions on all existing tables
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO dev_app;

-- Auto-grant data-only permissions on all future tables created by current user
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dev_app;

-- Grant sequence usage (for SERIAL/BIGSERIAL auto-increment columns)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO dev_app;

-- Auto-grant sequence usage on all future sequences created by current user
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT USAGE, SELECT ON SEQUENCES TO dev_app;
