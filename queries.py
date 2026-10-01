import pandas as pd
from sqlalchemy import text

# --- Data functions (return DataFrames; used by the web UI and the CLI) ---

def _read(engine, query):
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)


def get_all_outlets(engine):
    return _read(engine, """
        SELECT outlet_id, name AS outlet_name, physical_loc AS physical_location,
               ke_number, channel, division, kdm_name, kdm_phone,
               tmr_name, tmr_phone, team_lead_name AS tl_name, latest_comments
        FROM v_outlets_all
        ORDER BY outlet_id
    """)


def get_recently_activated(engine):
    return _read(engine, """
        SELECT outlet_name, location, ke_number, channel, days_since_last_activation,
               kdm_name, kdm_phone, tmr_name, tmr_phone, tl_name
        FROM v_outlets_recently_activated
    """)


def get_inactive_two_weeks(engine):
    return _read(engine, """
        SELECT outlet_name, location, ke_number, channel, days_since_last_activation,
               kdm_name, kdm_phone, tmr_name, tmr_phone, tl_name
        FROM v_outlets_inactive_2w
    """)


def get_tmr_locations(engine):
    return _read(engine, """
        SELECT tmr_name, tmr_phone, physical_loc AS location, outlet_name, activations
        FROM v_tmr_locations
        ORDER BY tmr_name, physical_loc
    """)


# --- CLI printers (behaviour unchanged) ---

def _print_df(df, empty_msg, title):
    if df.empty:
        print(f"\n{empty_msg}")
    else:
        print(f"\n--- {title} ({len(df)} records) ---")
        print(df.to_string(index=False))


def print_all_outlets_summary(engine):
    _print_df(get_all_outlets(engine), "No outlet records found.", "All Outlets Summary")


def print_activated_last_two_weeks(engine):
    _print_df(get_recently_activated(engine), "No recently activated Nairobi records found.",
              "Nairobi Outlets Activated in Last 2 Weeks")


def print_inactive_two_weeks(engine):
    _print_df(get_inactive_two_weeks(engine), "No inactive Nairobi records found.",
              "Nairobi Outlets Inactive for >= 2 Weeks")


def print_tmr_locations(engine):
    _print_df(get_tmr_locations(engine), "No TMR location records found.",
              "TMR Associated Locations & Outlets")
