# Diagnostic: compares the outlets in the Excel files with the outlets table.
# Reads the database but changes nothing.
import re

import pandas as pd
from sqlalchemy import text

from connections import get_db_engine
from etl.extract import extract_excel_files
from etl.transform import transform_data


def norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def clean_ke(value):
    """A usable KE number in upper case, or None for blank / NaN / 'NAN'."""
    if not isinstance(value, str):
        return None
    ke = value.strip().upper()
    return ke if ke and ke not in ("NAN", "NONE") else None


def raw_outlet_counts(raw):
    """Rows per file with something in the outlet name column, before any filtering."""
    counts = {}
    for name, df in raw.items():
        cols = [c for c in df.columns if "outlet" in str(c).lower() and "name" in str(c).lower()]
        counts[name] = int(df[cols[0]].notna().sum()) if cols else 0
    return counts


def find_gaps(raw_counts, cleaned, db_names):
    dropped = {n: raw_counts.get(n, 0) - len(rows) for n, rows in cleaned.items()}
    dropped = {n: d for n, d in dropped.items() if d > 0}

    db_keys = {norm(n) for n in db_names}
    not_in_db, no_ke, by_name, by_ke = {}, {}, {}, {}
    for fname, rows in cleaned.items():
        for r in rows:
            key = norm(r["outlet_name"])
            ke = clean_ke(r["ke_number"])
            if key not in db_keys:
                not_in_db.setdefault((r["outlet_name"], ke), set()).add(fname)
            if ke is None:
                no_ke.setdefault(r["outlet_name"], set()).add(fname)
            else:
                by_name.setdefault(key, set()).add(ke)
                by_ke.setdefault(ke, set()).add(r["outlet_name"])

    same_name_many_ke = {k: v for k, v in by_name.items() if len(v) > 1}
    same_ke_many_names = {k: v for k, v in by_ke.items() if len({norm(n) for n in v}) > 1}
    return dropped, not_in_db, no_ke, same_name_many_ke, same_ke_many_names


def main():
    engine = get_db_engine()
    with engine.connect() as conn:
        db = pd.read_sql(text("SELECT id, name, ke_number FROM outlets"), conn)

    raw = extract_excel_files()
    raw_counts = raw_outlet_counts(raw)   # count before transform changes the columns
    cleaned = transform_data(raw)

    dropped, not_in_db, no_ke, same_name, same_ke = find_gaps(raw_counts, cleaned, list(db["name"]))

    print("\n--- Rows removed before reaching the database (no channel or no outlet name) ---")
    for name, n in dropped.items():
        print(f"{name}: {n} of {raw_counts[name]} rows")
    if not dropped:
        print("none")

    print("\n--- Outlet names in the files that are not in the outlets table ---")
    for (name, ke), files in sorted(not_in_db.items(), key=lambda x: str(x[0][0])):
        print(f"{name} | KE: {ke} | {len(files)} file(s)")
    if not not_in_db:
        print("none")

    print(f"\n--- Outlets in the files with no KE number ({len(no_ke)}) ---")
    for name, files in sorted(no_ke.items()):
        print(f"{name} | {len(files)} file(s)")

    print("\n--- Same outlet name with different KE numbers (may have been merged into one) ---")
    for key, kes in same_name.items():
        print(key, sorted(kes))
    if not same_name:
        print("none")

    print("\n--- Same KE number used by different outlet names ---")
    for ke, names in same_ke.items():
        print(ke, sorted(names))
    if not same_ke:
        print("none")

    print(f"\nOutlets in the database: {len(db)}")


if __name__ == "__main__":
    main()
