-- Run once in pgAdmin (Query Tool) before using the edit screens.
-- Keeps a history of every outlet change, like activation_changes does for activations.

CREATE TABLE IF NOT EXISTS outlet_changes (
  id          int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  outlet_id   int NOT NULL REFERENCES outlets(id) ON DELETE CASCADE,
  old_row     jsonb NOT NULL,
  changed_at  timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION log_outlet_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO outlet_changes (outlet_id, old_row) VALUES (OLD.id, to_jsonb(OLD));
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_outlet_history ON outlets;
CREATE TRIGGER trg_outlet_history
AFTER UPDATE ON outlets
FOR EACH ROW
WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE FUNCTION log_outlet_change();
