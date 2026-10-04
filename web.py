from flask import Flask, flash, redirect, render_template, url_for, abort

import queries
from connections import get_db_engine
from etl.extract import extract_excel_files
from etl.load import load_data
from etl.transform import transform_data

app = Flask(__name__)
app.secret_key = "recce-local-only"  # only used to sign flash messages
engine = None

REPORTS = {
    "outlets": ("All outlets", queries.get_all_outlets,
                "No outlets yet. Use Sync reports to import your Excel files."),
    "activated": ("Activated in the last 2 weeks", queries.get_recently_activated,
                  "No Nairobi outlets were activated in the last 2 weeks."),
    "inactive": ("Inactive for 2 weeks or more", queries.get_inactive_two_weeks,
                 "No Nairobi outlets have been inactive for 2 weeks or more."),
    "tmr": ("TMR locations", queries.get_tmr_locations,
            "No TMR location records found."),
}

# Columns fetched by the queries but not shown on a given page
HIDDEN_COLUMNS = {
    "outlets": ["outlet_id", "latest_comments"],
}


@app.route("/")
def index():
    return redirect(url_for("report", slug="outlets"))


@app.route("/<slug>")
def report(slug):
    if slug not in REPORTS:
        abort(404)
    title, fetch, empty_msg = REPORTS[slug]
    df = fetch(engine).drop(columns=HIDDEN_COLUMNS.get(slug, [])).fillna("")
    return render_template(
        "report.html", slug=slug, title=title, empty_msg=empty_msg,
        reports=REPORTS, columns=list(df.columns), rows=df.values.tolist(),
    )


@app.post("/sync")
def sync():
    raw = extract_excel_files()
    if not raw:
        flash("No Excel files found in the reports folder.", "error")
    elif load_data(engine, transform_data(raw)):
        flash(f"Sync complete: {len(raw)} file(s) processed.", "ok")
    else:
        flash("Sync failed and was rolled back. Check the terminal for details.", "error")
    return redirect(url_for("report", slug="outlets"))


if __name__ == "__main__":
    engine = get_db_engine()  # prompts for the password once, in the terminal
    app.run(debug=False, port=5000)
