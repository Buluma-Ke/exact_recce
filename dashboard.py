"""Numbers for the dashboard home page. Reads the base tables, not the views."""

from sqlalchemy import text

TODAY_SQL = "(now() AT TIME ZONE 'Africa/Nairobi')::date"


def _rows(engine, sql):
    """One short connection per query, so a failing query cannot poison the others."""
    try:
        with engine.connect() as conn:
            return conn.execute(text(sql)).fetchall()
    except Exception as e:
        print(f"dashboard query failed: {e}")
        return []


KNOWN_LABELS = {"ontrade": "Ontrade", "offtrade": "Offtrade", "tht": "THT"}


def _label(value):
    """Excel has 'ontrade', 'Ontrade', 'Off trade', 'THT ', so ignore case and spaces."""
    v = " ".join((value or "").split())
    if not v:
        return "Unknown"
    return KNOWN_LABELS.get(v.replace(" ", "").lower(), v.title())


def _breakdown(outlets, field):
    groups = {}
    for o in outlets:
        g = groups.setdefault(_label(o[field]), {"total": 0, "active": 0})
        g["total"] += 1
        g["active"] += 1 if o["active14"] else 0
    items = [
        {"name": n, "total": g["total"], "active": g["active"],
         "pct": round(100 * g["active"] / g["total"])}
        for n, g in groups.items()
    ]
    return sorted(items, key=lambda i: -i["total"])


def get_dashboard_data(engine):
    # one row per outlet, with its latest past activation and next planned one
    rows = _rows(engine, f"""
        SELECT o.id, o.channel, o.division,
               max(a.activation_date) FILTER (WHERE a.activation_date <= t.today) AS last_act,
               min(a.activation_date) FILTER (WHERE a.activation_date >  t.today) AS next_act,
               t.today
        FROM outlets o
        CROSS JOIN (SELECT {TODAY_SQL} AS today) t
        LEFT JOIN activations a ON a.outlet_id = o.id
        GROUP BY o.id, o.channel, o.division, t.today
    """)
    outlets = []
    for r in rows:
        days = (r.today - r.last_act).days if r.last_act else None
        outlets.append({
            "channel": r.channel, "division": r.division, "next_act": r.next_act,
            "days": days,
            "active7": days is not None and days <= 7,
            "active14": days is not None and days <= 14,
            "never": r.last_act is None,
        })

    total = len(outlets)
    channels = _breakdown(outlets, "channel")
    regions = _breakdown(outlets, "division")
    active14 = sum(o["active14"] for o in outlets)
    planned = [o["next_act"] for o in outlets if o["next_act"]]

    acts7 = _rows(engine, f"""
        SELECT count(*) FROM activations
        WHERE activation_date BETWEEN {TODAY_SQL} - 7 AND {TODAY_SQL}
    """)

    k = {
        "total": total,
        "channels": len(channels),
        "regions": len(regions),
        "active7": sum(o["active7"] for o in outlets),
        "acts7": acts7[0][0] if acts7 else 0,
        "active14": active14,
        "active14_pct": round(100 * active14 / total) if total else 0,
        "inactive": total - active14,
        "never": sum(o["never"] for o in outlets),
        "planned": len(planned),
        "next_date": min(planned).strftime("%d %b") if planned else None,
    }

    # activations per week, last 8 weeks (Monday start), zero weeks included
    weeks = []
    for r in _rows(engine, f"""
        SELECT w::date AS week_start, count(a.id) AS n
        FROM generate_series(date_trunc('week', {TODAY_SQL}::timestamp) - interval '7 weeks',
                             date_trunc('week', {TODAY_SQL}::timestamp), interval '1 week') w
        LEFT JOIN activations a
               ON a.activation_date >= w::date
              AND a.activation_date <  w::date + 7
              AND a.activation_date <= {TODAY_SQL}
        GROUP BY w ORDER BY w
    """):
        weeks.append({"label": r.week_start.strftime("%d %b"), "count": r.n})
    peak = max((w["count"] for w in weeks), default=0) or 1
    for w in weeks:
        w["pct"] = round(100 * w["count"] / peak)

    tls = [
        {"name": r.name, "n": r.n, "outlets": r.outlets}
        for r in _rows(engine, f"""
            SELECT s.name, count(*) AS n, count(DISTINCT a.outlet_id) AS outlets
            FROM activations a JOIN staff s ON s.id = a.team_lead_id
            WHERE a.activation_date BETWEEN {TODAY_SQL} - 30 AND {TODAY_SQL}
              AND lower(s.name) <> 'none'
            GROUP BY s.id, s.name ORDER BY n DESC, s.name LIMIT 5
        """)
    ]

    syncs = [
        {"file": r.file_name, "when": r.imported_at.astimezone().strftime("%d %b %H:%M"),
         "ins": r.rows_inserted, "upd": r.rows_updated}
        for r in _rows(engine, """
            SELECT file_name, imported_at, rows_inserted, rows_updated
            FROM import_batches ORDER BY imported_at DESC LIMIT 5
        """)
    ]

    review = _rows(engine, "SELECT count(*) FROM import_review")

    return {
        "k": k, "channels": channels, "regions": regions, "weeks": weeks,
        "tls": tls, "syncs": syncs,
        "review": review[0][0] if review else 0,
        "last_sync": syncs[0]["when"] if syncs else None,
    }
