import hashlib
import os
import threading
import webbrowser
from datetime import datetime

from flask import Flask, flash, redirect, render_template, request, url_for, abort
from werkzeug.utils import secure_filename

import queries
from connections import get_db_engine
from dashboard import get_dashboard_data
from etl.extract import FOLDER_PATH, extract_excel_files
from etl.import_file import import_file
from etl.load import calculate_file_sha256
from etl.load import load_data
from etl.transform import transform_data

app = Flask(__name__)
app.secret_key = "recce-local-only"  # only used to sign flash messages
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # reject uploads over 25 MB
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
def dashboard():
    return render_template(
        "dashboard.html", slug=None, reports=REPORTS, **get_dashboard_data(engine)
    )


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
    return redirect(url_for("dashboard"))


@app.post("/upload")
def upload():
    """Add ONE Excel report. A copy is kept in the reports folder."""
    f = request.files.get("file")
    if not f or not f.filename:
        flash("No file selected.", "error")
    elif not f.filename.lower().endswith(".xlsx"):
        flash("Please choose an Excel (.xlsx) file.", "error")
    else:
        os.makedirs(FOLDER_PATH, exist_ok=True)
        data = f.read()
        name = secure_filename(f.filename) or "upload.xlsx"
        path = os.path.join(FOLDER_PATH, name)
        # same name but different contents: keep both, never overwrite
        if os.path.exists(path) and calculate_file_sha256(path) != hashlib.sha256(data).hexdigest():
            stem, ext = os.path.splitext(name)
            path = os.path.join(FOLDER_PATH, f"{stem}_{datetime.now():%Y%m%d-%H%M%S}{ext}")
        is_new_copy = not os.path.exists(path)
        if is_new_copy:
            with open(path, "wb") as out:
                out.write(data)
        ok, message = import_file(engine, path)
        if not ok and is_new_copy:
            try:
                os.remove(path)  # do not leave a bad file for the folder sync to trip over
            except OSError:
                pass
        flash(message, "ok" if ok else "error")
    return redirect(url_for("dashboard"))


URL = "http://127.0.0.1:5000"
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def open_browser():
    """Open the app in Chrome if it is installed, otherwise in the default browser."""
    for path in CHROME_PATHS:
        if os.path.exists(path):
            webbrowser.register("chrome", None, webbrowser.BackgroundBrowser(path))
            webbrowser.get("chrome").open(URL)
            return
    webbrowser.open(URL)


if __name__ == "__main__":
    engine = get_db_engine()  # prompts for the password once, in the terminal
    threading.Timer(1.0, open_browser).start()  # wait a moment for the server to start
    app.run(debug=False, port=5000)
