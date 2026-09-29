from datetime import datetime
import re
import pandas as pd

def parse_staff(raw_str):
    """
    Parse staff name and phone number from a combined raw string.
    Handles standard formats, spaced out mobile numbers, and hyphens smoothly.
    """
    if not raw_str or str(raw_str).lower() == "nan":
        return None, None

    clean_str = str(raw_str).strip()

    # Look for Kenyan mobile patterns allowing optional spaces and country codes
    phone_pattern = r'(?:(?:\+?254|0)[17]\d{2}[\s]?\d{3}[\s]?\d{3}|(?:\+?254|0)[17]\d{8})'

    match = re.search(phone_pattern, clean_str)

    if match:
        phone_raw = match.group(0)
        phone = re.sub(r'\s+', '', phone_raw)
        name = clean_str[:match.start()].strip()
        name = re.sub(r'[\-_]+$', '', name).strip()
        return (name if name else None), phone

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

def parse_time(val):
    """
    Convert messy time strings (e.g. '11.00am', '2:30 PM') into standard SQL time format ('HH:MM:SS').
    """
    if pd.isna(val) or str(val).lower() in ["nan", "none", ""]:
        return None

    val_str = str(val).strip()
    try:
        normalized = val_str.lower().replace('.', ':')
        dt = pd.to_datetime(normalized, format='%I:%M%p', errors='raise')
        return dt.strftime('%H:%M:%S')
    except Exception:
        try:
            dt = pd.to_datetime(val_str, errors='raise')
            return dt.strftime('%H:%M:%S')
        except Exception:
            return None

def parse_numeric(val):
    """
    Convert raw numeric fields safely to floats/ints.
    """
    if pd.isna(val) or str(val).lower() in ["nan", "none", ""]:
        return None
    try:
        cleaned = re.sub(r'[^\d.]', '', str(val))
        return float(cleaned) if '.' in cleaned else int(cleaned)
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
                "kickoff": parse_time(row.get("kick___off_time")),
                "stock_qty": parse_numeric(row.get("raspberry_stock")),
                "stock_unit": "cases",
                "price_can": parse_numeric(row.get("raspberry_price_can")),
                "price_bottle": parse_numeric(row.get("raspberry_price_bottle")),
                "comments": str(row.get("comments/insights", "")),
                "source_file": basename
            }
            cleaned_rows.append(row_dict)

        transformed_data[basename] = cleaned_rows

    return transformed_data
