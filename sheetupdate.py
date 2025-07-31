# sheetupdate.py

import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === CONFIG ===
credentials_path = r"D:\ShortsReelsAutomationTool\credentials.json"
google_sheet_key = "1Z3alm344GJcKaP7B6vGMU4oIINchhrmjZjX1iHBd4QM"

# === Setup Sheet Connection ===
def setup_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(google_sheet_key).sheet1
    return sheet

# === Get or Create Today's Column ===
def get_or_create_status_column(sheet):
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    headers = sheet.row_values(1)
    if today_str in headers:
        return headers.index(today_str) + 1
    else:
        sheet.update_cell(1, len(headers) + 1, today_str)
        return len(headers) + 1

# === Update Cell (Row = data row, Col = today's status col) ===
def update_status(sheet, row_index, col_index, status_text):
    sheet.update_cell(row_index, col_index, status_text)

# === Utility to Bulk Fetch Sheet Data ===
def get_sheet_data():
    sheet = setup_sheet()
    col_index = get_or_create_status_column(sheet)
    rows = sheet.get_all_values()[1:]  # skip header
    return sheet, col_index, rows
