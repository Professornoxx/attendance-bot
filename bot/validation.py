from typing import Tuple, Optional, Dict, Any
from database.base import BaseDatabase
from datetime import datetime

def parse_time_to_seconds(time_str: str) -> int:
    """Helper to convert HH:MM:SS string to total seconds of the day."""
    try:
        parts = list(map(int, time_str.split(":")))
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            return parts[0] * 3600 + parts[1] * 60
    except (ValueError, TypeError):
        pass
    return 0

def calculate_time_difference(start_time: str, end_time: str) -> int:
    """Calculate the duration between two HH:MM:SS times on the same day in seconds."""
    start_sec = parse_time_to_seconds(start_time)
    end_sec = parse_time_to_seconds(end_time)
    # If end_time is earlier than start_time (e.g. overnight), wrap around 24 hours
    if end_sec < start_sec:
        return (24 * 3600 - start_sec) + end_sec
    return end_sec - start_sec

def auto_close_leftover_sessions(db: BaseDatabase, telegram_id: int, today_str: str, 
                                 sheets_sync_mgr=None) -> None:
    """
    Checks if there are active sessions from a previous day.
    If so, automatically closes them at 23:59:59 of their respective date.
    This prevents stale states and keeps durations correct.
    """
    # 1. Check Attendance
    active_att = db.get_active_attendance_session(telegram_id)
    if active_att and active_att["date"] != today_str:
        session_id = active_att["id"]
        login_time = active_att["login_time"]
        duration = calculate_time_difference(login_time, "23:59:59")
        db.update_attendance_session(session_id, "23:59:59", duration)
        print(f"🧹 Auto-closed leftover attendance session ID {session_id} for user {telegram_id} on date {active_att['date']}")
        if sheets_sync_mgr:
            sheets_sync_mgr.sync_session_end("attendance", session_id, "23:59:59", format_seconds_to_duration(duration))

    # 2. Check Break
    active_brk = db.get_active_break_session(telegram_id)
    if active_brk and active_brk["date"] != today_str:
        session_id = active_brk["id"]
        break_in = active_brk["break_in_time"]
        duration = calculate_time_difference(break_in, "23:59:59")
        db.update_break_session(session_id, "23:59:59", duration)
        print(f"🧹 Auto-closed leftover break session ID {session_id} for user {telegram_id} on date {active_brk['date']}")
        if sheets_sync_mgr:
            sheets_sync_mgr.sync_session_end("break", session_id, "23:59:59", format_seconds_to_duration(duration))

    # 3. Check Movements
    active_move = db.get_active_in_out_session(telegram_id)
    if active_move and active_move["date"] != today_str:
        session_id = active_move["id"]
        in_time = active_move["in_time"]
        duration = calculate_time_difference(in_time, "23:59:59")
        db.update_in_out_session(session_id, "23:59:59", duration)
        print(f"🧹 Auto-closed leftover movement session ID {session_id} for user {telegram_id} on date {active_move['date']}")
        if sheets_sync_mgr:
            sheets_sync_mgr.sync_session_end("in_out", session_id, "23:59:59", format_seconds_to_duration(duration))

def format_seconds_to_duration(seconds: int) -> str:
    """Format total seconds into HH:MM:SS representation."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

class AttendanceValidationEngine:
    """
    Enforces workflow states using active database entries.
    Prevents invalid transitions and returns diagnostic responses.
    """

    @staticmethod
    def validate(db: BaseDatabase, telegram_id: int, action: str, today_str: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Validates whether the requested action is legal for the employee.
        Returns:
            (is_valid, error_message, context_dict)
        """
        # Retrieve user profile
        user = db.get_user(telegram_id)
        if not user:
            return False, "⚠️ You are not registered. Please send /start to register first.", None

        # Block banned users from all actions
        if user.get("status") == "banned":
            allowance_minutes = user.get("break_allowance") or 65
            return False, (
                f"🚫 *You are BANNED from using this system.*\n\n"
                f"Reason: You have exceeded the maximum allowed combined break and field movement time of *{allowance_minutes} minutes* today.\n\n"
                f"Please contact your administrator."
            ), None

        # Fetch active states
        active_att = db.get_active_attendance_session(telegram_id)
        active_brk = db.get_active_break_session(telegram_id)
        active_move = db.get_active_in_out_session(telegram_id)

        context = {
            "user": user,
            "active_attendance": active_att,
            "active_break": active_brk,
            "active_in_out": active_move
        }

        # Enforce validation rules
        if action == "login":
            if active_att:
                return False, "⚠️ Invalid Action: You are already Logged In! (No active sign-out found)", context
            return True, None, context

        elif action == "logout":
            if not active_att:
                return False, "⚠️ Invalid Action: You cannot Log Out before Logging In first!", context
            if active_brk:
                return False, "⚠️ Invalid Action: Please end your Lunch Break (Lunch In.) before Logging Out!", context
            if active_move:
                return False, "⚠️ Invalid Action: Please end your field movement (Out) before Logging Out!", context
            return True, None, context

        elif action == "break_in":
            if not active_att:
                return False, "⚠️ Invalid Action: You cannot take a Lunch Break before Logging In!", context
            if active_brk:
                return False, "⚠️ Invalid Action: You are already on a Lunch Break!", context
            if active_move:
                return False, "⚠️ Invalid Action: You cannot start a Lunch Break while on a field movement!", context
            return True, None, context

        elif action == "break_out":
            if not active_brk:
                return False, "⚠️ Invalid Action: You are not currently on a Lunch Break!", context
            return True, None, context

        elif action == "in":  # Start Movement
            if not active_att:
                return False, "⚠️ Invalid Action: You cannot start a field visit before Logging In!", context
            if active_brk:
                return False, "⚠️ Invalid Action: You cannot start a field visit while on a Lunch Break!", context
            if active_move:
                return False, "⚠️ Invalid Action: You are already on an active field visit!", context
            return True, None, context

        elif action == "out":  # End Movement
            if not active_move:
                return False, "⚠️ Invalid Action: You do not have an active field visit to end (No In record found)!", context
            return True, None, context

        return False, "⚠️ Unknown action requested.", None
