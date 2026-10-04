# Dry run: reads and cleans the Excel files but never touches the database.
from etl.extract import extract_excel_files
from etl.transform import transform_data

cleaned = transform_data(extract_excel_files())

print("\n--- Activation date range per file ---")
for name, rows in cleaned.items():
    acts = [r["act_date"] for r in rows if r["act_date"]]
    missing = len(rows) - len(acts)
    if acts:
        print(f"{name}: {len(rows)} rows | {min(acts)} to {max(acts)} | missing: {missing}")
    else:
        print(f"{name}: {len(rows)} rows | no activation dates | missing: {missing}")
