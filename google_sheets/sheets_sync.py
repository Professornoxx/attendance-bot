import os
import gspread
from google.oauth2.service_account import Credentials
from typing import Optional, Dict, Any, List
import config

class GoogleSheetsSyncManager:
    """
    Handles real-time synchronization of attendance events to Google Sheets.
    Implements self-healing worksheets (auto-creates worksheets & headers).
    """

    HEADERS = ["Session ID", "Telegram ID", "Username", "Name", "Date", "Start Time", "End Time", "Duration", "Status"]

    SHEET_MAPPING = {
        "attendance": "Attendance Sessions",
        "break": "Break Sessions",
        "in_out": "In-Out Sessions"
    }

    def __init__(self) -> None:
        self.client: Optional[gspread.Client] = None
        self.spreadsheet: Optional[gspread.Spreadsheet] = None
        self.service_account_email: Optional[str] = None
        self.initialized = False

    def authenticate(self) -> bool:
        """Authenticate using credentials from config and open the spreadsheet."""
        try:
            creds_data = config.get_google_credentials()
            if not creds_data:
                print("⚠️ Google Sheets API Warning: No credentials found. Sheet sync will be disabled.")
                return False

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]

            if isinstance(creds_data, dict):
                # Authenticate via JSON string from environment variables
                creds = Credentials.from_service_account_info(creds_data, scopes=scopes)
                self.service_account_email = creds_data.get("client_email")
                self.client = gspread.authorize(creds)
            else:
                # Authenticate via credentials file path
                self.client = gspread.service_account(filename=creds_data)
                # Load email for logging
                import json
                with open(creds_data, 'r') as f:
                    file_creds = json.load(f)
                    self.service_account_email = file_creds.get("client_email")

            # Open Spreadsheet
            if config.GOOGLE_SPREADSHEET_ID:
                self.spreadsheet = self.client.open_by_key(config.GOOGLE_SPREADSHEET_ID)
            elif config.GOOGLE_SPREADSHEET_NAME:
                self.spreadsheet = self.client.open(config.GOOGLE_SPREADSHEET_NAME)
            else:
                print("⚠️ Google Sheets API Warning: Spreadsheet ID or name not configured.")
                return False

            print(f"✅ Google Sheets Connected: '{self.spreadsheet.title}'")
            print(f"ℹ️ Make sure to share your sheet with Service Account: {self.service_account_email}")
            self.initialize_worksheets()
            self.initialized = True
            return True

        except Exception as e:
            print(f"❌ Google Sheets Connection Error: {e}")
            if self.service_account_email:
                print(f"ℹ️ Hint: Check if the spreadsheet is shared with: {self.service_account_email}")
            return False

    def initialize_worksheets(self) -> None:
        """Create worksheets and headers if they do not exist."""
        if not self.spreadsheet:
            return

        existing_sheets = [ws.title for ws in self.spreadsheet.worksheets()]

        for key, sheet_title in self.SHEET_MAPPING.items():
            if sheet_title not in existing_sheets:
                print(f"📝 Worksheet '{sheet_title}' not found. Creating and writing headers...")
                worksheet = self.spreadsheet.add_worksheet(title=sheet_title, rows=1000, cols=len(self.HEADERS))
                worksheet.append_row(self.HEADERS)
                # Format headers to bold
                worksheet.format("A1:I1", {"textFormat": {"bold": True}})
            else:
                # Double check that headers exist
                worksheet = self.spreadsheet.worksheet(sheet_title)
                first_row = worksheet.row_values(1)
                if not first_row or first_row[0] != self.HEADERS[0]:
                    print(f"📝 Writing missing headers to '{sheet_title}'...")
                    worksheet.insert_row(self.HEADERS, 1)
                    worksheet.format("A1:I1", {"textFormat": {"bold": True}})

    def sync_session_start(self, session_type: str, session_id: Any, telegram_id: int, 
                           username: Optional[str], name: str, date_str: str, start_time_str: str) -> bool:
        """
        Sync the start of a session (Login, Break In, In) to Google Sheets.
        """
        if not self.initialized or not self.spreadsheet:
            return False

        sheet_title = self.SHEET_MAPPING.get(session_type)
        if not sheet_title:
            return False

        try:
            worksheet = self.spreadsheet.worksheet(sheet_title)
            # Prefix sheet session_id based on session_type for clarity (e.g. ATT-1, BRK-2, MOV-3)
            prefix = "ATT" if session_type == "attendance" else "BRK" if session_type == "break" else "MOV"
            unique_id = f"{prefix}-{session_id}"

            row_data = [
                unique_id,
                str(telegram_id),
                username or "",
                name,
                date_str,
                start_time_str,
                "", # End Time (empty initially)
                "", # Duration (empty initially)
                "active"
            ]
            worksheet.append_row(row_data)
            return True
        except Exception as e:
            print(f"❌ Error syncing start to sheet '{sheet_title}': {e}")
            return False

    def sync_session_end(self, session_type: str, session_id: Any, end_time_str: str, duration_str: str) -> bool:
        """
        Update Google Sheets when a session is closed (Logout, Break Out, Out).
        """
        if not self.initialized or not self.spreadsheet:
            return False

        sheet_title = self.SHEET_MAPPING.get(session_type)
        if not sheet_title:
            return False

        try:
            worksheet = self.spreadsheet.worksheet(sheet_title)
            prefix = "ATT" if session_type == "attendance" else "BRK" if session_type == "break" else "MOV"
            unique_id = f"{prefix}-{session_id}"

            # Retrieve all IDs from Column A to locate row
            col_ids = worksheet.col_values(1)
            if unique_id in col_ids:
                row_idx = col_ids.index(unique_id) + 1 # Convert to 1-based row index
                # We want to update End Time (Col 7 - G), Duration (Col 8 - H), and Status (Col 9 - I)
                worksheet.update(
                    range_name=f"G{row_idx}:I{row_idx}",
                    values=[[end_time_str, duration_str, "completed"]]
                )
                return True
            else:
                print(f"⚠️ Session ID '{unique_id}' not found in Google Sheet '{sheet_title}'.")
                return False
        except Exception as e:
            print(f"❌ Error syncing end to sheet '{sheet_title}': {e}")
            return False
