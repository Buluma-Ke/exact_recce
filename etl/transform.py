from datetime import date, datetime
import re
import statistics
import pandas as pd

TODAY = date.today()

# d/m/yyyy or m/d/yyyy text dates (both orders turn up in the files)
TEXT_DATE_RE = re.compile(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})")
# a slash mistyped as a digit, e.g. '7/1812026' for '7/18/2026'
TYPO_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})1?(20\d{2})")
# '26th & 27th 09/2026' style: several days followed by month/year
DAYS_MONTH_RE = re.compile(r"((?:\d{1,2}(?:st|nd|rd|th)\s*(?:&|and|,)?\s*)+)(\d{1,2})/(\d{4})")


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


def _safe_date(y, m, d):
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def _text_readings(text):
    """
    Find every date in a text cell. Each date comes back as a list of its possible
    readings (day first, then month first). Impossible readings, such as month 17,
    are left out, so '07/14/2026' has one reading and '07/10/2026' has two.
    Handles '13/09/2026', '11/9/2026,12/9/2026', '07/14/2026 & 07/16/2026',
    '26th & 27th 09/2026' and a mistyped '7/1812026'.
    """
    found = []
    for a, b, y in TEXT_DATE_RE.findall(text) or TYPO_DATE_RE.findall(text):
        readings = []
        for d in (_safe_date(y, b, a), _safe_date(y, a, b)):
            if d and d not in readings:
                readings.append(d)
        if readings:
            found.append(readings)
    if found:
        return found

    match = DAYS_MONTH_RE.search(text)
    if match:
        days = re.findall(r"\d{1,2}", match.group(1))
        singles = [_safe_date(match.group(3), match.group(2), d) for d in days]
        return [[d] for d in singles if d]

    iso = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", text)
    if iso and _safe_date(*iso.groups()):
        return [[_safe_date(*iso.groups())]]
    return []


def _as_date(val):
    return val.date() if isinstance(val, datetime) else val


def file_anchor(df):
    """
    Work out roughly when a file's dates fall, using only dates that cannot be
    day/month swapped (text dates with one possible reading, and real dates with
    a day above 12). Falls back to today when a file has none.
    """
    ordinals = []
    for col in ("date_of_recce", "date_of_activation"):
        if col not in df.columns:
            continue
        for v in df[col].dropna():
            if isinstance(v, (datetime, date)):
                d = _as_date(v)
                if d.day > 12:
                    ordinals.append(d.toordinal())
            else:
                ordinals.extend(r[0].toordinal() for r in _text_readings(str(v)) if len(r) == 1)
    if not ordinals:
        return TODAY
    return date.fromordinal(int(statistics.median(ordinals)))


def _score(d, anchor):
    # Distance from the file's anchor date: the closest reading wins.
    return abs((d - anchor).days)


def _fix_year(d, anchor):
    # Year typos such as 2028 for 2026: if still in the future, try the anchor's year.
    if d > TODAY:
        try:
            alt = d.replace(year=anchor.year)
        except ValueError:
            return d
        if alt <= TODAY:
            return alt
    return d


def parse_date(val, anchor=None):
    """
    Convert raw date values to python date objects.
    Day and month can be swapped in real date cells and text dates can be written
    either way round, so when both readings are possible the one closest to the
    file's anchor date is used. If a cell holds several dates, the latest is used.
    """
    if val is None or pd.isna(val):
        return None
    anchor = anchor or TODAY

    if isinstance(val, (datetime, date)):
        d = _as_date(val)
        candidates = [d]
        if d.day <= 12 and d.day != d.month:
            candidates.append(date(d.year, d.day, d.month))
        return _fix_year(min(candidates, key=lambda c: _score(c, anchor)), anchor)

    readings = _text_readings(str(val))
    if not readings:
        return None
    best = [min(r, key=lambda c: _score(c, anchor)) for r in readings]
    return _fix_year(max(best), anchor)


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

        anchor = file_anchor(df)

        stats = {"fixed": 0}

        def clean_date(raw, label):
            parsed = parse_date(raw, anchor)
            if isinstance(raw, (datetime, date)) and parsed and parsed != _as_date(raw):
                stats["fixed"] += 1
            elif parsed is None and raw is not None and not pd.isna(raw):
                print(f"  {basename}: unreadable {label}: {raw!r}")
            return parsed

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
                "recce_date": clean_date(row.get("date_of_recce"), "recce date"),
                "act_date": clean_date(row.get("date_of_activation"), "activation date"),
                "kickoff": parse_time(row.get("kick___off_time")),
                "stock_qty": parse_numeric(row.get("raspberry_stock")),
                "stock_unit": "cases",
                "price_can": parse_numeric(row.get("raspberry_price_can")),
                "price_bottle": parse_numeric(row.get("raspberry_price_bottle")),
                "comments": str(row.get("comments/insights", "")),
                "source_file": basename
            }
            cleaned_rows.append(row_dict)

        if stats["fixed"]:
            print(f"  {basename}: {stats['fixed']} day/month-swapped dates corrected")
        transformed_data[basename] = cleaned_rows

    return transformed_data
