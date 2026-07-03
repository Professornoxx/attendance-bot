import sqlite3
import os
import threading
from typing import List, Dict, Any, Optional
from .base import BaseDatabase

class SQLiteDatabase(BaseDatabase):
    """
    SQLite implementation of the BaseDatabase adapter.
    Uses sqlite3 with dict-like row factories for clean key-value returns.
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._migrations_run = False
        self._lock = threading.Lock()

    @property
    def conn(self) -> Optional[sqlite3.Connection]:
        return getattr(self._local, 'conn', None)

    @conn.setter
    def conn(self, value: Optional[sqlite3.Connection]) -> None:
        self._local.conn = value

    def connect(self) -> sqlite3.Connection:
        if not self.conn:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # Enforce constraints like Foreign Keys in SQLite
            conn.execute("PRAGMA foreign_keys = ON;")
            self._local.conn = conn
            
            with self._lock:
                if not self._migrations_run:
                    self._run_migrations()
                    self._migrations_run = True
        return self.conn


    def _run_migrations(self) -> None:
        """Self-healing migration: adds new columns if they don't exist."""
        if not self.conn:
            return
        cursor = self.conn.cursor()

        # Base tables aren't created yet (fresh DB before schema.sql has run).
        # execute_schema() re-invokes this once the tables exist, so skip quietly.
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            return

        # 1. Migrate users table
        cursor.execute("PRAGMA table_info(users)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        migrations = [
            ("shift_start", "ALTER TABLE users ADD COLUMN shift_start VARCHAR(50)"),
            ("shift_end",   "ALTER TABLE users ADD COLUMN shift_end VARCHAR(50)"),
            ("status",      "ALTER TABLE users ADD COLUMN status VARCHAR(50) NOT NULL DEFAULT 'active'"),
            ("employee_id", "ALTER TABLE users ADD COLUMN employee_id VARCHAR(100)"),
            ("project",     "ALTER TABLE users ADD COLUMN project VARCHAR(100)"),
            ("shift_type",  "ALTER TABLE users ADD COLUMN shift_type VARCHAR(50) DEFAULT 'day'"),
            ("break_allowance", "ALTER TABLE users ADD COLUMN break_allowance INTEGER DEFAULT 65"),
            ("attendance_settings", "ALTER TABLE users ADD COLUMN attendance_settings TEXT"),
        ]
        for col_name, ddl in migrations:
            if col_name not in existing_columns:
                try:
                    self.conn.execute(ddl)
                    self.conn.commit()
                    print(f"✅ Migration: Added column '{col_name}' to users table.")
                except sqlite3.Error as e:
                    print(f"⚠️ Migration warning for '{col_name}': {e}")

        # Create unique index for employee_id
        try:
            self.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_employee_id ON users(employee_id) WHERE employee_id IS NOT NULL;")
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"⚠️ Migration index warning for employee_id: {e}")

        # 2. Migrate attendance_sessions table
        cursor.execute("PRAGMA table_info(attendance_sessions)")
        existing_att_columns = {row[1] for row in cursor.fetchall()}
        att_migrations = [
            ("is_half_day",   "ALTER TABLE attendance_sessions ADD COLUMN is_half_day INTEGER DEFAULT 0"),
            ("fine_applied",  "ALTER TABLE attendance_sessions ADD COLUMN fine_applied INTEGER DEFAULT 0"),
            ("fine_amount",   "ALTER TABLE attendance_sessions ADD COLUMN fine_amount REAL DEFAULT 0.0"),
            ("fine_reason",   "ALTER TABLE attendance_sessions ADD COLUMN fine_reason VARCHAR(255)"),
        ]
        for col_name, ddl in att_migrations:
            if col_name not in existing_att_columns:
                try:
                    self.conn.execute(ddl)
                    self.conn.commit()
                    print(f"✅ Migration: Added column '{col_name}' to attendance_sessions table.")
                except sqlite3.Error as e:
                    print(f"⚠️ Migration warning for '{col_name}' in attendance_sessions: {e}")

        # 3. Auto-create permission_requests table if missing (self-healing)
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='permission_requests'"
        )
        if not cursor.fetchone():
            try:
                self.conn.executescript("""
                    CREATE TABLE IF NOT EXISTS permission_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER NOT NULL,
                        username VARCHAR(255),
                        name VARCHAR(255) NOT NULL,
                        date VARCHAR(10) NOT NULL,
                        request_type VARCHAR(50) NOT NULL,
                        start_time VARCHAR(8) NOT NULL,
                        end_time VARCHAR(8) NOT NULL,
                        duration_seconds INTEGER DEFAULT 0,
                        reason VARCHAR(1000) NOT NULL,
                        status VARCHAR(20) DEFAULT 'pending',
                        approver_id INTEGER,
                        approver_name VARCHAR(255),
                        decided_at TIMESTAMP,
                        notification_status VARCHAR(50) DEFAULT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_perm_lookup ON permission_requests(telegram_id, date);
                    CREATE INDEX IF NOT EXISTS idx_perm_status ON permission_requests(status);
                """)
                self.conn.commit()
                print("✅ Migration: Created 'permission_requests' table.")
            except Exception as e:
                print(f"⚠️ Migration warning for permission_requests: {e}")

        # 4. Migrate permission_requests table (add notification_status if missing)
        cursor.execute("PRAGMA table_info(permission_requests)")
        existing_perm_columns = {row[1] for row in cursor.fetchall()}
        if existing_perm_columns and "notification_status" not in existing_perm_columns:
            try:
                self.conn.execute("ALTER TABLE permission_requests ADD COLUMN notification_status VARCHAR(50) DEFAULT NULL")
                self.conn.commit()
                print("✅ Migration: Added column 'notification_status' to permission_requests table.")
            except sqlite3.Error as e:
                print(f"⚠️ Migration warning for 'notification_status' in permission_requests: {e}")

        # 5. Clean up existing users' names and projects from EMPLOYEE_DATA fallback
        try:
            from bot.shifts import EMPLOYEE_DATA
            cursor.execute("SELECT telegram_id, username, full_name, project, shift_type, shift_start, shift_end FROM users")
            users_list = cursor.fetchall()
            bad_names = {
                "login.", "login", "log in", "logout.", "logout", "log out", 
                "break out.", "break out", "breakin.", "break in.", "break in", 
                "break in ☕", "out.", "out", "in.", "in", "login 🟢",
                "lunch out.", "lunch out", "lunchin.", "lunch in.", "lunch in"
            }
            for u in users_list:
                uname = u['username']
                if not uname:
                    continue
                uname_lower = uname.lower()
                meta = EMPLOYEE_DATA.get(uname_lower)
                if meta:
                    updates = []
                    params = []
                    
                    # Clean full_name if bad name
                    curr_name = u['full_name']
                    if not curr_name or curr_name.strip().lower() in bad_names:
                        updates.append("full_name = ?")
                        params.append(meta['name'])
                        
                    # Fix project if NULL/empty
                    if not u['project']:
                        updates.append("project = ?")
                        params.append(meta['project'])
                        
                    # Fix shift_type if NULL/empty
                    if not u['shift_type']:
                        updates.append("shift_type = ?")
                        params.append(meta['shift_type'])

                    # Fix shift times if NULL/empty
                    if not u['shift_start']:
                        updates.append("shift_start = ?")
                        params.append(meta['shift_start'])
                    if not u['shift_end']:
                        updates.append("shift_end = ?")
                        params.append(meta['shift_end'])

                    if updates:
                        params.append(u['telegram_id'])
                        cursor.execute(
                            f"UPDATE users SET {', '.join(updates)} WHERE telegram_id = ?",
                            tuple(params)
                        )
            self.conn.commit()
            print("✅ Migration: Cleaned up existing users with EMPLOYEE_DATA.")
        except Exception as e:
            print(f"⚠️ Migration warning during user cleanup: {e}")


    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def execute_schema(self, schema_file: str) -> None:
        if not os.path.exists(schema_file):
            raise FileNotFoundError(f"Schema SQL file not found at {schema_file}")
        
        with open(schema_file, 'r') as f:
            schema_sql = f.read()
            
        conn = self.connect()
        try:
            conn.executescript(schema_sql)
            conn.commit()
            # Run migrations AFTER tables are created to add any new columns
            self._run_migrations()
        except sqlite3.Error as e:
            conn.rollback()
            raise e

    # --- User Management ---
    def register_user(self, telegram_id: int, username: Optional[str], full_name: str,
                      role: str = 'employee', shift_start: Optional[str] = None,
                      shift_end: Optional[str] = None) -> bool:
        conn = self.connect()
        
        # Look up from EMPLOYEE_DATA fallback
        from bot.shifts import EMPLOYEE_DATA
        uname_lower = username.lower() if username else ""
        meta = EMPLOYEE_DATA.get(uname_lower) if uname_lower else None
        
        project = None
        shift_type = 'day'
        
        bad_names = {
            "login.", "login", "log in", "logout.", "logout", "log out", 
            "break out.", "break out", "breakin.", "break in.", "break in", 
            "break in ☕", "out.", "out", "in.", "in", "login 🟢",
            "lunch out.", "lunch out", "lunchin.", "lunch in.", "lunch in"
        }
        
        if meta:
            if not shift_start:
                shift_start = meta.get("shift_start")
            if not shift_end:
                shift_end = meta.get("shift_end")
            project = meta.get("project")
            shift_type = meta.get("shift_type", "day")
            if not full_name or full_name.strip().lower() in bad_names:
                full_name = meta.get("name") or full_name

        try:
            conn.execute(
                """
                INSERT INTO users (telegram_id, username, full_name, role, shift_start, shift_end, status, project, shift_type)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username=excluded.username,
                    full_name=excluded.full_name,
                    role=excluded.role,
                    shift_start=COALESCE(excluded.shift_start, shift_start),
                    shift_end=COALESCE(excluded.shift_end, shift_end),
                    project=COALESCE(excluded.project, project),
                    shift_type=COALESCE(excluded.shift_type, shift_type)
                """,
                (telegram_id, username, full_name, role, shift_start, shift_end, project, shift_type)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite register_user Error: {e}")
            conn.rollback()
            return False

    def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_users(self) -> List[Dict[str, Any]]:
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY registered_at DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def update_user_status(self, telegram_id: int, status: str) -> bool:
        conn = self.connect()
        try:
            conn.execute(
                "UPDATE users SET status = ? WHERE telegram_id = ?",
                (status, telegram_id)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite update_user_status Error: {e}")
            conn.rollback()
            return False

    # --- Attendance Sessions (Login/Logout) ---
    def create_attendance_session(self, telegram_id: int, username: Optional[str], name: str, date: str, login_time: str) -> int:
        conn = self.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO attendance_sessions (telegram_id, username, name, date, login_time, status)
                VALUES (?, ?, ?, ?, ?, 'active')
                """,
                (telegram_id, username, name, date, login_time)
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            print(f"SQLite create_attendance_session Error: {e}")
            conn.rollback()
            raise e

    def update_attendance_session(self, session_id: int, logout_time: str, duration: int, is_half_day: int = 0) -> bool:
        conn = self.connect()
        try:
            conn.execute(
                """
                UPDATE attendance_sessions
                SET logout_time = ?, duration = ?, status = 'completed', is_half_day = ?
                WHERE id = ?
                """,
                (logout_time, duration, is_half_day, session_id)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite update_attendance_session Error: {e}")
            conn.rollback()
            return False

    def get_active_attendance_session(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM attendance_sessions 
            WHERE telegram_id = ? AND status = 'active'
            ORDER BY id DESC LIMIT 1
            """,
            (telegram_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_attendance_sessions_by_date(self, telegram_id: int, date: str) -> List[Dict[str, Any]]:
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM attendance_sessions 
            WHERE telegram_id = ? AND date = ?
            ORDER BY login_time ASC
            """,
            (telegram_id, date)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # --- Break Sessions (Break In/Break Out) ---
    def create_break_session(self, telegram_id: int, username: Optional[str], name: str, date: str, break_in_time: str) -> int:
        conn = self.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO break_sessions (telegram_id, username, name, date, break_in_time, status)
                VALUES (?, ?, ?, ?, ?, 'active')
                """,
                (telegram_id, username, name, date, break_in_time)
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            print(f"SQLite create_break_session Error: {e}")
            conn.rollback()
            raise e

    def update_break_session(self, session_id: int, break_out_time: str, duration: int) -> bool:
        conn = self.connect()
        try:
            conn.execute(
                """
                UPDATE break_sessions
                SET break_out_time = ?, duration = ?, status = 'completed'
                WHERE id = ?
                """,
                (break_out_time, duration, session_id)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite update_break_session Error: {e}")
            conn.rollback()
            return False

    def get_active_break_session(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM break_sessions 
            WHERE telegram_id = ? AND status = 'active'
            ORDER BY id DESC LIMIT 1
            """,
            (telegram_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_break_sessions_by_date(self, telegram_id: int, date: str) -> List[Dict[str, Any]]:
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM break_sessions 
            WHERE telegram_id = ? AND date = ?
            ORDER BY break_in_time ASC
            """,
            (telegram_id, date)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # --- Movement Sessions (In/Out) ---
    def create_in_out_session(self, telegram_id: int, username: Optional[str], name: str, date: str, in_time: str) -> int:
        conn = self.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO in_out_sessions (telegram_id, username, name, date, in_time, status)
                VALUES (?, ?, ?, ?, ?, 'active')
                """,
                (telegram_id, username, name, date, in_time)
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            print(f"SQLite create_in_out_session Error: {e}")
            conn.rollback()
            raise e

    def update_in_out_session(self, session_id: int, out_time: str, duration: int) -> bool:
        conn = self.connect()
        try:
            conn.execute(
                """
                UPDATE in_out_sessions
                SET out_time = ?, duration = ?, status = 'completed'
                WHERE id = ?
                """,
                (out_time, duration, session_id)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite update_in_out_session Error: {e}")
            conn.rollback()
            return False

    def get_active_in_out_session(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM in_out_sessions 
            WHERE telegram_id = ? AND status = 'active'
            ORDER BY id DESC LIMIT 1
            """,
            (telegram_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_in_out_sessions_by_date(self, telegram_id: int, date: str) -> List[Dict[str, Any]]:
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM in_out_sessions 
            WHERE telegram_id = ? AND date = ?
            ORDER BY in_time ASC
            """,
            (telegram_id, date)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # --- Early Logout Requests ---
    def create_early_logout_request(self, telegram_id: int, username: Optional[str], name: str, date: str, logout_time: str, reason: str) -> int:
        conn = self.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO early_logout_requests (telegram_id, username, name, date, logout_time, reason, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (telegram_id, username, name, date, logout_time, reason)
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            print(f"SQLite create_early_logout_request Error: {e}")
            conn.rollback()
            raise e

    def get_early_logout_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM early_logout_requests WHERE id = ?", (request_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_early_logout_request_by_date(self, telegram_id: int, date: str) -> Optional[Dict[str, Any]]:
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM early_logout_requests WHERE telegram_id = ? AND date = ? ORDER BY id DESC LIMIT 1",
            (telegram_id, date)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_early_logout_requests(self) -> List[Dict[str, Any]]:
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM early_logout_requests ORDER BY id DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def update_early_logout_request_status(self, request_id: int, status: str) -> bool:
        conn = self.connect()
        try:
            import datetime
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "UPDATE early_logout_requests SET status = ?, reviewed_at = ? WHERE id = ?",
                (status, now_str, request_id)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite update_early_logout_request_status Error: {e}")
            conn.rollback()
            return False

    def set_attendance_half_day(self, telegram_id: int, date: str, is_half_day: int) -> bool:
        conn = self.connect()
        try:
            conn.execute(
                "UPDATE attendance_sessions SET is_half_day = ? WHERE telegram_id = ? AND date = ?",
                (is_half_day, telegram_id, date)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite set_attendance_half_day Error: {e}")
            conn.rollback()
            return False

    # --- Fine Management ---
    def set_attendance_fine(self, session_id: int, fine_applied: int, fine_amount: float, fine_reason: Optional[str]) -> bool:
        conn = self.connect()
        try:
            conn.execute(
                """
                UPDATE attendance_sessions 
                SET fine_applied = ?, fine_amount = ?, fine_reason = ? 
                WHERE id = ?
                """,
                (fine_applied, fine_amount, fine_reason, session_id)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite set_attendance_fine Error: {e}")
            conn.rollback()
            return False

    def create_fine(self, telegram_id: int, date: str, amount: float, reason: Optional[str]) -> bool:
        conn = self.connect()
        try:
            conn.execute(
                """
                INSERT INTO fines (telegram_id, date, amount, reason)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_id, date) DO UPDATE SET
                    amount = excluded.amount,
                    reason = excluded.reason
                """,
                (telegram_id, date, amount, reason)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite create_fine Error: {e}")
            conn.rollback()
            return False

    def delete_fine(self, telegram_id: int, date: str) -> bool:
        conn = self.connect()
        try:
            conn.execute(
                "DELETE FROM fines WHERE telegram_id = ? AND date = ?",
                (telegram_id, date)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite delete_fine Error: {e}")
            conn.rollback()
            return False

    def get_fines_by_employee(self, telegram_id: int) -> List[Dict[str, Any]]:
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fines WHERE telegram_id = ? ORDER BY date DESC", (telegram_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_all_fines(self) -> List[Dict[str, Any]]:
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fines ORDER BY date DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # --- Permission Requests ---
    def create_permission_request(
        self, telegram_id: int, username: Optional[str], name: str,
        date: str, request_type: str, start_time: str, end_time: str,
        duration_seconds: int, reason: str
    ) -> int:
        """Create a new permission request. Returns the new row ID."""
        conn = self.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO permission_requests
                    (telegram_id, username, name, date, request_type,
                     start_time, end_time, duration_seconds, reason, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (telegram_id, username, name, date, request_type,
                 start_time, end_time, duration_seconds, reason)
            )
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print(f"SQLite create_permission_request Error: {e}")
            conn.rollback()
            raise e

    def get_permission_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single permission request by ID."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM permission_requests WHERE id = ?", (request_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_permission_requests_by_date(self, telegram_id: int, date: str) -> List[Dict[str, Any]]:
        """Fetch all permission requests for an employee on a specific date."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM permission_requests WHERE telegram_id = ? AND date = ? ORDER BY id ASC",
            (telegram_id, date)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_approved_permission_seconds(self, telegram_id: int, date: str) -> int:
        """Returns total approved permission duration (seconds) for an employee on a date."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SUM(duration_seconds) FROM permission_requests "
            "WHERE telegram_id = ? AND date = ? AND status = 'approved'",
            (telegram_id, date)
        )
        row = cursor.fetchone()
        return row[0] or 0

    def get_all_permission_requests(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all permission requests, optionally filtered by status."""
        conn = self.connect()
        cursor = conn.cursor()
        if status:
            cursor.execute(
                "SELECT * FROM permission_requests WHERE status = ? ORDER BY id DESC",
                (status,)
            )
        else:
            cursor.execute("SELECT * FROM permission_requests ORDER BY id DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def update_permission_request_status(
        self, request_id: int, status: str,
        approver_id: Optional[int] = None, approver_name: Optional[str] = None
    ) -> bool:
        """Update a permission request's decision (approve/reject) with approver info."""
        conn = self.connect()
        try:
            import datetime as _dt
            now_str = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                UPDATE permission_requests
                SET status = ?, approver_id = ?, approver_name = ?, decided_at = ?
                WHERE id = ?
                """,
                (status, approver_id, approver_name, now_str, request_id)
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"SQLite update_permission_request_status Error: {e}")
            conn.rollback()
            return False

    def update_permission_notification_status(self, request_id: int, status: str) -> bool:
        """Update the Telegram notification status ('sent', 'failed') for a request."""
        conn = self.connect()
        try:
            conn.execute(
                "UPDATE permission_requests SET notification_status = ? WHERE id = ?",
                (status, request_id)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite update_permission_notification_status Error: {e}")
            conn.rollback()
            return False

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Fetch a single user by Telegram username (case-insensitive, normalized)."""
        if not username:
            return None
        cleaned = username.strip().replace("@", "").lower()
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE LOWER(username) = ?", (cleaned,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_telegram_id_for_username(self, username: str, telegram_id: int) -> bool:
        """Update a user's Telegram ID based on their username."""
        if not username:
            return False
        cleaned = username.strip().replace("@", "").lower()
        conn = self.connect()
        try:
            conn.execute(
                "UPDATE users SET telegram_id = ? WHERE LOWER(username) = ?",
                (telegram_id, cleaned)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite update_telegram_id_for_username Error: {e}")
            conn.rollback()
            return False

    def create_staff_user(self, telegram_id: int, username: Optional[str], full_name: str,
                          employee_id: Optional[str], project: Optional[str], shift_type: str,
                          shift_start: str, shift_end: str, break_allowance: int = 65,
                          attendance_settings: Optional[str] = None) -> bool:
        """Create a new staff user record with all details."""
        conn = self.connect()
        # Clean username
        cleaned_username = username.strip().replace("@", "") if username else None
        try:
            conn.execute(
                """
                INSERT INTO users (telegram_id, username, full_name, role, shift_start, shift_end, status,
                                   employee_id, project, shift_type, break_allowance, attendance_settings)
                VALUES (?, ?, ?, 'employee', ?, ?, 'active', ?, ?, ?, ?, ?)
                """,
                (telegram_id, cleaned_username, full_name, shift_start, shift_end,
                 employee_id, project, shift_type, break_allowance, attendance_settings)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite create_staff_user Error: {e}")
            conn.rollback()
            return False

    def update_staff_user(self, telegram_id: int, username: Optional[str], full_name: str,
                          employee_id: Optional[str], project: Optional[str], shift_type: str,
                          shift_start: str, shift_end: str, break_allowance: int = 65,
                          attendance_settings: Optional[str] = None, status: str = 'active') -> bool:
        """Update an existing staff user record."""
        conn = self.connect()
        cleaned_username = username.strip().replace("@", "") if username else None
        try:
            conn.execute(
                """
                UPDATE users
                SET username = ?, full_name = ?, shift_start = ?, shift_end = ?, status = ?,
                    employee_id = ?, project = ?, shift_type = ?, break_allowance = ?, attendance_settings = ?
                WHERE telegram_id = ?
                """,
                (cleaned_username, full_name, shift_start, shift_end, status,
                 employee_id, project, shift_type, break_allowance, attendance_settings, telegram_id)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite update_staff_user Error: {e}")
            conn.rollback()
            return False

    def delete_user(self, telegram_id: int) -> bool:
        """Delete user record (SQLite ON DELETE CASCADE will handle removing linked records)."""
        conn = self.connect()
        try:
            conn.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite delete_user Error: {e}")
            conn.rollback()
            return False

    def update_telegram_id(self, old_telegram_id: int, new_telegram_id: int) -> bool:
        """Update a user's Telegram ID across users and all referencing tables safely."""
        if old_telegram_id == new_telegram_id:
            return True
        conn = self.connect()
        cursor = conn.cursor()
        try:
            # Check if new_telegram_id is already taken
            cursor.execute("SELECT 1 FROM users WHERE telegram_id = ?", (new_telegram_id,))
            if cursor.fetchone():
                return False  # Already exists
                
            cursor.execute("PRAGMA foreign_keys = OFF;")
            
            # List of all tables that contain telegram_id
            tables = [
                "users", "attendance_sessions", "break_sessions", 
                "in_out_sessions", "early_logout_requests", "fines", "permission_requests"
            ]
            for t in tables:
                cursor.execute(f"UPDATE {t} SET telegram_id = ? WHERE telegram_id = ?", (new_telegram_id, old_telegram_id))
                
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"SQLite update_telegram_id Error: {e}")
            conn.rollback()
            return False
        finally:
            try:
                cursor.execute("PRAGMA foreign_keys = ON;")
            except:
                pass

