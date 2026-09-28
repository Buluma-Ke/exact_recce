# Beverage Recce Database CLI

A modular Python command-line tool for parsing, cleaning, and ingesting beverage recce reports from Excel into a PostgreSQL database, complete with advanced analytical reporting.

## Project Structure

```text
excat_experience/
├── connections.py      # Database engine initialization
├── etl/
│   └── ingest.py       # Excel folder scanning, data cleaning, and upserts
├── queries.py          # Analytical reports and SQL window functions
├── app.py              # Main CLI execution loop
└── requirements.txt    # Project dependencies
```


## Prerequisites
- Python 3.8+
- PostgreSQL Server running locally

## Installation & Setup

1.  Clone the repository and navigate to the project folder:
    `Bash`
     `cd exact_experience`

2.  Create and activate a virtual environment:
    `Bash`
    `python -m venv .venv`
    `.\.venv\Scripts\Activate.ps1   # On Windows PowerShell`
3.  Install dependancies
    `Bash`
    `pip install -r requirements.txt`

## How to run
Execute the application using the virtual environment's python interpreter:
    `PowerShell`
    `.\.venv\Scripts\python.exe app.py`
