import glob
import os
import pandas as pd

from etl.cleanup import tidy_dataframe

FOLDER_PATH = r"C:\Users\Admin\OneDrive\Documentos\Exact\recce_reports"


def _read_excel(filename):
    try:
        df = pd.read_excel(filename)
    except ValueError:
        # openpyxl rejects some files with a damaged stylesheet;
        # calamine ignores styles, so it can still read the data.
        df = pd.read_excel(filename, engine="calamine")

    df = tidy_dataframe(df)
    basename = os.path.basename(filename)
    for original, expected in df.attrs["renamed_columns"].items():
        print(f"  {basename}: column '{original}' read as {expected}")
    if df.attrs["ignored_columns"]:
        print(f"  {basename}: columns not used: {', '.join(df.attrs['ignored_columns'])}")
    if df.attrs["missing_columns"]:
        print(f"  {basename}: WARNING no column found for: {', '.join(df.attrs['missing_columns'])}")
    return df

def extract_excel_files():
    """
    Scan the recce reports directory and read all Excel files into raw DataFrames.
    Returns a dictionary mapping filename to raw pandas DataFrame.
    """
    print("\n--- Scanning and Extracting Excel Files ---")
    all_files = glob.glob(os.path.join(FOLDER_PATH, "*.xlsx"))

    if not all_files:
        print("No Excel files found in the specified directory.")
        return {}

    extracted_data = {}
    for filename in all_files:
        basename = os.path.basename(filename)
        print(f"Extracting: {basename}...")
        try:
            extracted_data[basename] = _read_excel(filename)
        except Exception as e:
            print(f"Error reading {basename}: {e}")

    return extracted_data


def extract_excel_file(path):
    """
    Read a single Excel file (any location) into a raw DataFrame.
    Returns {filename: DataFrame}, or {} if the file cannot be read.
    """
    basename = os.path.basename(path)
    print(f"\n--- Extracting Single Excel File: {basename} ---")
    try:
        return {basename: _read_excel(path)}
    except Exception as e:
        print(f"Error reading {basename}: {e}")
        return {}
