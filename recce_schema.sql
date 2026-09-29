-- =====================================================================
-- RECCE / ACTIVATION REPORTS DATABASE  (PostgreSQL 12+)
-- =====================================================================
-- Run once with:  psql -d your_db -f recce_schema.sql
--
-- HOW DATA FLOWS
--   1. Python (pandas/openpyxl) reads a weekly Excel file, cleans it
--      (dates, times, phones, stock) and computes the file's SHA-256.
--   2. INSERT one row into import_batches  (skip the file if its hash
--      already exists = byte-identical duplicate).
--   3. Bulk-insert the cleaned rows into staging_activations.
--   4. SELECT * FROM ingest_batch(<batch_id>);
--        -> matches outlets, upserts staff + activations, reports counts.
--   5. Rows that could not be matched land in import_review. Fix them
--      (add an alias, or re-run with auto-create) and call
--      ingest_batch(<batch_id>) again: it is safe to re-run.
--
-- Different versions of the same week's file (50 rows, then 55 rows,
-- forks passed around WhatsApp) are merged: new rows are inserted,
-- changed rows are updated, identical rows are left alone, and nothing
-- is ever deleted.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- HELPER FUNCTIONS
-- ---------------------------------------------------------------------

-- Turns any outlet name into a comparable key:
-- 'Naivas  Embu-Pearl ' -> 'naivas embu pearl'
CREATE OR REPLACE FUNCTION normalize_key(t text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT nullif(btrim(regexp_replace(lower(coalesce(t, '')), '[^a-z0-9]+', ' ', 'g')), '')
$$;

-- Normalises Kenyan phone numbers to +2547XXXXXXXX / +2541XXXXXXXX.
-- Returns NULL for anything it cannot recognise (e.g. '07123456u8').
CREATE OR REPLACE FUNCTION normalize_phone(t text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE
            WHEN d ~ '^254[71][0-9]{8}$' THEN '+' || d
            WHEN d ~ '^0[71][0-9]{8}$'   THEN '+254' || substr(d, 2)
            WHEN d ~ '^[71][0-9]{8}$'    THEN '+254' || d
            ELSE NULL
         END
  FROM (SELECT nullif(regexp_replace(coalesce(t, ''), '[^0-9]', '', 'g'), '')) AS x(d)
$$;

-- "Today" in Nairobi, so the 2-week views do not flip at the wrong hour
-- when the database server runs in UTC.
CREATE OR REPLACE FUNCTION today_ke() RETURNS date
LANGUAGE sql STABLE AS $$
  SELECT (now() AT TIME ZONE 'Africa/Nairobi')::date
$$;

-- ---------------------------------------------------------------------
-- TABLE: import_batches
-- One row per Excel file received. It is an audit log (what came in,
-- when, from whom, what it changed), NOT the thing that decides which
-- data exists. file_sha256 is UNIQUE so a byte-identical file is only
-- loaded once; different versions of a file have different hashes.
-- ---------------------------------------------------------------------
CREATE TABLE import_batches (
  id              int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  file_name       text        NOT NULL,
  file_sha256     text        NOT NULL UNIQUE,
  report_week     int,                        -- e.g. 10 (from the file name / content)
  sender          text,                       -- optional: who posted it in the group
  source_modified timestamptz,                -- Excel's own "last modified" property
  imported_at     timestamptz NOT NULL DEFAULT now(),
  rows_total      int,                        -- rows read from the file
  rows_inserted   int         NOT NULL DEFAULT 0,
  rows_updated    int         NOT NULL DEFAULT 0,
  rows_unchanged  int         NOT NULL DEFAULT 0
);
COMMENT ON TABLE import_batches IS
  'Audit log: one row per Excel file ingested, with row counts of what it inserted/updated.';

-- ---------------------------------------------------------------------
-- TABLE: outlets
-- Master list: one row per physical outlet, no matter how many weeks or
-- how many times it was activated. Matching is by KE number when there
-- is one (THT outlets have none), otherwise by the normalised name.
-- ---------------------------------------------------------------------
CREATE TABLE outlets (
  id           int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ke_number    text,                          -- 'N/A' in Excel becomes NULL
  name         text NOT NULL,                 -- "Outlet Name - Location" column
  physical_loc text,                          -- "Physical Location" column
  channel      text,                          -- Ontrade / Offtrade / THT
  division     text,                          -- Mountain / Lake / Coast / Rift
  name_key     text GENERATED ALWAYS AS (normalize_key(name)) STORED,
  created_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT outlets_name_key_present CHECK (name_key IS NOT NULL),
  CONSTRAINT outlets_name_key_uk UNIQUE (name_key)
);
CREATE UNIQUE INDEX outlets_ke_number_uk ON outlets (ke_number) WHERE ke_number IS NOT NULL;
CREATE INDEX outlets_division_idx ON outlets (division);
COMMENT ON TABLE outlets IS
  'Master list of outlets. One row per outlet regardless of week; matched by KE number or normalised name.';

-- ---------------------------------------------------------------------
-- TABLE: outlet_aliases
-- Alternative spellings people typed for an outlet. Once you map
-- "Naivas Embu Pearl" -> outlet 12, every future import resolves it
-- automatically instead of creating a duplicate outlet.
-- ---------------------------------------------------------------------
CREATE TABLE outlet_aliases (
  alias_key  text PRIMARY KEY,                -- normalize_key() of the alternative spelling
  outlet_id  int  NOT NULL REFERENCES outlets(id) ON DELETE CASCADE
);
COMMENT ON TABLE outlet_aliases IS
  'Known alternative spellings of outlet names, mapped to the real outlet.';

-- ---------------------------------------------------------------------
-- TABLE: staff
-- KDMs, TMRs and Team Leads in one table, distinguished by role.
-- A person is unique per (role, name, phone).
-- ---------------------------------------------------------------------
CREATE TABLE staff (
  id         int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name       text NOT NULL,
  phone      text,                            -- normalised, e.g. +254721798839
  role       text NOT NULL CHECK (role IN ('KDM', 'TMR', 'TEAM_LEAD')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX staff_person_uk ON staff (role, lower(btrim(name)), (coalesce(phone, '')));
COMMENT ON TABLE staff IS
  'People from the report: KDM, TMR and Team Lead, distinguished by role.';

-- ---------------------------------------------------------------------
-- TABLE: activations
-- One row per outlet activation date, carrying TMR / KDM / Team Lead,
-- kickoff time, stock, prices and comments. 
-- Unique constraint removed to support multi-day / multiple activations.
-- ---------------------------------------------------------------------
CREATE TABLE activations (
  id                int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  outlet_id         int  NOT NULL REFERENCES outlets(id),
  activation_date   date NOT NULL,
  recce_date        date,
  kickoff_time      time,
  kdm_id            int REFERENCES staff(id),
  tmr_id            int REFERENCES staff(id),
  team_lead_id      int REFERENCES staff(id),
  stock_qty         numeric,                   -- "6 Cases" -> 6, "312 pcs" -> 312
  stock_unit        text,                      -- 'cases' or 'pcs'
  price_can         numeric,
  price_bottle      numeric,
  comments          text,
  first_batch_id    int NOT NULL REFERENCES import_batches(id),  -- file that first brought this row
  last_batch_id     int NOT NULL REFERENCES import_batches(id),  -- file that last changed it
  row_hash          text NOT NULL,             -- fingerprint of the data columns, to detect changes
  source_modified   timestamptz,               -- "last modified" of the file that wrote it
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX activations_outlet_date_idx ON activations (outlet_id, activation_date DESC);
CREATE INDEX activations_date_idx        ON activations (activation_date);
CREATE INDEX activations_tmr_idx         ON activations (tmr_id);
COMMENT ON TABLE activations IS
  'One row per outlet per activation date, with TMR/KDM/Team Lead, stock, prices and comments.';

-- ---------------------------------------------------------------------
-- TABLE: activation_changes
-- History: whenever a later file version changes an existing
-- activation (e.g. stock 10 -> 12), the OLD row is saved here as JSON.
-- ---------------------------------------------------------------------
CREATE TABLE activation_changes (
  id             int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  activation_id  int NOT NULL REFERENCES activations(id) ON DELETE CASCADE,
  batch_id       int REFERENCES import_batches(id),  -- the batch that caused the change
  old_row        jsonb NOT NULL,
  changed_at     timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE activation_changes IS
  'Audit trail: previous values of an activation each time a newer file changed it.';

CREATE OR REPLACE FUNCTION log_activation_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO activation_changes (activation_id, batch_id, old_row)
  VALUES (OLD.id, NEW.last_batch_id, to_jsonb(OLD));
  RETURN NEW;
END $$;

CREATE TRIGGER trg_activation_history
AFTER UPDATE ON activations
FOR EACH ROW
WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE FUNCTION log_activation_change();

-- ---------------------------------------------------------------------
-- TABLE: staging_activations
-- Landing zone. The Python loader dumps the CLEANED Excel rows here
-- (one row per Excel row); ingest_batch() then processes them.
-- Successfully processed rows are deleted; rows that failed stay.
-- ---------------------------------------------------------------------
CREATE UNLOGGED TABLE staging_activations (
  id               int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  batch_id         int NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
  row_num          int NOT NULL,              -- row number in the Excel file
  ke_number        text,
  outlet_name      text,
  physical_loc     text,
  channel          text,
  division         text,
  kdm_name         text,  kdm_phone   text,
  tmr_name         text,  tmr_phone   text,
  tl_name          text,  tl_phone    text,
  recce_date       date,
  activation_date  date,
  kickoff_time     time,
  stock_qty        numeric,
  stock_unit       text,
  price_can        numeric,
  price_bottle     numeric,
  comments         text,
  outlet_id        int                        -- filled in by ingest_batch()
);
CREATE INDEX staging_batch_idx ON staging_activations (batch_id);
COMMENT ON TABLE staging_activations IS
  'Temporary landing zone for cleaned Excel rows before matching and upsert.';

-- ---------------------------------------------------------------------
-- TABLE: import_review
-- Rows ingest_batch() could not load (unknown outlet, missing or
-- invalid activation date). Fix the cause, then re-run ingest_batch().
-- ---------------------------------------------------------------------
CREATE TABLE import_review (
  id          int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  batch_id    int NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
  row_num     int,
  reason      text NOT NULL,
  payload     jsonb NOT NULL,                -- the offending row
  created_at  timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE import_review IS
  'Queue of rows that could not be imported automatically and need a human decision.';

-- ---------------------------------------------------------------------
-- LOOKUP HELPERS used by ingest_batch()
-- ---------------------------------------------------------------------

-- Finds the outlet for a row: KE number first, then alias, then name.
CREATE OR REPLACE FUNCTION resolve_outlet(p_ke text, p_name text) RETURNS int
LANGUAGE sql STABLE AS $$
  SELECT COALESCE(
    (SELECT id FROM outlets WHERE p_ke IS NOT NULL AND ke_number = upper(btrim(p_ke))),
    (SELECT outlet_id FROM outlet_aliases WHERE alias_key = normalize_key(p_name)),
    (SELECT id FROM outlets WHERE name_key = normalize_key(p_name))
  )
$$;

-- Finds a staff member id by role + name + phone.
CREATE OR REPLACE FUNCTION find_staff(p_role text, p_name text, p_phone text) RETURNS int
LANGUAGE sql STABLE AS $$
  SELECT id FROM staff
  WHERE role = p_role
    AND lower(btrim(name)) = lower(btrim(p_name))
    AND coalesce(phone, '') = coalesce(normalize_phone(p_phone), '')
  LIMIT 1
$$;

-- Convenience: map a spelling variant to an existing outlet.
CREATE OR REPLACE FUNCTION add_outlet_alias(p_alias text, p_outlet_id int) RETURNS void
LANGUAGE sql AS $$
  INSERT INTO outlet_aliases (alias_key, outlet_id)
  VALUES (normalize_key(p_alias), p_outlet_id)
  ON CONFLICT (alias_key) DO UPDATE SET outlet_id = EXCLUDED.outlet_id
$$;

-- ---------------------------------------------------------------------
-- FUNCTION: ingest_batch(batch_id, auto_create_outlets)
-- Processes the staged rows of one batch (adapted for multi-day/multiple activations)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ingest_batch(p_batch_id int, p_auto_create_outlets boolean DEFAULT false)
RETURNS TABLE (o_total int, o_inserted int, o_updated int, o_unchanged int, o_review int)
LANGUAGE plpgsql AS $$
DECLARE
  v_mod     timestamptz;
  v_total   int;
  v_src     int := 0;
  v_ins     int := 0;
  v_upd     int := 0;
  v_review  int := 0;
BEGIN
  SELECT coalesce(b.source_modified, b.imported_at) INTO v_mod
  FROM import_batches b WHERE b.id = p_batch_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'import batch % not found', p_batch_id;
  END IF;

  SELECT count(*) INTO v_total FROM staging_activations WHERE batch_id = p_batch_id;

  -- 1. Staff -----------------------------------------------------------
  INSERT INTO staff (role, name, phone)
  SELECT DISTINCT ON (x.role, lower(btrim(x.name)), coalesce(x.phone, ''))
         x.role, btrim(x.name), x.phone
  FROM (
    SELECT 'KDM'::text AS role, kdm_name AS name, normalize_phone(kdm_phone) AS phone
      FROM staging_activations WHERE batch_id = p_batch_id
    UNION ALL
    SELECT 'TMR', tmr_name, normalize_phone(tmr_phone)
      FROM staging_activations WHERE batch_id = p_batch_id
    UNION ALL
    SELECT 'TEAM_LEAD', tl_name, normalize_phone(tl_phone)
      FROM staging_activations WHERE batch_id = p_batch_id
  ) x
  WHERE x.name IS NOT NULL AND btrim(x.name) <> ''
  ORDER BY x.role, lower(btrim(x.name)), coalesce(x.phone, '')
  ON CONFLICT (role, lower(btrim(name)), (coalesce(phone, ''))) DO NOTHING;

  -- 2. Outlets ---------------------------------------------------------
  UPDATE staging_activations s
     SET outlet_id = resolve_outlet(s.ke_number, s.outlet_name)
   WHERE s.batch_id = p_batch_id AND s.outlet_id IS NULL;

  IF p_auto_create_outlets THEN
    INSERT INTO outlets (ke_number, name, physical_loc, channel, division)
    SELECT DISTINCT ON (normalize_key(s.outlet_name))
           upper(btrim(s.ke_number)), btrim(s.outlet_name), s.physical_loc, s.channel, s.division
    FROM staging_activations s
    WHERE s.batch_id = p_batch_id
      AND s.outlet_id IS NULL
      AND normalize_key(s.outlet_name) IS NOT NULL
    ORDER BY normalize_key(s.outlet_name), s.row_num DESC
    ON CONFLICT DO NOTHING;

    UPDATE staging_activations s
       SET outlet_id = resolve_outlet(s.ke_number, s.outlet_name)
     WHERE s.batch_id = p_batch_id AND s.outlet_id IS NULL;
  END IF;

  -- Fill blanks on known outlets (never overwrite existing values)
  UPDATE outlets o
     SET ke_number    = CASE WHEN o.ke_number IS NULL
                             AND x.ke_number IS NOT NULL
                             AND NOT EXISTS (SELECT 1 FROM outlets o2 WHERE o2.ke_number = x.ke_number)
                            THEN x.ke_number ELSE o.ke_number END,
         physical_loc = coalesce(o.physical_loc, x.physical_loc),
         channel      = coalesce(o.channel, x.channel),
         division     = coalesce(o.division, x.division)
    FROM (
      SELECT DISTINCT ON (s.outlet_id)
             s.outlet_id, upper(btrim(s.ke_number)) AS ke_number,
             s.physical_loc, s.channel, s.division
      FROM staging_activations s
      WHERE s.batch_id = p_batch_id AND s.outlet_id IS NOT NULL
      ORDER BY s.outlet_id, s.row_num DESC
    ) x
   WHERE o.id = x.outlet_id;

  -- 3. Review queue ----------------------------------------------------
  DELETE FROM import_review WHERE batch_id = p_batch_id;

  INSERT INTO import_review (batch_id, row_num, reason, payload)
  SELECT s.batch_id, s.row_num,
         CASE WHEN s.outlet_id IS NULL THEN 'unmatched outlet'
              ELSE 'missing or invalid activation date' END,
         to_jsonb(s)
  FROM staging_activations s
  WHERE s.batch_id = p_batch_id
    AND (s.outlet_id IS NULL OR s.activation_date IS NULL);
  GET DIAGNOSTICS v_review = ROW_COUNT;

  -- 4. Upsert activations (without relying on unique constraint) --------
  DROP TABLE IF EXISTS tmp_src;
  CREATE TEMP TABLE tmp_src ON COMMIT DROP AS
  SELECT x.*,
         md5(ROW(x.kdm_id, x.tmr_id, x.team_lead_id, x.recce_date, x.kickoff_time,
                 x.stock_qty, x.stock_unit, x.price_can, x.price_bottle, x.comments)::text) AS row_hash
  FROM (
    SELECT DISTINCT ON (s.outlet_id, s.activation_date)
           s.outlet_id, s.activation_date,
           find_staff('KDM',        s.kdm_name, s.kdm_phone) AS kdm_id,
           find_staff('TMR',        s.tmr_name, s.tmr_phone)  AS tmr_id,
           find_staff('TEAM_LEAD', s.tl_name,  s.tl_phone)    AS team_lead_id,
           s.recce_date, s.kickoff_time, s.stock_qty, s.stock_unit,
           s.price_can, s.price_bottle, btrim(s.comments) AS comments
    FROM staging_activations s
    WHERE s.batch_id = p_batch_id
      AND s.outlet_id IS NOT NULL
      AND s.activation_date IS NOT NULL
    ORDER BY s.outlet_id, s.activation_date, s.row_num DESC
  ) x;

  SELECT count(*) INTO v_src FROM tmp_src;

  -- Update existing matching activation records
  WITH upd AS (
    UPDATE activations a
       SET recce_date      = t.recce_date,
           kickoff_time    = t.kickoff_time,
           kdm_id          = t.kdm_id,
           tmr_id          = t.tmr_id,
           team_lead_id    = t.team_lead_id,
           stock_qty       = t.stock_qty,
           stock_unit      = t.stock_unit,
           price_can       = t.price_can,
           price_bottle    = t.price_bottle,
           comments        = t.comments,
           last_batch_id   = p_batch_id,
           row_hash        = t.row_hash,
           source_modified = v_mod,
           updated_at      = now()
      FROM tmp_src t
     WHERE a.outlet_id = t.outlet_id
       AND a.activation_date = t.activation_date
       AND a.row_hash IS DISTINCT FROM t.row_hash
       AND v_mod >= coalesce(a.source_modified, '-infinity')
    RETURNING a.id
  )
  SELECT count(*) INTO v_upd FROM upd;

  -- Insert new activation records
  WITH ins AS (
    INSERT INTO activations
      (outlet_id, activation_date, recce_date, kickoff_time, kdm_id, tmr_id, team_lead_id,
       stock_qty, stock_unit, price_can, price_bottle, comments,
       first_batch_id, last_batch_id, row_hash, source_modified)
    SELECT t.outlet_id, t.activation_date, t.recce_date, t.kickoff_time,
           t.kdm_id, t.tmr_id, t.team_lead_id,
           t.stock_qty, t.stock_unit, t.price_can, t.price_bottle, t.comments,
           p_batch_id, p_batch_id, t.row_hash, v_mod
    FROM tmp_src t
    WHERE NOT EXISTS (
      SELECT 1 FROM activations a
      WHERE a.outlet_id = t.outlet_id
        AND a.activation_date = t.activation_date
    )
    RETURNING id
  )
  SELECT count(*) INTO v_ins FROM ins;

  -- 5. Bookkeeping -----------------------------------------------------
  DELETE FROM staging_activations
   WHERE batch_id = p_batch_id
     AND outlet_id IS NOT NULL
     AND activation_date IS NOT NULL;

  UPDATE import_batches b
     SET rows_total     = coalesce(b.rows_total, v_total),
         rows_inserted  = b.rows_inserted  + v_ins,
         rows_updated   = b.rows_updated   + v_upd,
         rows_unchanged = b.rows_unchanged + (v_src - v_ins - v_upd)
   WHERE b.id = p_batch_id;

  RETURN QUERY SELECT v_total, v_ins, v_upd, v_src - v_ins - v_upd, v_review;
END $$;

-- ---------------------------------------------------------------------
-- VIEWS
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_outlets_all AS
SELECT o.id AS outlet_id, o.ke_number, o.name, o.physical_loc, o.channel, o.division,
       agg.last_activated,
       agg.next_planned,
       coalesce(agg.activation_count, 0)              AS activation_count,
       today_ke() - agg.last_activated                AS days_since_last_activation,
       latest.tmr_name, latest.tmr_phone, latest.kdm_name, latest.team_lead_name,
       latest.comments                                AS latest_comments
FROM outlets o
LEFT JOIN LATERAL (
    SELECT max(a.activation_date) FILTER (WHERE a.activation_date <= today_ke()) AS last_activated,
           min(a.activation_date) FILTER (WHERE a.activation_date >  today_ke()) AS next_planned,
           count(*)              FILTER (WHERE a.activation_date <= today_ke()) AS activation_count
    FROM activations a
    WHERE a.outlet_id = o.id
) agg ON true
LEFT JOIN LATERAL (
    SELECT t.name AS tmr_name, t.phone AS tmr_phone, k.name AS kdm_name,
           l.name AS team_lead_name, a.comments
    FROM activations a
    LEFT JOIN staff t ON t.id = a.tmr_id
    LEFT JOIN staff k ON k.id = a.kdm_id
    LEFT JOIN staff l ON l.id = a.team_lead_id
    WHERE a.outlet_id = o.id
    ORDER BY a.activation_date DESC
    LIMIT 1
) latest ON true;

CREATE OR REPLACE VIEW v_outlets_recently_activated AS
SELECT *
FROM v_outlets_all
WHERE last_activated > today_ke() - 14
ORDER BY last_activated DESC, name;

CREATE OR REPLACE VIEW v_outlets_inactive_2w AS
SELECT *
FROM v_outlets_all
WHERE last_activated IS NULL OR last_activated <= today_ke() - 14
ORDER BY last_activated ASC NULLS FIRST, name;

CREATE OR REPLACE VIEW v_tmr_locations AS
SELECT t.id AS tmr_id, t.name AS tmr_name, t.phone AS tmr_phone,
       o.division, o.id AS outlet_id, o.name AS outlet_name, o.physical_loc, o.channel,
       count(*)             AS activations,
       min(a.activation_date) AS first_activation,
       max(a.activation_date) AS last_activation
FROM activations a
JOIN staff   t ON t.id = a.tmr_id AND t.role = 'TMR'
JOIN outlets o ON o.id = a.outlet_id
GROUP BY t.id, o.id
ORDER BY t.name, o.division, o.name;

COMMIT;