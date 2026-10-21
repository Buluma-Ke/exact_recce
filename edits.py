"""Data layer for the edit screens: outlet details and the import review queue."""
import re
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

CHANNELS = ["Ontrade", "Offtrade", "THT"]
GAP_FILTERS = ("all", "ke", "location", "channel", "division")

# THT outlets have no KE number by design, so a blank KE is only a gap for the others.
GAP_SQL = """
SELECT * FROM (
  SELECT id, name, ke_number, physical_loc, channel, division,
         (ke_number IS NULL AND upper(btrim(coalesce(channel, ''))) <> 'THT') AS miss_ke,
         (nullif(btrim(coalesce(physical_loc, '')), '') IS NULL) AS miss_location,
         (nullif(btrim(coalesce(channel, '')), '')      IS NULL) AS miss_channel,
         (nullif(btrim(coalesce(division, '')), '')     IS NULL) AS miss_division
  FROM outlets
) g
WHERE miss_ke OR miss_location OR miss_channel OR miss_division
ORDER BY lower(name)
"""


def _rows(engine, sql, **params):
    try:
        with engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(text(sql), params)]
    except Exception as e:
        print(f"query failed: {e}")
        return []


def get_gaps(engine, missing="all"):
    """Returns (rows matching the filter, counts for every filter)."""
    rows = _rows(engine, GAP_SQL)
    field = {"ke": "miss_ke", "location": "miss_location",
             "channel": "miss_channel", "division": "miss_division"}
    counts = {"all": len(rows)}
    for key, col in field.items():
        counts[key] = sum(1 for r in rows if r[col])
    if missing in field:
        rows = [r for r in rows if r[field[missing]]]
    return rows, counts


def count_attention(engine):
    gaps = len(_rows(engine, GAP_SQL))
    review = _rows(engine, "SELECT count(*) AS n FROM import_review")
    return {"gaps": gaps, "review": review[0]["n"] if review else 0}


# ---------------------------------------------------------------- outlets
def get_outlet(engine, outlet_id):
    rows = _rows(engine, "SELECT id, name, ke_number, physical_loc, channel, division "
                         "FROM outlets WHERE id = :i", i=outlet_id)
    return rows[0] if rows else None


def get_choices(engine, outlet):
    channels = list(CHANNELS)
    current = (outlet.get("channel") or "").strip()
    if current and current not in channels:
        channels.append(current)  # keep a legacy value selectable
    divisions = [r["division"] for r in _rows(
        engine, "SELECT division FROM outlets WHERE nullif(btrim(division), '') IS NOT NULL "
                "GROUP BY division ORDER BY count(*) DESC, division")]
    return {"channels": channels, "divisions": divisions}


def _clean(value):
    value = " ".join((value or "").split())
    return value or None


def update_outlet(engine, outlet_id, form):
    """Returns (ok, message, values). `values` is what the form should show again on error."""
    name = _clean(form.get("name"))
    ke = re.sub(r"\s+", "", form.get("ke_number") or "").upper() or None
    loc = _clean(form.get("physical_loc"))
    channel = _clean(form.get("channel"))
    division = _clean(form.get("division"))
    values = {"name": name or "", "ke_number": ke or "", "physical_loc": loc or "",
              "channel": channel or "", "division": division or ""}

    if not name:
        return False, "The outlet name cannot be empty.", values
    if ke:
        if not re.fullmatch(r"KE[0-9O]+", ke):
            return False, "KE number should look like KE0123456 (leave it blank if there is none).", values
        ke = "KE" + ke[2:].replace("O", "0")  # the letter O is a common typo for zero
        values["ke_number"] = ke
    if channel:
        channel = {c.lower(): c for c in CHANNELS}.get(channel.replace(" ", "").lower(), channel)
        values["channel"] = channel

    try:
        with engine.begin() as conn:
            old = conn.execute(text("SELECT name FROM outlets WHERE id = :i FOR UPDATE"),
                               {"i": outlet_id}).scalar()
            if old is None:
                return False, "That outlet no longer exists.", values
            if division:  # reuse the spelling already in the data, so 'rift' joins 'Rift'
                existing = conn.execute(text(
                    "SELECT division FROM outlets WHERE lower(btrim(division)) = lower(:d) "
                    "GROUP BY division ORDER BY count(*) DESC LIMIT 1"), {"d": division}).scalar()
                division = existing or division
                values["division"] = division
            conn.execute(text(
                "UPDATE outlets SET name = :name, ke_number = :ke, physical_loc = :loc, "
                "channel = :channel, division = :division WHERE id = :i"),
                {"name": name, "ke": ke, "loc": loc, "channel": channel,
                 "division": division, "i": outlet_id})
            # Keep the old spelling as an alias, or the next import would create a duplicate outlet.
            conn.execute(text("SELECT add_outlet_alias(:old, :i) "
                              "WHERE normalize_key(:old) IS DISTINCT FROM normalize_key(:new)"),
                         {"old": old, "new": name, "i": outlet_id})
    except IntegrityError as e:
        constraint = getattr(getattr(e.orig, "diag", None), "constraint_name", "") or ""
        if "ke_number" in constraint and ke:
            owner = _rows(engine, "SELECT name FROM outlets WHERE ke_number = :k", k=ke)
            who = f" ({owner[0]['name']})" if owner else ""
            return False, f"KE number {ke} already belongs to another outlet{who}.", values
        if "name_key" in constraint:
            return False, "Another outlet already has this name.", values
        return False, "Could not save: that value conflicts with an existing outlet.", values
    return True, f"Saved {name}.", values


# ----------------------------------------------------------- review queue
def get_review(engine):
    return _rows(engine, """
        SELECT r.id AS review_id, r.reason, r.row_num, b.file_name,
               r.payload->>'outlet_name' AS outlet_name,
               r.payload->>'recce_date'  AS recce_date,
               r.payload->>'tmr_name'    AS tmr_name,
               r.payload->>'comments'    AS comments
        FROM import_review r JOIN import_batches b ON b.id = r.batch_id
        ORDER BY b.imported_at DESC, r.row_num
    """)


def fix_review(engine, review_id, date_text):
    """Give a held-back row its activation date, then let ingest_batch() import it."""
    try:
        d = date.fromisoformat((date_text or "").strip())
    except ValueError:
        return False, "Please pick a valid date."
    if not (date(2020, 1, 1) <= d <= date.today() + timedelta(days=365)):
        return False, "That date looks wrong. Please check the year."

    with engine.begin() as conn:
        row = conn.execute(text("SELECT batch_id, (payload->>'id')::int AS sid "
                                "FROM import_review WHERE id = :i"), {"i": review_id}).fetchone()
        if not row:
            return False, "That row is no longer in the review list (it may already be fixed)."
        updated = conn.execute(text(
            "UPDATE staging_activations SET activation_date = :d WHERE id = :sid AND batch_id = :b"),
            {"d": d, "sid": row.sid, "b": row.batch_id}).rowcount
        if not updated:
            return False, "The staged row is gone. Upload the file again to bring it back."
        res = conn.execute(text("SELECT o_inserted, o_updated FROM ingest_batch(:b, true)"),
                           {"b": row.batch_id}).fetchone()
    if res and (res.o_inserted or res.o_updated):
        return True, f"Saved. Activation on {d:%d %b %Y} added."
    return True, f"Saved. An identical activation on {d:%d %b %Y} already existed."


def dismiss_review(engine, review_id):
    with engine.begin() as conn:
        row = conn.execute(text("SELECT batch_id, (payload->>'id')::int AS sid "
                                "FROM import_review WHERE id = :i"), {"i": review_id}).fetchone()
        if not row:
            return False, "That row is no longer in the review list."
        conn.execute(text("DELETE FROM staging_activations WHERE id = :sid AND batch_id = :b"),
                     {"sid": row.sid, "b": row.batch_id})
        conn.execute(text("DELETE FROM import_review WHERE id = :i"), {"i": review_id})
    return True, "Row dismissed. It will come back if you import the same file again."
