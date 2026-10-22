
-- 1. Base View
--    Contacts come from the latest activation. An outlet that has no activation yet (for example a
--    recce-only row waiting in the review queue) falls back to the contacts on that held-back row.
DROP VIEW IF EXISTS v_outlets_all CASCADE;
CREATE VIEW v_outlets_all AS
SELECT
    o.id AS outlet_id,
    o.ke_number,
    o.name,
    o.physical_loc,
    o.channel,
    o.division,
    (SELECT MAX(activation_date) FROM activations WHERE outlet_id = o.id) AS last_activated,
    (SELECT comments FROM activations WHERE outlet_id = o.id ORDER BY activation_date DESC LIMIT 1) AS latest_comments,
    COALESCE(k.name,  rv.payload->>'kdm_name')  AS kdm_name,
    COALESCE(k.phone, rv.payload->>'kdm_phone') AS kdm_phone,
    COALESCE(t.name,  rv.payload->>'tmr_name')  AS tmr_name,
    COALESCE(t.phone, rv.payload->>'tmr_phone') AS tmr_phone,
    COALESCE(tl.name, rv.payload->>'tl_name')   AS team_lead_name,
    COALESCE(tl.name, rv.payload->>'tl_name')   AS tl_name
FROM outlets o
LEFT JOIN activations a ON a.outlet_id = o.id AND a.activation_date = (SELECT MAX(activation_date) FROM activations WHERE outlet_id = o.id)
LEFT JOIN staff k ON a.kdm_id = k.id
LEFT JOIN staff t ON a.tmr_id = t.id
LEFT JOIN staff tl ON a.team_lead_id = tl.id
LEFT JOIN LATERAL (
    SELECT r.payload
    FROM import_review r
    WHERE (r.payload->>'outlet_id')::int = o.id
    ORDER BY r.id DESC
    LIMIT 1
) rv ON a.id IS NULL;


-- 2. Option 2: Activated in Last 2 Weeks (Nairobi only, no negative days)
DROP VIEW IF EXISTS v_outlets_recently_activated CASCADE;
CREATE VIEW v_outlets_recently_activated AS
SELECT
    name AS outlet_name,
    physical_loc AS location,
    ke_number,
    channel,
    days_since_last_activation,
    kdm_name,
    kdm_phone,
    tmr_name,
    tmr_phone,
    tl_name,
    division,
    last_activated
FROM (
    SELECT
        *,
        GREATEST(0, CURRENT_DATE - last_activated) AS days_since_last_activation
    FROM v_outlets_all
) sub
WHERE last_activated BETWEEN CURRENT_DATE - INTERVAL '14 days' AND CURRENT_DATE
  AND (physical_loc ILIKE '%Nairobi%' OR division ILIKE '%Nairobi%')
ORDER BY channel ASC, days_since_last_activation DESC;


-- 3. Option 3: Inactive for >= 2 Weeks (Nairobi only, no negative days)
--    Never-activated outlets show 999 days. GREATEST() ignores NULL, so the old
--    COALESCE(GREATEST(0, ...), 999) always returned 0 for them.
DROP VIEW IF EXISTS v_outlets_inactive_2w CASCADE;
CREATE VIEW v_outlets_inactive_2w AS
SELECT
    name AS outlet_name,
    physical_loc AS location,
    ke_number,
    channel,
    days_since_last_activation,
    kdm_name,
    kdm_phone,
    tmr_name,
    tmr_phone,
    tl_name,
    division,
    last_activated
FROM (
    SELECT
        *,
        CASE WHEN last_activated IS NULL THEN 999
             ELSE GREATEST(0, CURRENT_DATE - last_activated)
        END AS days_since_last_activation
    FROM v_outlets_all
) sub
WHERE (last_activated IS NULL OR last_activated < CURRENT_DATE - INTERVAL '14 days')
  AND (physical_loc ILIKE '%Nairobi%' OR division ILIKE '%Nairobi%')
ORDER BY channel ASC, days_since_last_activation DESC;
