import os

from connections import get_db_engine
from etl.load import load_data 
from queries import (
    print_activated_last_two_weeks,
    print_all_outlets_summary,
    print_inactive_two_weeks,
    print_tmr_locations,
)
from etl.extract import FOLDER_PATH, extract_excel_files
from etl.import_file import import_file
from etl.transform import transform_data


def main_menu():
    """
    Execute the interactive command line interface loop.
    """

    print("Initializing Database Connection...")
    engine = get_db_engine()

    while True:
        print("\n======================================")
        print("      BEVERAGE RECCE DATABASE CLI")
        print("======================================")
        print("1. Import ALL Excel Reports in a Folder & View All Outlets")
        print("2. Add a Single Excel Report File")
        print("3. View Outlets Activated in Last 2 Weeks")
        print("4. View Outlets Inactive for >= 2 Weeks")
        print("5. View TMR Associated Locations & Outlets")
        print("6. Exit")

        choice = input("\nEnter your choice (1-6): ").strip()

        if choice == "1":
            # Running the full E -> T -> L pipeline steps explicitly
            folder = input(
                f"\nFolder with the Excel reports (press Enter for {FOLDER_PATH}): "
            ).strip().strip('"').strip("'")
            if folder and not os.path.isdir(folder):
                print(f"Folder not found: {folder}")
                continue
            raw_data = extract_excel_files(folder or None)
            if raw_data:
                transformed_data = transform_data(raw_data)
                success = load_data(engine, transformed_data)
                if success:
                    print_all_outlets_summary(engine)
        elif choice == "2":
            path = input(
                "\nPath to the Excel file (you can drag the file into this window): "
            ).strip().strip('"').strip("'")
            if not path:
                print("No path entered.")
            elif not os.path.isfile(path):
                print(f"File not found: {path}")
            elif not path.lower().endswith(".xlsx"):
                print("Please choose an Excel (.xlsx) file.")
            else:
                success, message = import_file(engine, path)
                print(f"\n{message}")
                if success:
                    print_all_outlets_summary(engine)
        elif choice == "3":
            print_activated_last_two_weeks(engine)
        elif choice == "4":
            print_inactive_two_weeks(engine)
        elif choice == "5":
            print_tmr_locations(engine)
        elif choice == "6":
            print("\nExiting. Goodbye!")
            break
        else:
            print("\nInvalid choice. Please select between 1 and 6.")


if __name__ == "__main__":
    main_menu()
