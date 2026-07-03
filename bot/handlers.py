from telegram import Update
from telegram.ext import ContextTypes
import config
from database.base import BaseDatabase
from google_sheets.sheets_sync import GoogleSheetsSyncManager
from bot.validation import (
    AttendanceValidationEngine,
    auto_close_leftover_sessions,
    calculate_time_difference,
    format_seconds_to_duration
)
from reports.reporter import (
    AttendanceReporter,
    get_current_date_str,
    get_current_time_str,
    get_shift_break_allowance
)
from bot.keyboards import BotKeyboards
from bot.shifts import get_employee_shift

BAN_LIMIT_SECONDS = 65 * 60  # 65 minutes in seconds (legacy fallback)
DEFAULT_FINE_AMOUNT = 500.0  # Default fine amount in INR
LATE_LOGIN_GRACE_MINUTES = 10  # Grace period before late login fine kicks in


class BotHandlerManager:
    """
    Controller class to manage Telegram events.
    Binds the database and Google sheets sync adapters to handlers.
    """

    def __init__(self, db: BaseDatabase, sheets_sync: GoogleSheetsSyncManager):
        self.db = db
        self.sheets_sync = sheets_sync

    async def _check_and_enforce_ban(
        self, update: Update, telegram_id: int, today_date: str,
        keyboard, username: str = None, shift_start: str = None, shift_end: str = None
    ) -> bool:
        """
        Calculates combined break + field movement duration for today.
        Uses shift-type-aware allowance (65 min day / 75 min night).
        If it exceeds the configured break allowance, applies a fine and notifies
        the employee and admins — but does NOT ban the user.
        Returns True if the limit was exceeded, False otherwise.
        """
        from reports.reporter import AttendanceReporter

        # Load user break allowance from database
        db_user = self.db.get_user(telegram_id)
        raw_db_allowance = (db_user.get("break_allowance") or 65) if db_user else 65

        # Use shift-type-aware allowance
        effective_shift_start = shift_start or (db_user.get("shift_start") if db_user else None) or "09:00:00"
        effective_shift_end   = shift_end   or (db_user.get("shift_end")   if db_user else None) or "18:00:00"
        allowance_minutes = get_shift_break_allowance(effective_shift_start, effective_shift_end, raw_db_allowance)
        limit_seconds = allowance_minutes * 60

        summary = AttendanceReporter.get_employee_daily_summary(self.db, telegram_id, today_date)
        combined_seconds = summary["total_break_seconds"]

        if combined_seconds > limit_seconds:
            over_by = combined_seconds - limit_seconds
            limit_str = format_seconds_to_duration(limit_seconds)
            name = db_user["full_name"] if db_user else str(telegram_id)
            uname = f"@{username}" if username else f"ID:{telegram_id}"

            # Apply a fine instead of banning
            fine_reason = (
                f"Exceeded Break/Field Limit — "
                f"{format_seconds_to_duration(combined_seconds)} used, "
                f"limit {allowance_minutes} min"
            )
            try:
                self.db.create_fine(telegram_id, today_date, DEFAULT_FINE_AMOUNT, fine_reason)
            except Exception as fine_err:
                print(f"⚠️ Error applying break-limit fine for {telegram_id}: {fine_err}")

            # Warn the employee (no ban message)
            warn_msg = (
                f"⚠️ *Break/Field Time Limit Exceeded*\n\n"
                f"⏱️ Combined Break + Field Time: `{format_seconds_to_duration(combined_seconds)}`\n"
                f"📏 Allowed Limit: `{limit_str}` ({allowance_minutes} minutes)\n"
                f"⛔ Over Limit by: `{format_seconds_to_duration(over_by)}`\n"
                f"💰 Fine Applied: *INR {DEFAULT_FINE_AMOUNT:.0f}*\n\n"
                f"_Please keep your break and field movement within the allowed limit._"
            )
            try:
                await update.message.reply_text(warn_msg, parse_mode="Markdown")
            except Exception:
                pass

            # Notify all admins
            for admin_id in config.ADMIN_TELEGRAM_IDS:
                try:
                    await update.get_bot().send_message(
                        chat_id=admin_id,
                        text=(
                            f"⚠️ *Break Limit Fine Alert*\n\n"
                            f"👤 Employee: *{name}* ({uname})\n"
                            f"📅 Date: `{today_date}`\n"
                            f"⏱️ Combined Time: `{format_seconds_to_duration(combined_seconds)}`\n"
                            f"📏 Limit ({allowance_minutes} min): `{limit_str}`\n"
                            f"⛔ Over Limit by: `{format_seconds_to_duration(over_by)}`\n"
                            f"💰 Fine Applied: *INR {DEFAULT_FINE_AMOUNT:.0f}*"
                        ),
                        parse_mode="Markdown"
                    )
                except Exception as notify_err:
                    print(f"⚠️ Could not notify admin {admin_id}: {notify_err}")
            return True
        return False

    def _get_remaining_time_text(self, telegram_id: int, username: str, today_date: str, current_time: str) -> str:
        """
        Calculates remaining allowed break/field movement time for the employee.
        Accounts for already-used seconds today plus time elapsed in the current active session.
        Returns a plain-text countdown string.
        """
        from reports.reporter import AttendanceReporter, get_shift_break_allowance

        db_user = self.db.get_user(telegram_id)
        raw_db_allowance = (db_user.get("break_allowance") or 65) if db_user else 65

        effective_shift_start = (db_user.get("shift_start") if db_user else None) or "09:00:00"
        effective_shift_end   = (db_user.get("shift_end")   if db_user else None) or "18:00:00"
        allowance_minutes = get_shift_break_allowance(effective_shift_start, effective_shift_end, raw_db_allowance)
        limit_seconds = allowance_minutes * 60

        # Total already-used break+movement seconds (closed sessions only)
        summary = AttendanceReporter.get_employee_daily_summary(self.db, telegram_id, today_date)
        used_closed_seconds = summary["total_break_seconds"]

        # Add elapsed time in the currently active session (if any)
        current_session_elapsed = 0
        active_brk = self.db.get_active_break_session(telegram_id)
        active_move = self.db.get_active_in_out_session(telegram_id)
        if active_brk:
            current_session_elapsed = calculate_time_difference(active_brk["break_in_time"], current_time)
        elif active_move:
            current_session_elapsed = calculate_time_difference(active_move["in_time"], current_time)

        total_used = used_closed_seconds + current_session_elapsed
        remaining = max(0, limit_seconds - total_used)
        remaining_str = format_seconds_to_duration(remaining)

        if remaining == 0:
            status_icon = "🔴"
            status_note = "\n⚠️ _Your allowed break time has been fully used!_"
        elif remaining < 600:  # Less than 10 minutes
            status_icon = "🟠"
            status_note = "\n⚠️ _Less than 10 minutes remaining!_"
        else:
            status_icon = "🟢"
            status_note = ""

        return (
            f"{status_icon} *Time Remaining to Return*\n\n"
            f"⏳ `{remaining_str}`{status_note}"
        )



    async def _check_and_apply_late_login_fine(
        self, update: Update, telegram_id: int, session_id: int,
        today_date: str, login_time: str, shift_start: str,
        keyboard, db_user: dict, username: str = None
    ) -> None:
        """
        Checks if the employee logged in more than LATE_LOGIN_GRACE_MINUTES after
        their shift start. If so, automatically applies a Rs. 500 fine.
        """
        from reports.reporter import get_current_time_str

        def _time_to_sec(t: str) -> int:
            try:
                parts = list(map(int, t.split(":")))
                return parts[0] * 3600 + parts[1] * 60 + (parts[2] if len(parts) > 2 else 0)
            except Exception:
                return 0

        login_sec  = _time_to_sec(login_time)
        start_sec  = _time_to_sec(shift_start)
        grace_sec  = LATE_LOGIN_GRACE_MINUTES * 60

        # Handle overnight wrapping: if shift_start is late evening and login is early morning
        diff = login_sec - start_sec
        if diff < -12 * 3600:   # Wrapped forward past midnight
            diff += 24 * 3600
        elif diff > 12 * 3600:  # Login is way earlier (night shift started previous evening)
            diff -= 24 * 3600

        if diff <= grace_sec:
            # On time or within grace period — no fine
            return

        # Late login detected
        late_by_sec  = diff - grace_sec
        late_minutes = late_by_sec // 60
        fine_reason  = f"Late Login — {late_minutes} min after shift start ({shift_start[:5]})"
        name = db_user["full_name"] if db_user else str(telegram_id)

        try:
            # Apply fine to the attendance session
            self.db.set_attendance_fine(session_id, 1, DEFAULT_FINE_AMOUNT, fine_reason)
            # Create audit fine record
            self.db.create_fine(telegram_id, today_date, DEFAULT_FINE_AMOUNT, fine_reason)
        except Exception as fine_err:
            print(f"⚠️ Error applying late login fine for {telegram_id}: {fine_err}")
            return

        # Notify employee
        late_msg = (
            f"⚠️ *Late Login Fine Applied*\n\n"
            f"📅 Date: `{today_date}`\n"
            f"⏰ Your Login: `{login_time}`\n"
            f"🕐 Shift Start: `{shift_start[:5]}`\n"
            f"⏱️ Late By: `{late_minutes} minutes`\n"
            f"💰 Fine: *INR {DEFAULT_FINE_AMOUNT:.0f}*\n\n"
            f"_Employees must login within {LATE_LOGIN_GRACE_MINUTES} minutes of their shift start._"
        )
        try:
            # No reply_markup here: "Login Recorded!" (sent immediately before this,
            # in the same handler call) already re-attached the persistent keyboard.
            # Re-attaching it again here made Telegram Desktop anchor its "reply to"
            # bar on this message instead of the login confirmation.
            await update.message.reply_text(late_msg, parse_mode="Markdown")
        except Exception:
            pass

        # Notify admins
        uname = f"@{username}" if username else f"ID:{telegram_id}"
        admin_msg = (
            f"⏰ *Late Login Fine* — {name} ({uname})\n"
            f"📅 Date: `{today_date}` | Login: `{login_time}`\n"
            f"🕐 Shift Start: `{shift_start[:5]}` | Late by: `{late_minutes} min`\n"
            f"💰 Fine Applied: *INR {DEFAULT_FINE_AMOUNT:.0f}*"
        )
        for admin_id in config.ADMIN_TELEGRAM_IDS:
            try:
                await update.get_bot().send_message(
                    chat_id=admin_id, text=admin_msg, parse_mode="Markdown"
                )
            except Exception as notify_err:
                print(f"⚠️ Could not notify admin {admin_id} of late login: {notify_err}")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /start command. Handles registration check & greeting."""
        user = update.effective_user
        if not user:
            return

        telegram_id = user.id
        username = user.username
        
        # 1. Try finding by telegram_id
        db_user = self.db.get_user(telegram_id)
        
        # 2. If not found by telegram_id, check if they were pre-registered by username
        if not db_user and username:
            pre_registered = self.db.get_user_by_username(username)
            if pre_registered:
                # Update their Telegram ID to their actual user ID
                self.db.update_telegram_id_for_username(username, telegram_id)
                # Re-fetch the user details
                db_user = self.db.get_user(telegram_id)
        
        is_admin = telegram_id in config.ADMIN_TELEGRAM_IDS

        if db_user:
            # Welcome back registered user
            # Upgrade to admin if not recorded in DB
            if is_admin and db_user["role"] != "admin":
                self.db.register_user(telegram_id, username, db_user["full_name"], "admin")
                db_user = self.db.get_user(telegram_id)

            keyboard = BotKeyboards.get_attendance_keyboard()
            await update.message.reply_text(
                text=f"👋 *Welcome back, {db_user['full_name']}!*\n\n"
                     f"Select an action from the menu below to punch your time card.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            # Registration flow starter
            await update.message.reply_text(
                text="👋 *Welcome to the Employee Attendance & Time Tracking Bot!*\n\n"
                     "You are not registered yet. Please reply directly with your *Full Name* "
                     "to register and start using the system.",
                parse_mode="Markdown"
            )

    async def request_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /request [reason] command. Allows employees to submit early logout requests."""
        user = update.effective_user
        if not user or not update.message:
            return

        telegram_id = user.id
        username = user.username
        db_user = self.db.get_user(telegram_id)
        
        if not db_user:
            await update.message.reply_text("⚠️ You must register first before submitting requests.")
            return

        if db_user.get("status") == "banned":
            await update.message.reply_text("❌ Access Denied: You are BANNED from the system.")
            return

        if not context.args:
            await update.message.reply_text(
                "⚠️ *Missing Reason*\n\n"
                "Please specify the reason for early logout.\n"
                "Usage: `/request <reason>`\n"
                "Example: `/request Family emergency`",
                parse_mode="Markdown"
            )
            return

        reason = " ".join(context.args).strip()
        today_date = get_current_date_str()

        # Check if there is a logout today
        sessions = self.db.get_attendance_sessions_by_date(telegram_id, today_date)
        if not sessions:
            await update.message.reply_text("⚠️ You have not logged in today yet. Please login and logout first.")
            return

        last_session = sessions[-1]
        shift_start, shift_end = get_employee_shift(username, self.db)
        
        if last_session["status"] == "active":
            await update.message.reply_text("⚠️ Please Logout first before submitting an early logout request.")
            return

        logout_time = last_session["logout_time"]
        if not logout_time:
            await update.message.reply_text("⚠️ No completed logout session found for today.")
            return

        def time_str_to_seconds(t_str: str) -> int:
            try:
                parts = list(map(int, t_str.split(":")))
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            except Exception:
                return 0

        if time_str_to_seconds(logout_time) >= time_str_to_seconds(shift_end):
            await update.message.reply_text(
                f"ℹ️ Your logout today was at `{logout_time}`, which is at or after your shift end time (`{shift_end}`).\n"
                "No early logout request is required."
            )
            return

        try:
            existing = self.db.get_early_logout_request_by_date(telegram_id, today_date)
            if existing:
                await update.message.reply_text(
                    f"ℹ️ You have already submitted an early logout request for today ({today_date}) with reason: *{existing['reason']}*.\n"
                    f"Status: `{existing['status'].capitalize()}`",
                    parse_mode="Markdown"
                )
                return

            self.db.create_early_logout_request(
                telegram_id=telegram_id,
                username=username,
                name=db_user["full_name"],
                date=today_date,
                logout_time=logout_time,
                reason=reason
            )

            await update.message.reply_text(
                f"📩 *Early Logout Request Submitted!*\n\n"
                f"👤 Name: *{db_user['full_name']}*\n"
                f"📅 Date: `{today_date}`\n"
                f"⏰ Logout Time: `{logout_time}`\n"
                f"📝 Reason: *{reason}*\n\n"
                f"Your request has been sent to the administrator for review.",
                parse_mode="Markdown"
            )

            # Notify admins
            for admin_id in config.ADMIN_TELEGRAM_IDS:
                try:
                    await update.get_bot().send_message(
                        chat_id=admin_id,
                        text=(
                            f"📩 *New Early Logout Request* 📩\n\n"
                            f"👤 Employee: *{db_user['full_name']}* (@{username or 'NoUsername'})\n"
                            f"📅 Date: `{today_date}`\n"
                            f"⏰ Logout: `{logout_time}` (Shift ends: `{shift_end}`)\n"
                            f"📝 Reason: *{reason}*\n\n"
                            f"Review this request on the dashboard."
                        ),
                        parse_mode="Markdown"
                    )
                except Exception as notify_err:
                    print(f"⚠️ Could not notify admin {admin_id}: {notify_err}")

        except Exception as e:
            print(f"Error submitting early logout request: {e}")
            await update.message.reply_text("⚠️ An error occurred while saving your request. Please try again.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

        """Global message handler. Routes registration entries and button actions."""
        user = update.effective_user
        if not user or not update.message:
            return

        telegram_id = user.id
        username = user.username
        message_text = update.message.text.strip()
        
        db_user = self.db.get_user(telegram_id)
        is_admin = telegram_id in config.ADMIN_TELEGRAM_IDS or (db_user and db_user["role"] == "admin")
        keyboard = BotKeyboards.get_attendance_keyboard()
        is_group = update.effective_chat.type in ["group", "supergroup"]

        # 1. Handle Registration Flow for unregistered users
        if not db_user:
            if is_group:
                # Silently delete their message in the group to avoid spam and enforce DM registration
                try:
                    await update.message.delete()
                except Exception:
                    pass
                return

            # Treat the text message as their registration full name
            if len(message_text) < 3 or len(message_text) > 100:
                await update.message.reply_text("⚠️ Please enter a valid Full Name (between 3 and 100 characters).")
                return

            role = "admin" if telegram_id in config.ADMIN_TELEGRAM_IDS else "employee"
            shift_start, shift_end = get_employee_shift(username, self.db)
            success = self.db.register_user(telegram_id, username, message_text, role, shift_start, shift_end)
            
            if success:
                keyboard = BotKeyboards.get_attendance_keyboard()
                await update.message.reply_text(
                    text=f"✅ *Registration Successful!*\n\n"
                         f"Registered as: *{message_text}*\n"
                         f"Role: *{role.capitalize()}*\n\n"
                         f"You can now track your attendance using the menu buttons below.",
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
            else:
                await update.message.reply_text("⚠️ Database error during registration. Please try again.")
            return

        today_date = get_current_date_str()
        current_time = get_current_time_str()

        # A. Clean up yesterday leftover sessions if any immediately so they don't block state checks
        auto_close_leftover_sessions(self.db, telegram_id, today_date, self.sheets_sync)

        # Fetch active states
        active_att  = self.db.get_active_attendance_session(telegram_id)
        active_brk  = self.db.get_active_break_session(telegram_id)
        active_move = self.db.get_active_in_out_session(telegram_id)

        # 2. If the employee is currently logged in AND on an active Out or Lunch Out session,
        #    respond ONLY with the remaining time countdown. No keyboard. No other info.
        if active_att and (active_brk or active_move):
            # Allow "Lunch In." while on lunch break, and "IN." while on field movement,
            # so the employee can end their session. All other messages → countdown only.
            is_ending_break = (active_brk  and message_text == "Lunch In.")
            is_ending_move  = (active_move and message_text == "IN.")

            if not is_ending_break and not is_ending_move:
                if is_group:
                    # In a group chat, delete the invalid message. Do not reply with countdown to keep chat clean.
                    if not is_admin:
                        try:
                            await update.message.delete()
                        except Exception:
                            pass
                    return
                else:
                    countdown_text = self._get_remaining_time_text(telegram_id, username, today_date, current_time)
                    await update.message.reply_text(countdown_text, parse_mode="Markdown")
                    return

        action_map = {
            "Login.": "login",
            "Logout.": "logout",
            "Lunch Out.": "break_in",
            "Lunch In.": "break_out",
            "Out.": "in",
            "IN.": "out",
        }

        action = action_map.get(message_text)
        if not action:
            if is_group:
                # If it's a group chat and the sender is not an admin, delete their message.
                if not is_admin:
                    try:
                        await update.message.delete()
                    except Exception:
                        pass
                return
            else:
                # Fallback for unrecognized messages in private chat
                await update.message.reply_text(
                    text="ℹ️ Please use the button keyboard below to select actions."
                )
                return

        # --- Running Punch Actions ---
        # B. Validate State Transition
        is_valid, error_msg, ctx = AttendanceValidationEngine.validate(self.db, telegram_id, action, today_date)
        if not is_valid:
            await update.message.reply_text(error_msg)
            return

        # C. Process Database & Sheets operations
        name = db_user["full_name"]
        
        try:
            if action == "login":
                session_id = self.db.create_attendance_session(telegram_id, username, name, today_date, current_time)
                # Run Sheets Sync async-safe
                self.sheets_sync.sync_session_start("attendance", session_id, telegram_id, username, name, today_date, current_time)
                await update.message.reply_text(
                    f"🟢 *Login Recorded!*\n📅 Date: `{today_date}`\n⏰ Time: `{current_time}`",
                    parse_mode="Markdown"
                )
                # Check and apply late login fine (>10 min after shift start)
                shift_start_time, shift_end_time = get_employee_shift(username, self.db)
                await self._check_and_apply_late_login_fine(
                    update=update,
                    telegram_id=telegram_id,
                    session_id=session_id,
                    today_date=today_date,
                    login_time=current_time,
                    shift_start=shift_start_time,
                    keyboard=keyboard,
                    db_user=db_user,
                    username=username
                )

            elif action == "logout":
                active_att = ctx["active_attendance"]
                duration = calculate_time_difference(active_att["login_time"], current_time)

                # --- Auto-calculate Full Day / Half Day at logout ---
                shift_start, shift_end = get_employee_shift(username, self.db)

                def time_str_to_seconds(t_str: str) -> int:
                    try:
                        parts = list(map(int, t_str.split(":")))
                        return parts[0] * 3600 + parts[1] * 60 + parts[2]
                    except Exception:
                        return 0

                # Total shift duration (handles overnight shifts via wrap-around)
                shift_start_sec = time_str_to_seconds(shift_start)
                shift_end_sec   = time_str_to_seconds(shift_end)
                if shift_end_sec <= shift_start_sec:
                    # Overnight shift: e.g. 20:30 → 08:30
                    shift_total_seconds = (86400 - shift_start_sec) + shift_end_sec
                else:
                    shift_total_seconds = shift_end_sec - shift_start_sec
                shift_total_seconds = max(1, shift_total_seconds)

                # Required = 8 hours (28800 seconds) for a Full Day
                required_working_seconds = 8 * 3600

                # Raw worked seconds = sum of all login-to-logout durations (NO break subtraction)
                # This is pure clock time: logout_time − login_time
                att_sessions = self.db.get_attendance_sessions_by_date(telegram_id, today_date)
                raw_worked_seconds = 0
                for s in att_sessions:
                    if s["id"] == active_att["id"]:
                        raw_worked_seconds += duration
                    else:
                        raw_worked_seconds += s["duration"] or 0

                # Half Day rule: raw clock time < 8 hours → Half Day
                #                raw clock time >= 8 hours → Full Day
                is_early    = time_str_to_seconds(current_time) < shift_end_sec
                is_half_day = 1 if raw_worked_seconds < required_working_seconds else 0

                self.db.update_attendance_session(active_att["id"], current_time, duration, is_half_day)
                self.sheets_sync.sync_session_end("attendance", active_att["id"], current_time, format_seconds_to_duration(duration))

                day_type_label = "🟡 Half Day" if is_half_day else "🟢 Full Day"

                # Required hours in HH:MM for display
                req_h = 8
                req_m = 0
                raw_h = raw_worked_seconds // 3600
                raw_m = (raw_worked_seconds % 3600) // 60

                early_warning = ""
                if is_early:
                    early_warning = (
                        f"\n\n⚠️ *Early Logout Detected!*\n"
                        f"Shift ends: `{shift_end[:5]}` | You logged out: `{current_time[:5]}`\n"
                        f"Raw time: `{raw_h:02d}h {raw_m:02d}m` / Required: `08h 00m`\n"
                        f"Submit a reason: `/request <your reason>`\n"
                        f"Example: `/request Doctor appointment`"
                    )

                await update.message.reply_text(
                    f"🔴 *Logout Recorded!*\n"
                    f"📅 Date: `{today_date}`\n"
                    f"⏰ Time: `{current_time}`\n"
                    f"⏱️ Raw Duration: `{raw_h:02d}h {raw_m:02d}m` (Required: `08h 00m`)\n"
                    f"📊 Day Status: *{day_type_label}*{early_warning}",
                    parse_mode="Markdown"
                )


            elif action == "break_in":
                session_id = self.db.create_break_session(telegram_id, username, name, today_date, current_time)
                self.sheets_sync.sync_session_start("break", session_id, telegram_id, username, name, today_date, current_time)
                # Send ONLY remaining time — no extra text, no keyboard
                countdown_text = self._get_remaining_time_text(telegram_id, username, today_date, current_time)
                await update.message.reply_text(countdown_text, parse_mode="Markdown")

            elif action == "break_out":
                active_brk = ctx["active_break"]
                duration = calculate_time_difference(active_brk["break_in_time"], current_time)
                self.db.update_break_session(active_brk["id"], current_time, duration)
                self.sheets_sync.sync_session_end("break", active_brk["id"], current_time, format_seconds_to_duration(duration))
                # Enforce shift-aware combined break limit (silent fine, no extra message)
                shift_start_time, shift_end_time = get_employee_shift(username, self.db)
                await self._check_and_enforce_ban(update, telegram_id, today_date, keyboard, username, shift_start_time, shift_end_time)
                # Send ONLY remaining time — no extra text, no keyboard
                countdown_text = self._get_remaining_time_text(telegram_id, username, today_date, current_time)
                await update.message.reply_text(countdown_text, parse_mode="Markdown")

            elif action == "in":
                session_id = self.db.create_in_out_session(telegram_id, username, name, today_date, current_time)
                self.sheets_sync.sync_session_start("in_out", session_id, telegram_id, username, name, today_date, current_time)
                # Send ONLY remaining time — no extra text, no keyboard
                countdown_text = self._get_remaining_time_text(telegram_id, username, today_date, current_time)
                await update.message.reply_text(countdown_text, parse_mode="Markdown")

            elif action == "out":
                active_move = ctx["active_in_out"]
                duration = calculate_time_difference(active_move["in_time"], current_time)
                self.db.update_in_out_session(active_move["id"], current_time, duration)
                self.sheets_sync.sync_session_end("in_out", active_move["id"], current_time, format_seconds_to_duration(duration))
                # Enforce shift-aware combined break limit (silent fine, no extra message)
                shift_start_time, shift_end_time = get_employee_shift(username, self.db)
                await self._check_and_enforce_ban(update, telegram_id, today_date, keyboard, username, shift_start_time, shift_end_time)
                # Send ONLY remaining time — no extra text, no keyboard
                countdown_text = self._get_remaining_time_text(telegram_id, username, today_date, current_time)
                await update.message.reply_text(countdown_text, parse_mode="Markdown")

        except Exception as e:
            print(f"❌ Error executing punch action '{action}': {e}")
            await update.message.reply_text(
                "⚠️ System Error processing action. DB update success, but sync failed."
            )
