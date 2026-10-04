# Recce Database

A Python tool for parsing, cleaning and ingesting beverage recce reports from Excel into a PostgreSQL database. It has two interfaces: a command-line menu and a small web UI, both reading the same reports.

## Project Structure

```text
excat_experience/
├── connections.py      # Database engine initialization (prompts for the password)
├── etl/
│   ├── extract.py      # Scans the reports folder and reads the Excel files
│   ├── transform.py    # Cleans staff, dates, times and numbers into row dictionaries
│   └── load.py         # Stages rows and calls the database's ingest_batch function
├── queries.py          # Report queries; each returns a DataFrame, plus CLI print helpers
├── views.sql           # Database views behind the reports
├── app.py              # Command-line menu
├── web.py              # Web UI (Flask)
├── preview_dates.py    # Dry run: cleans the Excel files without touching the database
├── templates/          # HTML templates for the web UI
├── static/             # Stylesheet for the web UI
└── requirements.txt    # Project dependencies
```

## Prerequisites

- Python 3.9+
- PostgreSQL server running locally, with the `exact_recce` database, its tables, the `ingest_batch` function and the views from `views.sql`

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

## Configuration

- **Database:** `connections.py` connects to `exact_recce` on `localhost:5432` as user `Admin`. The password is requested in the terminal each time the app starts.
- **Reports folder:** set `FOLDER_PATH` in `etl/extract.py` to the folder that holds the weekly Excel reports.

## How to Run

Use the virtual environment's Python interpreter.

**Web UI** (opens in Chrome, or your default browser, after you enter the password):

```powershell
.\.venv\Scripts\python.exe web.py
```

Pages:

- **All outlets**: every outlet with its KDM, TMR and team lead
- **Activated in the last 2 weeks**: Nairobi outlets
- **Inactive for 2 weeks or more**: Nairobi outlets
- **TMR locations**: locations and outlets per TMR, with activation counts

The **Sync reports** button imports the Excel files, the same as option 1 in the CLI.

**Command-line menu:**

```powershell
.\.venv\Scripts\python.exe app.py
```

**Dry run** (cleans the Excel files and prints a summary per file, with no database changes):

```powershell
.\.venv\Scripts\python.exe preview_dates.py
```

## Notes on the Excel Data

- Dates arrive in mixed forms: real date cells, text written day-first or month-first, and cells holding several dates. `transform.py` reads all of these, corrects day/month swaps by comparing against the rest of the file, and keeps the latest date when a cell holds more than one. Anything it still cannot read is listed during the run.
- Keep one final copy of each weekly report in the reports folder. When copies differ, the one loaded last overwrites the others.
- Rows without an activation date are not imported as activations. They are held in the `import_review` table.
