from typing import Tuple, Optional, Dict, Any

# Predefined shift and project mappings for all employees.
# Format: username (normalized lowercase, no @) -> metadata dict
EMPLOYEE_DATA = {
    # Day Shift Employees
    "professor_noxx": {
        "name": "professor",
        "project": "un assigned",
        "shift_start": "09:30:00",
        "shift_end": "20:00:00",
        "shift_type": "day"
    },
    "shobana_0001": {
        "name": "SHOBANA",
        "project": "1",
        "shift_start": "08:30:00",
        "shift_end": "19:00:00",
        "shift_type": "day"
    },
    "reema_here": {
        "name": "REEMA",
        "project": "1",
        "shift_start": "09:30:00",
        "shift_end": "20:00:00",
        "shift_type": "day"
    },
    "zona_47": {
        "name": "ZONA",
        "project": "1",
        "shift_start": "08:30:00",
        "shift_end": "19:00:00",
        "shift_type": "day"
    },
    "brindha111": {
        "name": "BRINDHA",
        "project": "1",
        "shift_start": "08:30:00",
        "shift_end": "19:00:00",
        "shift_type": "day"
    },
    "anika9161": {
        "name": "ANIKA",
        "project": "2",
        "shift_start": "09:30:00",
        "shift_end": "20:00:00",
        "shift_type": "day"
    },
    "jeni0816": {
        "name": "JENI",
        "project": "2",
        "shift_start": "08:30:00",
        "shift_end": "19:00:00",
        "shift_type": "day"
    },
    "saranya_0812": {
        "name": "SARANYA",
        "project": "2",
        "shift_start": "08:30:00",
        "shift_end": "19:00:00",
        "shift_type": "day"
    },
    "agalya11": {
        "name": "AGALYA",
        "project": "2",
        "shift_start": "09:30:00",
        "shift_end": "20:00:00",
        "shift_type": "day"
    },
    "jesi2004": {
        "name": "JESIKA",
        "project": "2",
        "shift_start": "08:30:00",
        "shift_end": "19:00:00",
        "shift_type": "day"
    },
    "yuvashree97": {
        "name": "YUVASHREE",
        "project": "2",
        "shift_start": "08:30:00",
        "shift_end": "19:00:00",
        "shift_type": "day"
    },
    "rithika_srii": {
        "name": "RITHIKA",
        "project": "3",
        "shift_start": "08:30:00",
        "shift_end": "19:00:00",
        "shift_type": "day"
    },
    "preethii11": {
        "name": "PREETHI",
        "project": "3",
        "shift_start": "08:30:00",
        "shift_end": "19:00:00",
        "shift_type": "day"
    },
    "sindhu218": {
        "name": "SINDHU",
        "project": "3",
        "shift_start": "09:30:00",
        "shift_end": "20:00:00",
        "shift_type": "day"
    },
    "rehaa_n004": {
        "name": "REHAAN",
        "project": "3",
        "shift_start": "08:30:00",
        "shift_end": "20:30:00",
        "shift_type": "day"
    },
    "hathvika11": {
        "name": "HATHVIKA",
        "project": "3",
        "shift_start": "08:30:00",
        "shift_end": "20:30:00",
        "shift_type": "day"
    },
    "lava0828": {
        "name": "LAVANYA",
        "project": "4",
        "shift_start": "08:30:00",
        "shift_end": "20:30:00",
        "shift_type": "day"
    },
    "sahana1125": {
        "name": "SAHANA",
        "project": "4",
        "shift_start": "09:00:00",
        "shift_end": "19:30:00",
        "shift_type": "day"
    },
    "anu0504": {
        "name": "ANUSHA",
        "project": "4",
        "shift_start": "08:30:00",
        "shift_end": "19:00:00",
        "shift_type": "day"
    },
    "sanj439": {
        "name": "SANJANA",
        "project": "5",
        "shift_start": "08:30:00",
        "shift_end": "19:00:00",
        "shift_type": "day"
    },
    "pragathi_1007": {
        "name": "PRAGATHI",
        "project": "5",
        "shift_start": "08:30:00",
        "shift_end": "19:00:00",
        "shift_type": "day"
    },
    "abinaya_056": {
        "name": "ABINAYA",
        "project": "7",
        "shift_start": "08:30:00",
        "shift_end": "19:00:00",
        "shift_type": "day"
    },
    "a_ashmitha": {
        "name": "ASHMITHA",
        "project": "7",
        "shift_start": "10:00:00",
        "shift_end": "20:30:00",
        "shift_type": "day"
    },
    "shruthiii_s": {
        "name": "SHRUTHI",
        "project": "7",
        "shift_start": "10:00:00",
        "shift_end": "20:30:00",
        "shift_type": "day"
    },
    "riya211": {
        "name": "RIYA",
        "project": "8",
        "shift_start": "09:30:00",
        "shift_end": "20:00:00",
        "shift_type": "day"
    },
    "its_nila": {
        "name": "NILA",
        "project": "8",
        "shift_start": "09:30:00",
        "shift_end": "20:00:00",
        "shift_type": "day"
    },
    "shana02_19": {
        "name": "SHANA",
        "project": "Coinus",
        "shift_start": "09:30:00",
        "shift_end": "20:00:00",
        "shift_type": "day"
    },
    "sachin0_12": {
        "name": "SACHIN",
        "project": "Payment",
        "shift_start": "08:30:00",
        "shift_end": "20:30:00",
        "shift_type": "day"
    },
    "sarav_511": {
        "name": "SARAVANAN",
        "project": "Payment",
        "shift_start": "08:30:00",
        "shift_end": "20:30:00",
        "shift_type": "day"
    },
    "dev_11_01": {
        "name": "DEVA",
        "project": "Payment",
        "shift_start": "08:30:00",
        "shift_end": "20:30:00",
        "shift_type": "day"
    },
    "dheedhee05": {
        "name": "DHEE",
        "project": "Resource",
        "shift_start": "09:30:00",
        "shift_end": "20:00:00",
        "shift_type": "day"
    },
    "taraeditor1": {
        "name": "TARA",
        "project": "Resource",
        "shift_start": "09:00:00",
        "shift_end": "18:00:00",
        "shift_type": "day"
    },

    # Night Shift Employees
    "prithvi071": {
        "name": "PRITHVI",
        "project": "1",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "shiva2004_543": {
        "name": "SHIVA",
        "project": "1",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "aarav_010": {
        "name": "AARAV",
        "project": "1",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "aadhithya111": {
        "name": "AADHITHYA",
        "project": "2",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "akashjr18": {
        "name": "AKASH",
        "project": "2",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "pradeep2507": {
        "name": "PRADEEP",
        "project": "2",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "kabila025": {
        "name": "KABILAN",
        "project": "2",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "nithi_n007": {
        "name": "NITHIN",
        "project": "3",
        "shift_start": "20:00:00",
        "shift_end": "08:00:00",
        "shift_type": "night"
    },
    "suresh1193": {
        "name": "SURESH",
        "project": "3",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "vijay7001": {
        "name": "VIJAY",
        "project": "4",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "shan2727": {
        "name": "SHAN",
        "project": "4",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "rajesh7701": {
        "name": "RAJESH",
        "project": "4",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "jason000005": {
        "name": "JASON",
        "project": "5",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "ricky22551": {
        "name": "RICKY",
        "project": "7",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "kavish1236": {
        "name": "KAVISH",
        "project": "8",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "praveen_012": {
        "name": "PRAVEEN",
        "project": "Coinus",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "pugazh08_05": {
        "name": "PUGAZH",
        "project": "Payment",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "akilan_00": {
        "name": "AKILAN",
        "project": "Payment",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    },
    "rishi_toxic_00": {
        "name": "RISHI",
        "project": "Payment",
        "shift_start": "20:30:00",
        "shift_end": "08:30:00",
        "shift_type": "night"
    }
}

DEFAULT_SHIFT_START = "09:00:00"
DEFAULT_SHIFT_END = "18:00:00"

def get_employee_shift(username: Optional[str], db: Optional[Any] = None) -> Tuple[str, str]:
    """
    Cleans username and looks up shift timing parameters.
    Checks database first, then falls back to hardcoded EMPLOYEE_DATA.
    Pass an existing `db` (e.g. self.db from BotHandlerManager) so this reuses
    the already-open connection instead of opening (and leaking) a new one.
    Returns:
        (shift_start, shift_end) in 24h HH:MM:SS format
    """
    if not username:
        return DEFAULT_SHIFT_START, DEFAULT_SHIFT_END

    cleaned = username.strip().replace("@", "").lower()

    # Try database lookup first
    owns_connection = False
    try:
        if db is None:
            from database.sqlite_db import SQLiteDatabase
            import config
            db = SQLiteDatabase(config.DB_PATH)
            owns_connection = True
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT shift_start, shift_end FROM users WHERE LOWER(username) = ?", (cleaned,))
        row = cursor.fetchone()
        if row and row['shift_start'] and row['shift_end']:
            return row['shift_start'], row['shift_end']
    except Exception as e:
        print(f"⚠️ Error looking up shift from DB for {cleaned}: {e}")
    finally:
        if owns_connection:
            try:
                db.close()
            except Exception:
                pass

    # Fallback to EMPLOYEE_DATA dictionary
    data = EMPLOYEE_DATA.get(cleaned)
    if data:
        return data["shift_start"], data["shift_end"]
    return DEFAULT_SHIFT_START, DEFAULT_SHIFT_END
