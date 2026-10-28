-- Enterprise readiness B: the authenticated user (from the SSO gateway) of each audited call. NULL in auth mode
-- none (development), where there is no user.
ALTER TABLE quality.access_audit ADD COLUMN user_id TEXT;
CREATE INDEX access_audit_user_idx ON quality.access_audit (user_id, created_at DESC);
