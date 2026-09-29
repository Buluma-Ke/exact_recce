from datetime import datetime
import re
import pandas as pd

def parse_staff(raw_str):
    """
    Parse staff name and phone number from a combined raw string.
    Handles hyphens, extra whitespace, or combined name-phone strings smoothly.
    """
    if not raw_str or str(raw_str).lower() == "nan":
        return None, None

    clean_str = str(raw_str).strip()

    # Try matching standard Kenyan phone patterns (e.g., 07XXXXXXXX, 01XXXXXXXX, +254...)
    # This separates trailing phone numbers even if separated only by spaces instead of a hyphen.
    phone_match = re.search(r'(?:\+?254|0)[17]\d{8}$', clean_str)

    if phone_match:
        phone = phone_match.group(0)
        name = clean_str[:phone_match.start()].strip()
        # Clean up any leftover hanging hyphens from name splitting
        name = re.sub(r'[\-_]+$', '', name).strip()
        return (name if name else None), phone

    # Fallback to legacy hyphen split if regex didn't catch a trailing phone
    parts = clean_str.split("-")
    name = parts[0].strip()
    phone = parts[1].strip() if len(parts) > 1 else None
    return (name if name else None), (phone if phone else None)

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

def transform_data(raw_data_dict):
    """
    Takes a dictionary of raw DataFrames and applies cleaning and schema formatting.
    Returns a dictionary mapping filename to processed list of row dictionaries.
    """
    print("\n--- Transforming and Cleaning Data ---")
    transformed_data = {}

    for basename, df in raw_data_dict.items():
        # Standardize column names
        df.columns = (
            df.columns.str.strip()
            .str.lower()
            .str.replace(" ", "_")
            .str.replace("-", "_")
            .str.replace(r"[()]", "", regex=True)
        )
        df.replace(["N/A", "n/a", ""], None, inplace=True)

        cleaned_rows = []
        for _, row in df.iterrows():
            outlet_name = row.get("outlet_name___location") or row.get("outlet_name")

            if not outlet_name or pd.isna(outlet_name) or str(outlet_name).lower() == "nan":
                continue

            outlet_name_str = str(outlet_name).strip()
            channel = row.get("channel")
            if pd.isna(channel) or str(channel).lower() == "nan":
                continue

            # Parse staff fields securely
            tmr_name, tmr_phone = parse_staff(str(row.get("tmr_name_&_tel", "")))
            kdm_name, kdm_phone = parse_staff(str(row.get("kdm_name_&_tel", "")))
            tl_name, tl_phone = parse_staff(str(row.get("team_lead_name_&_tel", "")))

            row_dict = {
                "ke_number": row.get("ke_number"),
                "outlet_name": outlet_name_str,
                "physical_location": row.get("physical_location"),
                "channel": channel,
                "division": row.get("division"),
                "tmr_name": tmr_name,
                "tmr_phone": tmr_phone,
                "kdm_name": kdm_name,
                "kdm_phone": kdm_phone,
                "tl_name": tl_name,
                "tl_phone": tl_phone,
                "recce_date": parse_date(row.get("date_of_recce")),
                "act_date": parse_date(row.get("date_of_activation")),
                "kickoff": str(row.get("kick___off_time", "")),
                "stock": str(row.get("raspberry_stock", "")),
                "price": str(row.get("raspberry_price_bottle", "")),
                "comments": str(row.get("comments/insights", "")),
                "source_file": basename
            }
            cleaned_rows.append(row_dict)

        transformed_data[basename] = cleaned_rows

    return transformed_data
