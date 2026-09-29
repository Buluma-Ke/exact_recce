import pandas as pd
from sqlalchemy import text


def print_all_outlets_summary(engine):
    """
    Query 1: Retrieve and print all outlets with their latest associated contacts,
    team lead, and KDM phone number.
    """
    query = """
        SELECT
            outlet_id,
            name AS outlet_name,
            physical_loc AS physical_location,
            ke_number,
            channel,
            division,
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
    Option 2: View outlets activated in the last 2 weeks (Nairobi only).
    """
    query = """
        SELECT
            outlet_name,
            location,
            ke_number,
            channel,
            days_since_last_activation,
            kdm_name,
            kdm_phone,
            tmr_name,
            tmr_phone,
            tl_name
        FROM v_outlets_recently_activated
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if df.empty:
        print("\nNo recently activated Nairobi records found.")
    else:
        print(f"\n--- Nairobi Outlets Activated in Last 2 Weeks ({len(df)} records) ---")
        print(df.to_string(index=False))


def print_inactive_two_weeks(engine):
    """
    Option 3: View outlets inactive for >= 2 weeks (Nairobi only).
    """
    query = """
        SELECT
            outlet_name,
            location,
            ke_number,
            channel,
            days_since_last_activation,
            kdm_name,
            kdm_phone,
            tmr_name,
            tmr_phone,
            tl_name
        FROM v_outlets_inactive_2w
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if df.empty:
        print("\nNo inactive Nairobi records found.")
    else:
        print(f"\n--- Nairobi Outlets Inactive for >= 2 Weeks ({len(df)} records) ---")
        print(df.to_string(index=False))


def print_tmr_locations(engine):
    """
    Query 4: Retrieve and print TMR associated locations, outlets, and activation counts.
    """
    query = """
        SELECT
            tmr_name,
            tmr_phone,
            physical_loc AS location,
            outlet_name,
            activations
        FROM v_tmr_locations
        ORDER BY tmr_name, physical_loc
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if df.empty:
        print("\nNo TMR location records found.")
    else:
        print(f"\n--- TMR Associated Locations & Outlets ({len(df)} records) ---")
        print(df.to_string(index=False))
