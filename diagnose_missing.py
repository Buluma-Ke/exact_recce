"""
Dry run (no database): shows which Excel rows never reach the outlets table and why.
Run from the project root:  python diagnose_missing.py [search_text]
"""
import re
import sys
from collections import defaultdict

import pandas as pd

from etl.extract import extract_excel_files

SEARCH = (sys.argv[1] if len(sys.argv) > 1 else "chandarana").lower()
KE_OK = re.compile(r"^KE\d+$")


def norm_cols(df):
    df.columns = (
        df.columns.str.strip().str.lower().str.replace(" ", "_")
        .str.replace("-", "_").str.replace(r"[()]", "", regex=True)
    )
    return df


def key(name):  # same as normalize_key() in Postgres
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


raw = extract_excel_files()
ke_to_names = defaultdict(set)      # KE value -> {outlet name keys}
odd_ke = defaultdict(list)          # KE values that are not KE + digits

print("\n=== 1. Rows transform.py silently skips ===")
for fname, df in raw.items():
    df = norm_cols(df.copy())
    if "outlet_name___location" not in df.columns and "outlet_name" not in df.columns:
        print(f"{fname}: NO outlet name column. Columns are: {list(df.columns)}")
        continue
    for i, row in df.iterrows():
        name = row.get("outlet_name___location")
        if name is None or pd.isna(name):
            name = row.get("outlet_name")
        chan = row.get("channel")
        excel_row = i + 2
        if name is None or pd.isna(name) or not str(name).strip():
            if row.drop(labels=["#"], errors="ignore").notna().any():
                print(f"{fname} row {excel_row}: skipped, empty outlet name")
            continue
        if chan is None or pd.isna(chan) or str(chan).strip().lower() in ("", "n/a", "nan"):
            print(f"{fname} row {excel_row}: skipped, no channel -> {name!r}")
        ke = row.get("ke_number")
        if ke is not None and not pd.isna(ke):
            ke_s = str(ke)
            ke_to_names[ke_s.strip().upper()].add(key(name))
            if not KE_OK.match(ke_s.strip().upper()) and ke_s.strip().upper() != "N/A":
                odd_ke[repr(ke_s)].append(f"{fname} row {excel_row}: {name}")
            elif ke_s != ke_s.strip():
                odd_ke[repr(ke_s)].append(f"{fname} row {excel_row}: {name}")

print("\n=== 2. KE numbers that are not 'KE' + digits (placeholders merge outlets) ===")
for k, where in odd_ke.items():
    print(k, f"-> {len(where)} rows, e.g. {where[0]}")

print("\n=== 3. One KE number used by several different outlet names ===")
for ke, names in ke_to_names.items():
    if len(names) > 1:
        print(ke, "->", sorted(names))

print(f"\n=== 4. Rows mentioning '{SEARCH}' ===")
for fname, df in raw.items():
    df = norm_cols(df.copy())
    col = "outlet_name___location" if "outlet_name___location" in df.columns else "outlet_name"
    if col in df.columns:
        for i, row in df.iterrows():
            if SEARCH in str(row[col]).lower():
                print(f"{fname} row {i+2}: name={row[col]!r} ke={row.get('ke_number')!r} channel={row.get('channel')!r}")
