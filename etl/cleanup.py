"""
Tidy a freshly read Excel sheet before the transform step:
  * map differently worded headers onto the names transform.py expects
    ('KE No.' -> ke_number, 'Physical Location/Closest Landmark' -> physical_location, ...)
  * strip invisible characters that come from copy and paste (WhatsApp adds direction
    marks that break phone number parsing)
  * treat 'N/A', 'N/a', 'nil', '-' and similar as empty cells
"""
import re

import pandas as pd

INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")
NOT_AVAILABLE = re.compile(r"\s*(n\s*/\s*a|n\.a\.?|nil|null|none|-+)?\s*", re.I)

# The names transform.py reads, with a plain-English label for messages
EXPECTED = {
    "ke_number": "KE number",
    "outlet_name___location": "outlet name",
    "physical_location": "location",
    "channel": "channel",
    "division": "division",
    "kdm_name_&_tel": "KDM name and phone",
    "tmr_name_&_tel": "TMR name and phone",
    "team_lead_name_&_tel": "team lead name and phone",
    "date_of_recce": "date of recce",
    "date_of_activation": "date of activation",
    "kick___off_time": "kick-off time",
    "raspberry_stock": "raspberry stock",
    "raspberry_price_can": "raspberry price (can)",
    "raspberry_price_bottle": "raspberry price (bottle)",
    "comments/insights": "comments",
}


def _canonical(h):
    """h is a lowercase header with single spaces. Returns the expected name, or None."""
    if re.match(r"^ke\b", h):
        return "ke_number"
    if "outlet" in h:
        return "outlet_name___location"
    if "physical" in h or "landmark" in h:
        return "physical_location"
    if h.startswith("channel"):
        return "channel"
    if "division" in h or "region" in h:
        return "division"
    if "kdm" in h:
        return "kdm_name_&_tel"
    if "tmr" in h:
        return "tmr_name_&_tel"
    if "team lead" in h:
        return "team_lead_name_&_tel"
    if "recce" in h:
        return "date_of_recce"
    if "activation" in h:
        return "date_of_activation"
    if "kick" in h:
        return "kick___off_time"
    if "stock" in h:
        return "raspberry_stock"
    if "price" in h:
        return "raspberry_price_bottle" if "bottle" in h else "raspberry_price_can"
    if "comment" in h or "insight" in h:
        return "comments/insights"
    return None


def _clean_cell(value):
    if not isinstance(value, str):
        return value
    value = INVISIBLE.sub("", value).replace("\u00a0", " ")
    return None if NOT_AVAILABLE.fullmatch(value) else value


def tidy_dataframe(df):
    """Returns the tidied DataFrame. df.attrs lists renamed, ignored and missing columns."""
    renames, ignored, used = {}, [], set()
    for col in df.columns:
        header = re.sub(r"\s+", " ", INVISIBLE.sub("", str(col))).strip().lower()
        target = _canonical(header)
        if target and target not in used:
            used.add(target)
            if header != target:
                renames[col] = target
        elif header and header != "#" and not header.startswith("unnamed"):
            ignored.append(str(col).strip())
    df = df.rename(columns=renames)

    for col in df.columns:
        s = df[col]
        if pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s):
            df[col] = s.map(_clean_cell)

    df.attrs["renamed_columns"] = {str(k).strip(): v for k, v in renames.items()}
    df.attrs["ignored_columns"] = ignored
    df.attrs["missing_columns"] = [EXPECTED[k] for k in EXPECTED if k not in used]
    return df
