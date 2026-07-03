import os
import json
from dotenv import load_dotenv
import pytz

# Load env variables from .env file
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Parse admin IDs list
admin_ids_raw = os.getenv("ADMIN_TELEGRAM_IDS", "")
ADMIN_TELEGRAM_IDS = []
for x in admin_ids_raw.split(","):
    x_clean = x.strip()
    if x_clean.isdigit():
        ADMIN_TELEGRAM_IDS.append(int(x_clean))

# Set up local timezone
TIMEZONE_STR = os.getenv("TIMEZONE", "Asia/Kolkata")
try:
    TIMEZONE = pytz.timezone(TIMEZONE_STR)
except Exception:
    TIMEZONE = pytz.timezone("UTC")

DB_PATH = os.getenv("DB_PATH", "attendance.db")

GOOGLE_SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID", "")
GOOGLE_SPREADSHEET_NAME = os.getenv("GOOGLE_SPREADSHEET_NAME", "Employee Attendance Systems")
GOOGLE_CREDS_FILE = os.getenv("GOOGLE_CREDS_FILE", "service_account.json")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON", "")

def get_google_credentials():
    """
    Returns credentials as a dict or path to credentials file.
    Favors GOOGLE_CREDS_JSON if provided, otherwise checks GOOGLE_CREDS_FILE.
    """
    if GOOGLE_CREDS_JSON:
        try:
            return json.loads(GOOGLE_CREDS_JSON)
        except json.JSONDecodeError as e:
            print(f"Error decoding GOOGLE_CREDS_JSON: {e}")
    
    if os.path.exists(GOOGLE_CREDS_FILE):
        return GOOGLE_CREDS_FILE
        
    return None
