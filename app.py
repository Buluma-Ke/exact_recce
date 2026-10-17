import os
import sys

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import text

from connections import get_db_engine
from dashboard import get_dashboard_data
from etl.load import load_data 
from queries import (
    print_activated_last_two_weeks,
    print_all_outlets_summary,
    print_inactive_two_weeks,
    print_tmr_locations,
)
from etl.extract import extract_excel_files
from etl.transform import transform_data


# ----------------------------------------------------------------------
# Web UI (Flask). Start it with:  python app.py
# The original command line menu still works:  python app.py --cli
# ----------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("RECCE_SECRET_KEY", "recce-local-dev")

# Set once in the __main__ block below (the password prompt runs a single time).
engine = None

# slug -> (menu title, SQL, message shown when there are no rows)
REPORTS = {
    "outlets": (
        "All outlets",
        """
        SELECT name AS outlet_name, physical_loc AS physical_location, ke_number,
               channel, division, kdm_name, kdm_phone, tmr_name, tmr_phone,
               tl_name
        FROM v_outlets_all
        ORDER BY outlet_id
        """,
        "No outlets yet. Click Sync reports to load the Excel files.",
    ),
    "recently-activated": (
        "Activated in the last 2 weeks",
        "SELECT * FROM v_outlets_recently_activated",
        "No Nairobi outlets were activated in the last 2 weeks.",
    ),
    "inactive": (
        "Inactive for 2 weeks or more",
        "SELECT * FROM v_outlets_inactive_2w",
        "Every Nairobi outlet was activated in the last 2 weeks.",
    ),
    "tmr-locations": (
        "TMR locations",
        "SELECT * FROM v_tmr_locations",
        "No TMR assignments yet.",
    ),
}


@app.route("/")
def dashboard():
    return render_template(
        "dashboard.html", reports=REPORTS, slug=None, **get_dashboard_data(engine)
    )


@app.route("/<slug>")
def report(slug):
    if slug not in REPORTS:
        abort(404)
    title, sql, empty_msg = REPORTS[slug]
    columns, rows = [], []
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [list(r) for r in result.fetchall()]
    except Exception as e:
        flash(f"Could not load this report: {e}", "error")
    return render_template(
        "report.html", reports=REPORTS, slug=slug, title=title,
        columns=columns, rows=rows, empty_msg=empty_msg,
    )


@app.route("/sync", methods=["POST"])
def sync():
    # Same E -> T -> L steps as menu option 1 of the CLI
    raw_data = extract_excel_files()
    if not raw_data:
        flash("No Excel files found in the reports folder.", "error")
    else:
        transformed_data = transform_data(raw_data)
        if load_data(engine, transformed_data):
            flash(f"Synced {len(raw_data)} report file(s).", "ok")
        else:
            flash("Sync failed and was rolled back. See the terminal for details.", "error")
    return redirect(request.referrer or url_for("dashboard"))


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
    if "--cli" in sys.argv:
        main_menu()
    else:
        print("Initializing Database Connection...")
        engine = get_db_engine()
        # use_reloader=False so the password prompt only appears once
        app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
