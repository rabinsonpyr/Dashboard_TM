"""
Configuration for the cloud-hosted dashboard.
Column names below — edit if your Excel headers differ.
GOOGLE_DRIVE_FILE_ID and APP_PASSWORD are read from Streamlit Cloud's
"Secrets" settings (see README.md) — never hardcode them here.
"""

import streamlit as st

# Expected column names in the Excel file — MUST match your file's headers exactly.
COL_DATE = "Date"
COL_SALES = "Tillty"
COL_WOLT = "Wolt"
COL_UBEREATS = "UberEats"
COL_TOTAL = "Total Sales"
COL_TIPS = "Tips"
COL_PERSON = "Person"
COL_CASH = "Cash"

CURRENCY = "DKK"

# How often the app re-fetches the file from Google Drive (seconds).
# Lower = fresher data but more requests to Drive. 60s is a good default.
REFRESH_SECONDS = 60


def get_secret(name: str, default=None):
    """Read a value from Streamlit Cloud secrets, with a friendly fallback for local testing."""
    try:
        return st.secrets[name]
    except (KeyError, FileNotFoundError):
        return default


GOOGLE_DRIVE_FILE_ID = get_secret("GOOGLE_DRIVE_FILE_ID", "")
APP_PASSWORD = get_secret("APP_PASSWORD", "")
SERVICE_ACCOUNT_INFO = get_secret("gcp_service_account", None)
