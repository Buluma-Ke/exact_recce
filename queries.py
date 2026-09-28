import pandas as pd
from sqlalchemy import text


def print_all_outlets_summary(engine):
  """
  Query 1: Retrieve and print all outlets with their latest associated contacts and team lead.
  """

  query = """
        WITH latest_visit AS (
            SELECT outlet_id, team_lead_name, team_lead_phone,
                   ROW_NUMBER() OVER (PARTITION BY outlet_id ORDER BY date_of_recce DESC NULLS LAST) as rn
            FROM recce_visits
        ),
        latest_kdm AS (
            SELECT outlet_id, kdm_name, kdm_phone,
                   ROW_NUMBER() OVER (PARTITION BY outlet_id ORDER BY kdm_id DESC) as rn
            FROM kdm_contacts
        ),
        latest_tmr AS (
            SELECT outlet_id, tmr_name, tmr_phone,
                   ROW_NUMBER() OVER (PARTITION BY outlet_id ORDER BY tmr_id DESC) as rn
            FROM tmr_assignments
        )
        SELECT
            o.outlet_id,
            o.outlet_name,
            o.physical_location,
            o.ke_number,
            k.kdm_name,
            k.kdm_phone,
            t.tmr_name,
            t.tmr_phone,
            v.team_lead_name AS tl_name,
            v.team_lead_phone AS tl_phone
        FROM outlets o
        LEFT JOIN latest_visit v ON o.outlet_id = v.outlet_id AND v.rn = 1
        LEFT JOIN latest_kdm k ON o.outlet_id = k.outlet_id AND k.rn = 1
        LEFT JOIN latest_tmr t ON o.outlet_id = t.outlet_id AND t.rn = 1
        ORDER BY o.outlet_id
    """
  with engine.connect() as conn:
    df = pd.read_sql(text(query), conn)

  if df.empty:
    print("\nNo outlet records found.")
  else:
    print(f"\n--- All Outlets Summary ({len(df)} records) ---")
    print(df.to_string(index=False))


def print_activated_last_two_weeks(engine):
  """
  Query 2: Retrieve and print outlets activated within the last 14 days.
  """

  query = """
        WITH outlet_latest_activation AS (
            SELECT outlet_id, date_of_activation, team_lead_name, team_lead_phone,
                   ROW_NUMBER() OVER (PARTITION BY outlet_id ORDER BY date_of_recce DESC NULLS LAST) as rn
            FROM recce_visits
            WHERE date_of_activation IS NOT NULL
        ),
        latest_kdm AS (
            SELECT outlet_id, kdm_name, kdm_phone,
                   ROW_NUMBER() OVER (PARTITION BY outlet_id ORDER BY kdm_id DESC) as rn
            FROM kdm_contacts
        ),
        latest_tmr AS (
            SELECT outlet_id, tmr_name, tmr_phone,
                   ROW_NUMBER() OVER (PARTITION BY outlet_id ORDER BY tmr_id DESC) as rn
            FROM tmr_assignments
        )
        SELECT
            o.outlet_id,
            o.outlet_name,
            o.physical_location,
            o.ke_number,
            k.kdm_name,
            k.kdm_phone,
            t.tmr_name,
            t.tmr_phone,
            v.team_lead_name AS tl_name,
            v.team_lead_phone AS tl_phone
        FROM outlets o
        JOIN outlet_latest_activation v ON o.outlet_id = v.outlet_id AND v.rn = 1
        LEFT JOIN latest_kdm k ON o.outlet_id = k.outlet_id AND k.rn = 1
        LEFT JOIN latest_tmr t ON o.outlet_id = t.outlet_id AND t.rn = 1
        WHERE v.date_of_activation >= CURRENT_DATE - INTERVAL '14 days'
        ORDER BY v.date_of_activation DESC
    """
  with engine.connect() as conn:
    df = pd.read_sql(text(query), conn)

  if df.empty:
    print("\nNo outlets activated in the last 2 weeks.")
  else:
    print(
        f"\n--- Outlets Activated in the Last 2 Weeks ({len(df)} records) ---"
    )
    print(df.to_string(index=False))


def print_inactive_two_weeks(engine):
  """
  Query 3: Retrieve and print outlets unactivated for 14 days or longer.
  """

  query = """
        WITH outlet_latest_activation AS (
            SELECT outlet_id, date_of_activation, team_lead_name, team_lead_phone,
                   ROW_NUMBER() OVER (PARTITION BY outlet_id ORDER BY date_of_recce DESC NULLS LAST) as rn
            FROM recce_visits
        ),
        latest_kdm AS (
            SELECT outlet_id, kdm_name, kdm_phone,
                   ROW_NUMBER() OVER (PARTITION BY outlet_id ORDER BY kdm_id DESC) as rn
            FROM kdm_contacts
        ),
        latest_tmr AS (
            SELECT outlet_id, tmr_name, tmr_phone,
                   ROW_NUMBER() OVER (PARTITION BY outlet_id ORDER BY tmr_id DESC) as rn
            FROM tmr_assignments
        )
        SELECT
            o.outlet_id,
            o.outlet_name,
            o.physical_location,
            o.ke_number,
            k.kdm_name,
            k.kdm_phone,
            t.tmr_name,
            t.tmr_phone,
            v.team_lead_name AS tl_name,
            v.team_lead_phone AS tl_phone
        FROM outlets o
        LEFT JOIN outlet_latest_activation v ON o.outlet_id = v.outlet_id AND v.rn = 1
        LEFT JOIN latest_kdm k ON o.outlet_id = k.outlet_id AND k.rn = 1
        LEFT JOIN latest_tmr t ON o.outlet_id = t.outlet_id AND t.rn = 1
        WHERE v.date_of_activation IS NULL OR v.date_of_activation < CURRENT_DATE - INTERVAL '14 days'
        ORDER BY o.outlet_id
    """
  with engine.connect() as conn:
    df = pd.read_sql(text(query), conn)

  if df.empty:
    print("\nNo matching outlets found.")
  else:
    print(
        f"\n--- Outlets Inactive for >= 2 Weeks / No Activation ({len(df)}"
        " records) ---"
    )
    print(df.to_string(index=False))


def print_tmr_locations(engine):
  """
  Query 4: Retrieve and print TMR names, contact numbers, and associated operating locations.
  """
  
  query = """
        SELECT tmr_name, tmr_phone, STRING_AGG(DISTINCT physical_location, ', ') AS associated_locations
        FROM tmr_assignments
        WHERE tmr_name IS NOT NULL
        GROUP BY tmr_name, tmr_phone
        ORDER BY tmr_name
    """
  with engine.connect() as conn:
    df = pd.read_sql(text(query), conn)

  if df.empty:
    print("\nNo TMR records found.")
  else:
    print(f"\n--- TMR Associated Locations ({len(df)} records) ---")
    print(df.to_string(index=False))
