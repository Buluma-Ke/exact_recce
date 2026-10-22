# Recce Database

A Python tool for parsing, cleaning and ingesting beverage recce reports from Excel into a PostgreSQL database. It has two interfaces: a web UI (dashboard, reports, editing) and a command-line menu, both working on the same database.

## Project Structure

```text
excat_experience/
├── connections.py          # Database engine initialization (prompts for the password)
├── etl/
│   ├── extract.py          # Reads the Excel files (whole folder, or one file)
│   ├── cleanup.py          # Maps differently worded Excel headers, strips hidden characters
│   ├── transform.py        # Cleans staff, dates, times and numbers into row dictionaries
│   ├── load.py             # Stages rows and calls the database's ingest_batch function
│   └── import_file.py      # Runs extract, transform and load for ONE file
├── queries.py              # Report queries; each returns a DataFrame, plus CLI print helpers
├── dashboard.py            # Numbers for the dashboard home page
├── edits.py                # Editing outlets and the review queue
├── app.py                  # Command-line menu
├── web.py                  # Web UI (Flask)
├── start_recce.bat         # Double-click launcher for the web UI
├── sql/
│   ├── recce_schema.sql    # Tables, helper functions and the ingest_batch function
│   ├── views.sql           # Database views behind the reports
│   ├── editing_migration.sql  # History table for outlet edits
│   └── old/                # Superseded first design of the database
├── scripts/                # One-off tools, run as modules (see "Helper scripts")
│   ├── dates/              # Date parsing checks and the dry run
│   └── missing_outlets/    # Tools for finding outlets that were not imported
├── templates/              # HTML templates for the web UI
├── static/                 # Stylesheet for the web UI
└── requirements.txt        # Project dependencies
```

## Prerequisites

- Python 3.9+
- PostgreSQL server running locally with a database named `exact_recce`

## Installation & Setup

1. Navigate to the project folder:

   ```powershell
   cd excat_experience
   ```

2. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1   # On Windows PowerShell
   ```

3. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

4. Create the database objects. In pgAdmin's Query Tool (or with `psql`), run these files **in this order**:

   1. `sql/recce_schema.sql`: tables, helper functions and `ingest_batch`
   2. `sql/views.sql`: the views behind the reports
   3. `sql/editing_migration.sql`: history table for outlet edits (safe to run again)

## Configuration

- **Database:** `connections.py` connects to `exact_recce` on `localhost:5432` as user `Admin`. The password is requested in the terminal each time the app starts.
- **Reports folder:** set `FOLDER_PATH` in `etl/extract.py` to the folder that holds the weekly Excel reports. Single files uploaded in the web UI are also saved there.
- **Session key (optional):** the web UI signs its session cookie with the `RECCE_SECRET_KEY` environment variable. If it is not set, a built-in default is used, which is fine on your own PC.

## How to Run

Use the virtual environment's Python interpreter.

### Web UI

```powershell
.\.venv\Scripts\python.exe web.py
```

Or double-click `start_recce.bat`. After you enter the password the app opens in Chrome (or your default browser) at `http://127.0.0.1:5000`.

**Pages**

- **Dashboard**: outlet totals, activations in the last 7 days and 2 weeks, inactive and never-activated outlets, planned activations, breakdowns by channel and region, activations per week, top team leads, and recent imports
- **Needs attention**: outlets with a missing KE number, location, channel or region (THT outlets are not expected to have a KE number)
- **Review queue**: rows from the Excel files that have no usable activation date
- **All outlets**, **Activated in the last 2 weeks**, **Inactive for 2 weeks or more**: with channel and division drop-down filters and a text filter. The *Activated* and *Inactive* reports cover Nairobi outlets only, as defined in `sql/views.sql`
- **TMR locations**: locations and outlets per TMR, with activation counts

**Importing data**

- **Upload report**: add one Excel file. A copy is saved in the reports folder, and files that are not valid recce reports are rejected.
- **Sync folder**: import every Excel file in the reports folder, for when you have several to add.

**Editing**

- **Edit an outlet** (from *Needs attention* or the *Edit* link on *All outlets*): change the name, KE number, location, channel and region. KE numbers must look like `KE0123456`. Renaming an outlet keeps the old spelling as an alias, so future imports still match it, and every change is logged in `outlet_changes`.
- **Fix a review row**: pick the activation date and save, and the row is imported as a normal activation. *Dismiss* ignores the row.

Editing existing activations (dates, staff, stock) is not available yet.

### Command-line menu

```powershell
.\.venv\Scripts\python.exe app.py
```

1. Sync / ingest all Excel reports in the folder and view all outlets
2. Add a single Excel report file (asks for the file path; you can drag the file into the window)
3. View outlets activated in the last 2 weeks
4. View outlets inactive for 2 weeks or more
5. View TMR locations and outlets
6. Exit

## Using it from your phone

The web UI has no login, so do not publish it on the internet. The safe, free way to reach it from a phone is [Tailscale](https://tailscale.com), a private network between your own devices.

1. Install Tailscale on the PC and on the phone and sign in to the same account.
2. Allow the port for Tailscale addresses only. Run once in an administrator Command Prompt:

   ```text
   netsh advfirewall firewall add rule name="Recce (Tailscale only)" dir=in action=allow protocol=TCP localport=5000 remoteip=100.64.0.0/10
   ```

   If Windows shows a firewall pop-up when the app starts, do not allow public networks.
3. Start the app on the PC, then open `http://<pc-name>:5000` (or the PC's `100.x.x.x` Tailscale address) on the phone.

The PC must be on, awake and running the app. On phones the menu slides in from the button at the top.

Every form in the web UI carries a security token, so other websites cannot submit changes for you.

## Helper scripts

Run these from the project root as modules (running the files directly fails with `No module named 'etl'`):

```powershell
# Dry run: cleans the Excel files and prints a summary per file, with no database changes
.\.venv\Scripts\python.exe -m scripts.dates.preview_dates

# Lists Excel rows that are skipped and KE numbers that would merge outlets
.\.venv\Scripts\python.exe -m scripts.missing_outlets.diagnose_missing chandarana

# Compares every outlet name in the Excel files with the outlets table
.\.venv\Scripts\python.exe -m scripts.missing_outlets.reconcile_outlets
```

## Notes on the Excel Data

- Dates arrive in mixed forms: real date cells, text written day-first or month-first, and cells holding several dates. `transform.py` reads all of these, corrects day/month swaps by comparing against the rest of the file, and keeps the latest date when a cell holds more than one. Anything it still cannot read is listed during the run.
- Column headers differ between files (`KE No.`, `KE Number`, `Physical Location/Closest Landmark`, `Raspberry Price`). `etl/cleanup.py` maps them onto the expected names, prints what it mapped, and warns when a file has no column for something. Hidden characters from copy and paste (such as WhatsApp direction marks) are removed, and `N/A`, `N/a` and similar are treated as empty.
- Outlets are matched by KE number first (when there is one), then by known aliases, then by name. A KE number that is blank or not in the form `KE` plus digits is treated as no KE number, so placeholder values such as `N/A` or `NAN` cannot merge unrelated outlets.
- Different versions of the same report are merged: new rows are inserted, changed rows are updated, identical rows are left alone and nothing is deleted. When copies differ, the one loaded last overwrites the others. Files uploaded one at a time are recognised by their contents.
- Imports only fill blank outlet details and never overwrite existing ones, so edits made in the web UI are kept.
- Rows without an activation date are not imported as activations. They are held in the `import_review` table and shown in the *Review queue*. If the same Excel file is imported again and still lacks the date, the row returns to the queue, so fix the date in the Excel file too.
