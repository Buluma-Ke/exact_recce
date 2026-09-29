import pandas as pd
from sqlalchemy import text


def print_all_outlets_summary(engine):
    """
    Query 1: Retrieve and print all outlets with their latest associated contacts and team lead.
    """
    query = """
        SELECT
            outlet_id,
            name AS outlet_name,
            physical_loc AS physical_location,
            ke_number,
            kdm_name,
            kdm_phone,
            tmr_name,
            tmr_phone,
            team_lead_name AS tl_name,
            latest_comments
        FROM v_outlets_all
        ORDER BY outlet_id
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
    Query 2: Retrieve and print outlets activated within the last 14 days (excluding outlet_id).
    """
    query = """
        SELECT
            name AS outlet_name,
            physical_loc AS physical_location,
            ke_number,
            channel,
            division,
            last_activated,
            kdm_name,
            kdm_phone,
            tmr_name,
            tmr_phone,
            latest_comments
        FROM v_outlets_recently_activated
        ORDER BY last_activated DESC
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if df.empty:
        print("\nNo outlets activated in the last 2 weeks.")
    else:
        print(f"\n--- Outlets Activated in the Last 2 Weeks ({len(df)} records) ---")
        print(df.to_string(index=False))


def print_inactive_two_weeks(engine):
    """
    Query 3: Retrieve and print outlets unactivated for 14 days or longer.
    """
    query = """
        SELECT
            outlet_id,
            name AS outlet_name,
            physical_loc AS physical_location,
            ke_number,
            channel,
            division,
            last_activated,
            days_since_last_activation,
            tmr_name,
            tmr_phone
        FROM v_outlets_inactive_2w
        ORDER BY outlet_id
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if df.empty:
        print("\nNo matching outlets found.")
    else:
        print(f"\n--- Outlets Inactive for >= 2 Weeks / No Activation ({len(df)} records) ---")
        print(df.to_string(index=False))


def print_tmr_locations(engine):
    """
    Query 4: Retrieve and print TMR names, contact numbers, associated locations, and assigned outlets.
    """
    query = """
        SELECT
            tmr_name,
            tmr_phone,
            STRING_AGG(DISTINCT physical_loc, ', ') AS associated_locations,
            STRING_AGG(DISTINCT outlet_name, ', ') AS assigned_outlets,
            SUM(activations) AS total_activations
        FROM v_tmr_locations
        WHERE tmr_name IS NOT NULL
        GROUP BY tmr_name, tmr_phone
        ORDER BY tmr_name
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if df.empty:
        print("\nNo TMR records found.")
    else:
        print(f"\n--- TMR Associated Locations & Outlets ({len(df)} records) ---")
        print(df.to_string(index=False))
