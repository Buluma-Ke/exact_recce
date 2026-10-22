import os

from etl.extract import extract_excel_file
from etl.load import calculate_file_sha256, load_data
from etl.transform import transform_data


def import_file(engine, path):
    """
    Run the extract -> transform -> load steps for ONE Excel file.
    Used by both the web upload and the command line menu.
    Returns (ok, message).
    """
    basename = os.path.basename(path)

    raw_data = extract_excel_file(path)
    if not raw_data:
        return False, f"Could not read {basename}. Is it a valid .xlsx file?"

    transformed_data = transform_data(raw_data)
    row_count = sum(len(rows) for rows in transformed_data.values())
    if row_count == 0:
        return False, (
            f"No outlet rows found in {basename}. "
            "Is it a recce report with an outlet name and channel column?"
        )

    file_hashes = {basename: calculate_file_sha256(path)}
    if load_data(engine, transformed_data, file_hashes=file_hashes):
        message = f"Imported {basename}: {row_count} rows processed."
        missing = raw_data[basename].attrs.get("missing_columns")
        if missing:
            message += f" No column found for: {', '.join(missing)}, so those were left blank."
        return True, message
    return False, "Import failed and was rolled back. Check the terminal for details."
