"""
Compares every outlet name in the Excel files with the outlets table, so you
don't have to remember which ones are missing.
Run from the project root:  python reconcile_outlets.py
"""
import re

import pandas as pd
from sqlalchemy import text

from connections import get_db_engine
from etl.extract import extract_excel_files


def key(name):  # same as normalize_key() in Postgres
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def clean_ke(val):
    if val is None or pd.isna(val):
        return None
    s = re.sub(r"\s+", "", str(val)).upper()
    if re.fullmatch(r"KE[0-9O]+", s):
        return "KE" + s[2:].replace("O", "0")  # fixes 'KEO152439'
    return None


engine = get_db_engine()
with engine.connect() as conn:
    outlets = pd.read_sql(text("SELECT id, name, name_key, ke_number FROM outlets"), conn)
    aliases = pd.read_sql(text("SELECT alias_key, outlet_id FROM outlet_aliases"), conn)

by_key = set(outlets.name_key) | set(aliases.alias_key)
by_ke = {r.ke_number: r.name for r in outlets.itertuples() if r.ke_number}

seen = {}  # name_key -> (display name, ke, files)
for fname, df in extract_excel_files().items():
    df.columns = (df.columns.str.strip().str.lower().str.replace(" ", "_")
                  .str.replace("-", "_").str.replace(r"[()]", "", regex=True))
    col = "outlet_name___location" if "outlet_name___location" in df.columns else "outlet_name"
    if col not in df.columns:
        continue
    for _, row in df.iterrows():
        name = row.get(col)
        if name is None or pd.isna(name) or not str(name).strip():
            continue
        k = key(name)
        entry = seen.setdefault(k, [str(name).strip(), clean_ke(row.get("ke_number")), set()])
        entry[2].add(fname)

merged, missing = [], []
for k, (name, ke, files) in sorted(seen.items()):
    if k in by_key:
        continue
    if ke and ke in by_ke:
        merged.append((name, ke, by_ke[ke]))
    else:
        missing.append((name, ke, sorted(files)[:2]))

print(f"\nDistinct outlet names in Excel: {len(seen)}  |  outlets in DB: {len(outlets)}")
print(f"\n=== Merged into another outlet by KE number ({len(merged)}) - check each is the SAME place ===")
for name, ke, into in merged:
    print(f"  {name!r}  ->  {into!r}  ({ke})")
print(f"\n=== MISSING from the DB entirely ({len(missing)}) ===")
for name, ke, files in missing:
    print(f"  {name!r}  ke={ke}  e.g. {files[0]}")
