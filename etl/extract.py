import glob
import os
import pandas as pd

from etl.cleanup import tidy_dataframe

# Default reports folder: used for archived copies of uploaded files and as the CLI's default folder.
# Set the RECCE_REPORTS_DIR environment variable to use another folder without editing code.
FOLDER_PATH = os.environ.get(
    "RECCE_REPORTS_DIR", r"C:\Users\Admin\OneDrive\Documentos\Exact\recce_reports"
)


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

def extract_excel_files(folder=None):
    """
    Scan a folder (default: FOLDER_PATH) and read all Excel files into raw DataFrames.
    Files are read oldest first, so when versions of the same report disagree the most
    recently edited file is loaded last and wins. Excel's temporary "~$" lock files are skipped.
    Returns a dictionary mapping filename to raw pandas DataFrame.
    """
    folder = folder or FOLDER_PATH
    print(f"\n--- Scanning and Extracting Excel Files in {folder} ---")
    all_files = [
        f for f in glob.glob(os.path.join(folder, "*.xlsx"))
        if not os.path.basename(f).startswith("~$")
    ]
    all_files.sort(key=os.path.getmtime)

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
