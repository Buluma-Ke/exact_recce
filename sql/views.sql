
-- 1. Base View
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
    k.name AS kdm_name,
    k.phone AS kdm_phone,
    t.name AS tmr_name,
    t.phone AS tmr_phone,
    tl.name AS team_lead_name,
    tl.name AS tl_name
FROM outlets o
LEFT JOIN activations a ON a.outlet_id = o.id AND a.activation_date = (SELECT MAX(activation_date) FROM activations WHERE outlet_id = o.id)
LEFT JOIN staff k ON a.kdm_id = k.id
LEFT JOIN staff t ON a.tmr_id = t.id
LEFT JOIN staff tl ON a.team_lead_id = tl.id;


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
        COALESCE(GREATEST(0, CURRENT_DATE - last_activated), 999) AS days_since_last_activation
    FROM v_outlets_all
) sub
WHERE (last_activated IS NULL OR last_activated < CURRENT_DATE - INTERVAL '14 days')
  AND (physical_loc ILIKE '%Nairobi%' OR division ILIKE '%Nairobi%')
ORDER BY channel ASC, days_since_last_activation DESC;
