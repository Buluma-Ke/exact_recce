import glob
import os
import pandas as pd
from etl.extract import FOLDER_PATH

for f in glob.glob(os.path.join(FOLDER_PATH, "*.xlsx")):
    df = pd.read_excel(f)
    print("\n==", os.path.basename(f))
    print("columns:", list(df.columns))
    cols = [c for c in df.columns if "date" in str(c).lower()]
    if not cols:
        print("no column with 'date' in its name")
    for col in cols:
        print("--", col)
        for v in df[col].dropna().head(10):
            print("  ", type(v).__name__, repr(v))
