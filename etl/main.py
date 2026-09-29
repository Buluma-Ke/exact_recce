from extract import extract_excel_files
from transform import transform_data
from load import load_data

def run_ingestion(engine):
    """
    Coordinates the ETL pipeline: Extract -> Transform -> Load.
    """
    raw_data = extract_excel_files()
    if not raw_data:
        return False

    transformed_data = transform_data(raw_data)

    success = load_data(engine, transformed_data)
    return success

if __name__ == "__main__":
    # Example execution entrypoint if running directly with a SQLAlchemy engine
    pass
