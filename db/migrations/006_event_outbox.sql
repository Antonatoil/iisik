-- Applied to EACH existing owner database during Lab 6 deploy.
-- No table from Labs 3-5 is dropped; safe for existing persistent volumes.
CREATE TABLE IF NOT EXISTS event_outbox (
    event_id uuid PRIMARY KEY,
    topic text NOT NULL,
    partition_key text NOT NULL,
    envelope jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);
CREATE INDEX IF NOT EXISTS event_outbox_pending
ON event_outbox(created_at, event_id) WHERE published_at IS NULL;
CREATE TABLE IF NOT EXISTS event_inbox (
    event_id uuid PRIMARY KEY,
    event_type varchar(40) NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now()
);
-- The deployment migration runs as lab_admin. Explicitly grant the owner role
-- access to newly created tables, otherwise svc_l/svc_x cannot stage events.
DO $$
DECLARE service_role text := 'svc_' || right(current_database(), 1);
BEGIN
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE event_outbox, event_inbox TO %I', service_role);
END $$;
