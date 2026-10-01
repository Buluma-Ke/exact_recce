from connections import get_db_engine
from etl.load import load_data 
from queries import (
    print_activated_last_two_weeks,
    print_all_outlets_summary,
    print_inactive_two_weeks,
    print_tmr_locations,
)
from etl.extract import extract_excel_files
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
        print("1. Sync / Ingest Excel Reports & View All Outlets")
        print("2. View Outlets Activated in Last 2 Weeks")
        print("3. View Outlets Inactive for >= 2 Weeks")
        print("4. View TMR Associated Locations & Outlets")
        print("5. Exit")

        choice = input("\nEnter your choice (1-5): ").strip()

        if choice == "1":
            # Running the full E -> T -> L pipeline steps explicitly
            raw_data = extract_excel_files()
            if raw_data:
                transformed_data = transform_data(raw_data)
                success = load_data(engine, transformed_data)
                if success:
                    print_all_outlets_summary(engine)
        elif choice == "2":
            print_activated_last_two_weeks(engine)
        elif choice == "3":
            print_inactive_two_weeks(engine)
        elif choice == "4":
            print_tmr_locations(engine)
        elif choice == "5":
            print("\nExiting. Goodbye!")
            break
        else:
            print("\nInvalid choice. Please select between 1 and 5.")


if __name__ == "__main__":
    main_menu()
