from typing import Dict, Any, List, Optional
from database.base import BaseDatabase
from datetime import datetime
import config

def get_current_local_time() -> datetime:
    """Returns the current datetime in the configured timezone."""
    return datetime.now(config.TIMEZONE)

def get_current_time_str() -> str:
    """Returns HH:MM:SS format of current local time."""
    return get_current_local_time().strftime("%H:%M:%S")

def get_current_date_str() -> str:
    """Returns YYYY-MM-DD format of current local date."""
    return get_current_local_time().strftime("%Y-%m-%d")

def time_to_seconds(time_str: str) -> int:
    """Convert HH:MM:SS time string to total seconds since midnight."""
    try:
        parts = list(map(int, time_str.split(":")))
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            return parts[0] * 3600 + parts[1] * 60
    except (ValueError, TypeError):
        pass
    return 0

def format_seconds(seconds: int) -> str:
    """Format total seconds to HH:MM:SS string. Handles negative seconds safely."""
    is_negative = seconds < 0
    abs_seconds = abs(seconds)
    hours = abs_seconds // 3600
    minutes = (abs_seconds % 3600) // 60
    secs = abs_seconds % 60
    sign = "-" if is_negative else ""
    return f"{sign}{hours:02d}:{minutes:02d}:{secs:02d}"

def calculate_time_diff_seconds(start_time: str, end_time: str) -> int:
    """Calculate difference between start_time and end_time (HH:MM:SS) in seconds."""
    start_sec = time_to_seconds(start_time)
    end_sec = time_to_seconds(end_time)
    if end_sec < start_sec:
        # Wrap around 24 hours (overnight shifts)
        return (24 * 3600 - start_sec) + end_sec
    return end_sec - start_sec

def get_shift_break_allowance(shift_start: str, shift_end: str, db_allowance: int) -> int:
    """
    Returns the effective break allowance in minutes for an employee.
    - Night shift employees get 75 min by default.
    - Day shift employees get 65 min by default.
    - Any custom DB value that differs from the old 65-min default is always honoured.
    """
    if db_allowance and db_allowance != 65:
        return db_allowance

    try:
        start_hour = int(shift_start.split(":")[0])
        is_night = start_hour >= 18 or start_hour <= 6
    except Exception:
        is_night = False

    return 75 if is_night else 65

class AttendanceReporter:
    """
    Reporting Engine to aggregate working durations, break summaries,
    movements, and compute net working hours.
    """

    @staticmethod
    def get_employee_daily_summary(db: BaseDatabase, telegram_id: int, date_str: str) -> Dict[str, Any]:
        """
        Calculates daily attendance metrics for an employee on a specific date.
        If a session is active, it calculates duration dynamically up to the current time.
        """
        now_str = get_current_time_str()
        is_today = (date_str == get_current_date_str())

        # Retrieve all sessions of the day
        att_sessions = db.get_attendance_sessions_by_date(telegram_id, date_str)
        brk_sessions = db.get_break_sessions_by_date(telegram_id, date_str)
        move_sessions = db.get_in_out_sessions_by_date(telegram_id, date_str)

        # 1. Login/Logout Times
        login_time = "N/A"
        logout_time = "N/A"
        
        if att_sessions:
            login_time = att_sessions[0]["login_time"]
            last_sess = att_sessions[-1]
            if last_sess["status"] == "active":
                logout_time = "Active (Logged In)"
            else:
                logout_time = last_sess["logout_time"] or "N/A"

        # 2. Total Login Duration
        total_login_seconds = 0
        for sess in att_sessions:
            if sess["status"] == "active":
                if is_today:
                    total_login_seconds += calculate_time_diff_seconds(sess["login_time"], now_str)
                else:
                    # If looking at a past day, count until end of day (23:59:59)
                    total_login_seconds += calculate_time_diff_seconds(sess["login_time"], "23:59:59")
            else:
                total_login_seconds += sess["duration"] or 0

        # 3. Lunch Break Duration
        lunch_break_seconds = 0
        for sess in brk_sessions:
            if sess["status"] == "active":
                if is_today:
                    lunch_break_seconds += calculate_time_diff_seconds(sess["break_in_time"], now_str)
                else:
                    lunch_break_seconds += calculate_time_diff_seconds(sess["break_in_time"], "23:59:59")
            else:
                lunch_break_seconds += sess["duration"] or 0

        # 4. Total Movement (In-Out) Duration
        total_move_seconds = 0
        for sess in move_sessions:
            if sess["status"] == "active":
                if is_today:
                    total_move_seconds += calculate_time_diff_seconds(sess["in_time"], now_str)
                else:
                    total_move_seconds += calculate_time_diff_seconds(sess["in_time"], "23:59:59")
            else:
                total_move_seconds += sess["duration"] or 0

        # Total Break Duration is Lunch break + In/Out session break
        total_break_seconds = lunch_break_seconds + total_move_seconds

        # 5. Net Working Hours (Total Login Duration - Total Break Duration)
        net_working_seconds = total_login_seconds - total_break_seconds
        if net_working_seconds < 0:
            net_working_seconds = 0

        # 6. Automatically apply or revoke break-limit fines
        if login_time != "N/A" and att_sessions:
            # Load user break allowance from database
            db_user = db.get_user(telegram_id)
            raw_db_allowance = (db_user.get("break_allowance") or 65) if db_user else 65
            effective_shift_start = (db_user.get("shift_start") if db_user else None) or "09:00:00"
            effective_shift_end   = (db_user.get("shift_end")   if db_user else None) or "18:00:00"
            allowance_minutes = get_shift_break_allowance(effective_shift_start, effective_shift_end, raw_db_allowance)
            limit_seconds = allowance_minutes * 60

            last_sess = att_sessions[-1]
            last_sess_id = last_sess["id"]
            current_fine_applied = last_sess.get("fine_applied", 0)
            current_fine_reason = last_sess.get("fine_reason") or ""

            if total_break_seconds > limit_seconds:
                # Exceeded break limit! Apply fine automatically if not already applied
                if not current_fine_applied:
                    # Avoid overwriting explicit waivers
                    if current_fine_reason.lower() not in ["waived", "revoked", "exempt", "approved", "ok", "excused"]:
                        DEFAULT_FINE_AMOUNT = 500.0
                        fine_reason = (
                            f"Exceeded Break/Field Limit — "
                            f"{format_seconds(total_break_seconds)} used, "
                            f"limit {allowance_minutes} min"
                        )
                        db.create_fine(telegram_id, date_str, DEFAULT_FINE_AMOUNT, fine_reason)
                        db.set_attendance_fine(last_sess_id, 1, DEFAULT_FINE_AMOUNT, fine_reason)
            else:
                # Under the limit!
                # If a break limit fine was previously applied automatically, remove it
                if current_fine_applied and "Exceeded Break/Field Limit" in current_fine_reason:
                    db.delete_fine(telegram_id, date_str)
                    db.set_attendance_fine(last_sess_id, 0, 0.0, "")

        return {
            "telegram_id": telegram_id,
            "date": date_str,
            "login_time": login_time,
            "logout_time": logout_time,
            "total_login_seconds": total_login_seconds,
            "lunch_break_seconds": lunch_break_seconds,
            "total_break_seconds": total_break_seconds,
            "total_move_seconds": total_move_seconds,
            "net_working_seconds": net_working_seconds,
            "total_login_str": format_seconds(total_login_seconds),
            "lunch_break_str": format_seconds(lunch_break_seconds),
            "total_break_str": format_seconds(total_break_seconds),
            "total_move_str": format_seconds(total_move_seconds),
            "net_working_str": format_seconds(net_working_seconds),
        }

    @staticmethod
    def generate_admin_daily_report_text(db: BaseDatabase, date_str: str) -> str:
        """Generates a styled Markdown dashboard report of all employees for admin users."""
        users = db.get_all_users()
        if not users:
            return f"📅 *Daily Report ({date_str})*\n\n⚠️ No registered employees found in the system."

        text = f"📊 *System Dashboard - Daily Report*\n📅 *Date:* {date_str}\n━━━━━━━━━━━━━━━━━━━\n\n"
        
        employees_count = 0
        active_count = 0
        total_net_seconds = 0
        
        for u in users:
            if u["role"] == "admin":
                # We skip admins from the main list unless they log attendance
                # Let's show admins if they have attendance logs on this day, else skip
                att = db.get_attendance_sessions_by_date(u["telegram_id"], date_str)
                if not att:
                    continue

            summary = AttendanceReporter.get_employee_daily_summary(db, u["telegram_id"], date_str)
            employees_count += 1
            
            # Count active users
            if summary["logout_time"] == "Active (Logged In)":
                active_count += 1
                status_emoji = "🟢 Working"
            elif summary["login_time"] != "N/A":
                att_sess = db.get_attendance_sessions_by_date(u["telegram_id"], date_str)
                is_hd = 0
                if att_sess:
                    is_hd = att_sess[-1].get("is_half_day", 0)
                status_emoji = "🟡 Half Day" if is_hd else "🟢 Full Day"
            else:
                status_emoji = "⚪ Absent"
                
            total_net_seconds += summary["net_working_seconds"]
            
            text += (
                f"👤 *{u['full_name']}*\n"
                f"  ├─ Status: {status_emoji}\n"
                f"  ├─ Punch: `{summary['login_time']}` ➡️ `{summary['logout_time']}`\n"
                f"  ├─ Break: `{summary['total_break_str']}` | Field: `{summary['total_move_str']}`\n"
                f"  └─ Net Hours: *{summary['net_working_str']}*\n"
                f"───────────────────\n"
            )

        if employees_count == 0:
            return f"📅 *Daily Report ({date_str})*\n\n⚪ No employee attendance records found for today."

        avg_seconds = total_net_seconds // employees_count
        text += (
            f"📈 *Summary Statistics:*\n"
            f"👥 *Total Tracked:* {employees_count}\n"
            f"⚡ *Currently Active:* {active_count}\n"
            f"⏱️ *Average Net Hours:* `{format_seconds(avg_seconds)}`"
        )
        return text
