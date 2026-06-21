-- Create or update the non-owner runtime role used by the application.
--
-- Placeholders below are replaced at migration time. The role/password values
-- are quoted as SQL literals before substitution and then passed to Postgres
-- via format() with %I/%L for additional safety.

DO $body$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = __APP_USER_SQL__) THEN
        EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', __APP_USER_SQL__, __APP_PASSWORD_SQL__);
    ELSE
        EXECUTE format('ALTER ROLE %I LOGIN PASSWORD %L', __APP_USER_SQL__, __APP_PASSWORD_SQL__);
    END IF;
END
$body$;

GRANT USAGE ON SCHEMA public TO __APP_ROLE_IDENT__;
GRANT USAGE ON SCHEMA app TO __APP_ROLE_IDENT__;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO __APP_ROLE_IDENT__;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO __APP_ROLE_IDENT__;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO __APP_ROLE_IDENT__;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO __APP_ROLE_IDENT__;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO __APP_ROLE_IDENT__;
