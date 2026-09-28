from datetime import datetime
import glob
import os
import pandas as pd
from sqlalchemy import text

FOLDER_PATH = r"C:\Users\Admin\OneDrive\Documentos\Exact\recce_reports"


def parse_staff(raw_str):
  """
  Parse staff name and phone number from a combined raw string.
  """

  if not raw_str or str(raw_str).lower() == "nan":
    return None, None
  parts = str(raw_str).split("-")
  name = parts[0].strip()
  phone = parts[1].strip() if len(parts) > 1 else None
  return name, phone


def parse_date(val):
  """
  Convert raw date values to standard python date objects.
  """
  if pd.isna(val):
    return None
  if isinstance(val, datetime):
    return val.date()
  try:
    return pd.to_datetime(val, dayfirst=True).date()
  except:
    return None


def run_ingestion(engine):
  """
  Scan the recce reports directory, parse Excel files, and execute transactional upserts.
  """
  
  print("\n--- Scanning and Syncing Excel Files ---")
  all_files = glob.glob(os.path.join(FOLDER_PATH, "*.xlsx"))

  if not all_files:
    print("No Excel files found in the specified directory.")
    return False

  try:
    with engine.begin() as conn:
      for filename in all_files:
        basename = os.path.basename(filename)
        print(f"Processing: {basename}...")
        df = pd.read_excel(filename)

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

          if (
              not outlet_name
              or pd.isna(outlet_name)
              or str(outlet_name).lower() == "nan"
          ):
            continue

          outlet_name_str = str(outlet_name).strip()

          channel = row.get("channel")
          if pd.isna(channel) or str(channel).lower() == "nan":
            continue

          outlet_name = outlet_name_str

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

          outlet_id = conn.execute(
              text("SELECT outlet_id FROM outlets WHERE outlet_name = :name"),
              {"name": outlet_name},
          ).scalar()

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

          tl_raw = str(row.get("team_lead_name_&_tel", ""))
          tl_name, tl_phone = parse_staff(tl_raw)

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

    print("\nSync and database update completed successfully.")
    return True
  except Exception as e:
    print(f"\nError encountered during sync: {e}")
    print("Transaction rolled back. No partial changes were saved.")
    return False
