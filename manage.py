from datetime import datetime
import getpass
import glob
import os
import pandas as pd
from sqlalchemy import create_engine, text

# Secure password prompt
password = getpass.getpass("Enter your PostgreSQL password: ")

# Fixed f-string connection string with psycopg2 driver explicitly declared
DB_URI = f"postgresql+psycopg2://Admin:{password}@localhost:5432/exact_experience"
engine = create_engine(DB_URI)

FOLDER_PATH = r"C:\Users\Admin\OneDrive\Documentos\Exact\recce_reports"


def clean_and_sync_files():
  print("\n--- Scanning and Syncing Excel Files ---")
  all_files = glob.glob(os.path.join(FOLDER_PATH, "*.xlsx"))

  if not all_files:
    print("No Excel files found in the specified directory.")
    return

  # engine.begin() automatically rolls back EVERYTHING if an error occurs mid-way
  try:
    with engine.begin() as conn:
      for filename in all_files:
        basename = os.path.basename(filename)
        print(f"Processing: {basename}...")
        df = pd.read_excel(filename)

        # Standardize column names to match snake_case
        df.columns = (
            df.columns.str.strip()
            .str.lower()
            .str.replace(" ", "_")
            .str.replace("-", "_")
            .str.replace(r"[()]", "", regex=True)
        )
        df.replace(["N/A", "n/a", ""], None, inplace=True)

        for _, row in df.iterrows():
          outlet_name = row.get("outlet_name___location") or row.get(
              "outlet_name"
          )

          # Universal skip check: ignore missing names, NaNs, or section header banner rows
          if (
              not outlet_name
              or pd.isna(outlet_name)
              or str(outlet_name).lower() == "nan"
          ):
            continue

          outlet_name_str = str(outlet_name).strip()

          # Universal skip for section title banners (e.g. "None Active Account", headers, etc.)
          # If key tracking columns like 'channel' are empty/NaN, it's a section divider row, not an outlet.
          channel = row.get("channel")
          if pd.isna(channel) or str(channel).lower() == "nan":
            continue

          outlet_name = outlet_name_str

          # 1. Upsert Outlet (Master Info)
          conn.execute(
              text("""
                        INSERT INTO outlets (ke_number, outlet_name, physical_location, channel, division)
                        VALUES (:ke, :name, :loc, :chan, :div)
                        ON CONFLICT (outlet_name) DO UPDATE SET
                            ke_number = EXCLUDED.ke_number,
                            physical_location = EXCLUDED.physical_location,
                            channel = EXCLUDED.channel,
                            division = EXCLUDED.division
                    """),
              {
                  "ke": row.get("ke_number"),
                  "name": outlet_name,
                  "loc": row.get("physical_location"),
                  "chan": row.get("channel"),
                  "div": row.get("division"),
              },
          )

          # Retrieve outlet_id for foreign keys
          outlet_id = conn.execute(
              text("SELECT outlet_id FROM outlets WHERE outlet_name = :name"),
              {"name": outlet_name},
          ).scalar()

          # 2. Handle TMR Assignment Table
          tmr_raw = str(row.get("tmr_name_&_tel", ""))
          tmr_name, tmr_phone = parse_staff(tmr_raw)
          if tmr_name:
            conn.execute(
                text("""
                            INSERT INTO tmr_assignments (outlet_id, tmr_name, tmr_phone, physical_location, division)
                            VALUES (:oid, :name, :phone, :loc, :div)
                            ON CONFLICT DO NOTHING
                        """),
                {
                    "oid": outlet_id,
                    "name": tmr_name,
                    "phone": tmr_phone,
                    "loc": row.get("physical_location"),
                    "div": row.get("division"),
                },
            )

          # 3. Handle KDM Contacts Table
          kdm_raw = str(row.get("kdm_name_&_tel", ""))
          kdm_name, kdm_phone = parse_staff(kdm_raw)
          if kdm_name:
            existing_kdm = conn.execute(
                text(
                    "SELECT kdm_id FROM kdm_contacts WHERE outlet_id = :oid AND"
                    " kdm_name = :name"
                ),
                {"oid": outlet_id, "name": kdm_name},
            ).scalar()

            if not existing_kdm:
              conn.execute(
                  text("""
                                INSERT INTO kdm_contacts (outlet_id, kdm_name, kdm_phone, location)
                                VALUES (:oid, :name, :phone, :loc)
                            """),
                  {
                      "oid": outlet_id,
                      "name": kdm_name,
                      "phone": kdm_phone,
                      "loc": row.get("physical_location"),
                  },
              )

          # 4. Handle Staff (Team Lead parsed on the fly for visit logs)
          tl_raw = str(row.get("team_lead_name_&_tel", ""))
          tl_name, tl_phone = parse_staff(tl_raw)

          # 5. Upsert Recce Visit Log
          conn.execute(
              text("""
                        INSERT INTO recce_visits (
                            outlet_id, team_lead_name, team_lead_phone, date_of_recce,
                            date_of_activation, kick_off_time, raspberry_stock,
                            raspberry_price, comments, source_file
                        ) VALUES (
                            :oid, :tl_name, :tl_phone, :recce_date, :act_date,
                            :kickoff, :stock, :price, :comments, :file
                        )
                        ON CONFLICT (outlet_id, date_of_recce) DO UPDATE SET
                            team_lead_name = EXCLUDED.team_lead_name,
                            team_lead_phone = EXCLUDED.team_lead_phone,
                            date_of_activation = EXCLUDED.date_of_activation,
                            kick_off_time = EXCLUDED.kick_off_time,
                            raspberry_stock = EXCLUDED.raspberry_stock,
                            raspberry_price = EXCLUDED.raspberry_price,
                            comments = EXCLUDED.comments,
                            source_file = EXCLUDED.source_file
                    """),
              {
                  "oid": outlet_id,
                  "tl_name": tl_name,
                  "tl_phone": tl_phone,
                  "recce_date": parse_date(row.get("date_of_recce")),
                  "act_date": parse_date(row.get("date_of_activation")),
                  "kickoff": str(row.get("kick___off_time", "")),
                  "stock": str(row.get("raspberry_stock", "")),
                  "price": str(row.get("raspberry_price_bottle", "")),
                  "comments": str(row.get("comments/insights", "")),
                  "file": basename,
              },
          )

    print(
        "\n Sync and database update completed successfully! (Changes"
        " committed)"
    )

  except Exception as e:
    print(
        f"\n❌ Error encountered during sync: {e}\n[!] Transaction rolled"
        " back. No partial changes were saved to the database."
    )


def parse_staff(raw_str):
  if not raw_str or raw_str.lower() == "nan":
    return None, None
  parts = raw_str.split("-")
  name = parts[0].strip()
  phone = parts[1].strip() if len(parts) > 1 else None
  return name, phone


def parse_date(val):
  if pd.isna(val):
    return None
  if isinstance(val, datetime):
    return val.date()
  try:
    # dayfirst=True accurately handles DD/MM/YYYY date layouts
    return pd.to_datetime(val, dayfirst=True).date()
  except:
    return None


def search_outlet_history():
  query_name = input(
      "\nEnter outlet name (or part of it) to search history: "
  ).strip()
  with engine.connect() as conn:
    df = pd.read_sql(
        text("""
            SELECT o.outlet_name, o.physical_location, v.date_of_recce,
                   v.date_of_activation, v.team_lead_name, v.raspberry_stock,
                   v.comments, v.source_file
            FROM outlets o
            JOIN recce_visits v ON o.outlet_id = v.outlet_id
            WHERE o.outlet_name ILIKE :search
            ORDER BY v.date_of_recce DESC
        """),
        conn,
        params={"search": f"%{query_name}%"},
    )

  if df.empty:
    print("\nNo records found for that outlet.")
  else:
    print(f"\nFound {len(df)} visit records:")
    print(df.to_string(index=False))


def lookup_kdm():
  query_name = input(
      "\nEnter outlet name or KDM name to search contacts: "
  ).strip()
  with engine.connect() as conn:
    df = pd.read_sql(
        text("""
            SELECT o.outlet_name, k.kdm_name, k.kdm_phone, k.location
            FROM kdm_contacts k
            JOIN outlets o ON k.outlet_id = o.outlet_id
            WHERE o.outlet_name ILIKE :search OR k.kdm_name ILIKE :search
        """),
        conn,
        params={"search": f"%{query_name}%"},
    )

  if df.empty:
    print("\nNo KDM contacts found.")
  else:
    print(f"\nFound {len(df)} contacts:")
    print(df.to_string(index=False))


def main_menu():
  while True:
    print("\n==============================")
    print("   BEVERAGE RECCE DATABASE CLI")
    print("==============================")
    print("1. Sync / Ingest Excel Reports Folder")
    print("2. Search Outlet Visit History")
    print("3. Lookup KDM & Contact Info")
    print("4. Exit")

    choice = input("\nEnter your choice (1-4): ").strip()

    if choice == "1":
      clean_and_sync_files()
    elif choice == "2":
      search_outlet_history()
    elif choice == "3":
      lookup_kdm()
    elif choice == "4":
      print("\nExiting. Goodbye!")
      break
    else:
      print("\nInvalid choice. Please select between 1 and 4.")


if __name__ == "__main__":
  main_menu()
