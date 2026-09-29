import glob
import os
import pandas as pd

FOLDER_PATH = r"C:\Users\Admin\OneDrive\Documentos\Exact\recce_reports"

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
            df = pd.read_excel(filename)
            extracted_data[basename] = df
        except Exception as e:
            print(f"Error reading {basename}: {e}")

    return extracted_data
