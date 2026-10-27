import hashlib
import io
import os
import secrets
import threading
import webbrowser
from datetime import datetime

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename

import edits
import logistics
import queries
from connections import get_db_engine
from dashboard import get_dashboard_data
from etl.extract import FOLDER_PATH
from etl.import_file import import_file
from etl.load import calculate_file_sha256
from etl.load import load_data
from etl.transform import transform_data

app = Flask(__name__)
# Signs the session cookie (flash messages and the CSRF token). Set RECCE_SECRET_KEY to your own value.
app.secret_key = os.environ.get("RECCE_SECRET_KEY", "recce-local-only")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024  # a whole folder of reports can be uploaded at once
app.config["MAX_FORM_PARTS"] = 5000
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

# Pages that get the channel and division drop-down filters
FILTERABLE = ("outlets", "activated", "inactive")

# Columns fetched by the queries but not shown on a given page
HIDDEN_COLUMNS = {
    "outlets": ["outlet_id", "latest_comments"],
}


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def check_csrf():
    """Every POST must carry the token from our own forms, so other websites cannot post for you."""
    if request.method == "POST":
        sent = request.form.get("_csrf", "").encode()
        if not sent or not secrets.compare_digest(sent, session.get("_csrf", "").encode()):
            flash("Your session expired. Please try again.", "error")
            return redirect(url_for("dashboard"))


@app.context_processor
def inject_attention():
    """Counts for the sidebar badges."""
    if engine is None:
        return {"attention": {"gaps": 0, "review": 0}}
    return {"attention": edits.count_attention(engine)}


def _safe_next(default):
    """Where to go after saving. Only local paths are accepted."""
    nxt = request.form.get("next") or request.args.get("next") or ""
    if nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt:
        return nxt
    return default


@app.route("/")
def dashboard():
    return render_template(
        "dashboard.html", slug=None, reports=REPORTS, **get_dashboard_data(engine)
    )


@app.route("/logistics")
def logistics_guide():
    guide = logistics.get_guide(engine, request.args.get("week"))
    return render_template("logistics.html", slug=None, reports=REPORTS, g=guide)


@app.get("/logistics/download")
def logistics_download():
    guide = logistics.get_guide(engine, request.args.get("week"))
    if not guide["rows"]:
        flash("No outlets are activating in that week, so there is nothing to download.", "error")
        return redirect(url_for("logistics_guide", week=guide["start"].isoformat()))
    name = f"Logistics_Guide_{guide['start']:%Y-%m-%d}_to_{guide['end']:%Y-%m-%d}.xlsx"
    return send_file(
        io.BytesIO(logistics.build_xlsx(guide)), as_attachment=True, download_name=name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/gaps")
def gaps():
    current = request.args.get("missing", "all")
    if current not in edits.GAP_FILTERS:
        current = "all"
    rows, counts = edits.get_gaps(engine, current)
    pills = [("all", "Any gap"), ("ke", "KE number"), ("location", "Location"),
             ("channel", "Channel"), ("division", "Region")]
    return render_template("gaps.html", slug=None, reports=REPORTS, rows=rows,
                           current=current, pills=[(k, label, counts[k]) for k, label in pills])


@app.route("/outlets/<int:outlet_id>/edit", methods=["GET", "POST"])
def outlet_edit(outlet_id):
    outlet = edits.get_outlet(engine, outlet_id)
    if not outlet:
        abort(404)
    back = _safe_next(url_for("gaps"))
    if request.method == "POST":
        ok, message, values = edits.update_outlet(engine, outlet_id, request.form)
        if ok:
            flash(message, "ok")
            return redirect(back)
        flash(message, "error")
        outlet = {**outlet, **values}
    return render_template("outlet_edit.html", slug=None, reports=REPORTS, outlet=outlet,
                           choices=edits.get_choices(engine, outlet), back=back)


@app.route("/review")
def review():
    return render_template("review.html", slug=None, reports=REPORTS, rows=edits.get_review(engine))


@app.post("/review/<int:review_id>/fix")
def review_fix(review_id):
    ok, message = edits.fix_review(engine, review_id, request.form.get("activation_date", ""))
    flash(message, "ok" if ok else "error")
    return redirect(url_for("review"))


@app.post("/review/<int:review_id>/dismiss")
def review_dismiss(review_id):
    ok, message = edits.dismiss_review(engine, review_id)
    flash(message, "ok" if ok else "error")
    return redirect(url_for("review"))


@app.route("/<slug>")
def report(slug):
    if slug not in REPORTS:
        abort(404)
    title, fetch, empty_msg = REPORTS[slug]
    df = fetch(engine)
    edit_ids = df["outlet_id"].tolist() if slug == "outlets" and "outlet_id" in df.columns else None
    df = df.drop(columns=HIDDEN_COLUMNS.get(slug, [])).fillna("")
    return render_template(
        "report.html", slug=slug, title=title, empty_msg=empty_msg,
        reports=REPORTS, columns=list(df.columns), rows=df.values.tolist(),
        edit_ids=edit_ids, filters=slug in FILTERABLE,
    )


def _archive_copy(data, filename):
    """Keep a copy of an uploaded file in the reports folder. Returns (path, is_new_copy)."""
    os.makedirs(FOLDER_PATH, exist_ok=True)
    name = secure_filename(filename) or "upload.xlsx"
    path = os.path.join(FOLDER_PATH, name)
    # same name but different contents: keep both, never overwrite
    if os.path.exists(path) and calculate_file_sha256(path) != hashlib.sha256(data).hexdigest():
        stem, ext = os.path.splitext(name)
        path = os.path.join(FOLDER_PATH, f"{stem}_{datetime.now():%Y%m%d-%H%M%S}{ext}")
    is_new_copy = not os.path.exists(path)
    if is_new_copy:
        with open(path, "wb") as out:
            out.write(data)
    return path, is_new_copy


def _import_upload(file_storage):
    """Archive one uploaded file and import it. Returns (ok, message)."""
    # a folder upload sends 'folder/file.xlsx'; keep only the file name
    name = os.path.basename((file_storage.filename or "").replace("\\", "/"))
    path, is_new_copy = _archive_copy(file_storage.read(), name)
    ok, message = import_file(engine, path)
    if not ok and is_new_copy:
        try:
            os.remove(path)  # do not leave a bad file behind
        except OSError:
            pass
    return ok, message


@app.post("/upload")
def upload():
    """Add ONE Excel report. A copy is kept in the reports folder."""
    f = request.files.get("file")
    if not f or not f.filename:
        flash("No file selected.", "error")
    elif not f.filename.lower().endswith(".xlsx"):
        flash("Please choose an Excel (.xlsx) file.", "error")
    else:
        ok, message = _import_upload(f)
        flash(message, "ok" if ok else "error")
    return redirect(url_for("dashboard"))


@app.post("/import")
def import_folder():
    """Import every .xlsx the browser sent from a chosen folder (or several chosen files).
    Only files directly in the folder are used, not those in its subfolders."""
    imported, failed, ignored, missing_cols = 0, [], 0, 0
    for f in request.files.getlist("files"):
        parts = (f.filename or "").replace("\\", "/").split("/")
        name = parts[-1]
        if len(parts) > 2 or not name.lower().endswith(".xlsx") or name.startswith("~$"):
            ignored += 1
            continue
        ok, message = _import_upload(f)
        if ok:
            imported += 1
            missing_cols += "No column found for" in message
        else:
            failed.append(f"{name}: {message}")

    total = imported + len(failed)
    if not total:
        flash("No Excel (.xlsx) files found in that selection.", "error")
        return redirect(url_for("dashboard"))
    summary = f"Imported {imported} of {total} Excel file{'' if total == 1 else 's'}."
    if ignored:
        summary += f" Ignored {ignored} other file{'' if ignored == 1 else 's'}."
    if missing_cols:
        summary += f" {missing_cols} had columns that were not found (see the terminal for details)."
    flash(summary, "ok" if imported else "error")
    if failed:
        shown = "; ".join(failed[:4]) + (f"; and {len(failed) - 4} more" if len(failed) > 4 else "")
        flash(f"Not imported: {shown}", "error")
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
    # host="0.0.0.0" lets other devices reach the app (your phone, over Tailscale).
    # Keep the Windows Firewall rule limited to Tailscale addresses (see setup steps).
    app.run(debug=False, host="0.0.0.0", port=5000)
