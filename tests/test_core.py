"""
Offline test suite for the attendance system's core logic.

Runs entirely against a throwaway temp SQLite database (schema.sql).
Never touches the production attendance.db, and never calls Telegram
or Google Sheets over the network (those calls are mocked where needed).

Run with:
    PYTHONPATH=. python3 -m unittest tests.test_core -v
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from database.sqlite_db import SQLiteDatabase
from bot.validation import (
    AttendanceValidationEngine,
    auto_close_leftover_sessions,
    calculate_time_difference,
    format_seconds_to_duration,
)
from bot.shifts import get_employee_shift
from bot.keyboards import BotKeyboards
from reports.reporter import AttendanceReporter, calculate_time_diff_seconds


def make_temp_db() -> SQLiteDatabase:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = SQLiteDatabase(path)
    schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema.sql")
    db.execute_schema(schema_path)
    return db


class DurationMathTests(unittest.TestCase):
    def test_same_day_difference(self):
        self.assertEqual(calculate_time_difference("09:00:00", "17:30:00"), 8 * 3600 + 30 * 60)

    def test_overnight_wrap(self):
        # Night shift: 20:30 -> 08:30 next day = 12 hours
        self.assertEqual(calculate_time_difference("20:30:00", "08:30:00"), 12 * 3600)

    def test_format_seconds_to_duration(self):
        self.assertEqual(format_seconds_to_duration(3661), "01:01:01")

    def test_reporter_calculate_time_diff_matches(self):
        self.assertEqual(
            calculate_time_diff_seconds("20:30:00", "08:30:00"),
            calculate_time_difference("20:30:00", "08:30:00"),
        )


class ValidationEngineTests(unittest.TestCase):
    def setUp(self):
        self.db = make_temp_db()
        self.tid = 1001
        self.db.register_user(self.tid, "testuser1", "Test User", "employee", "09:00:00", "18:00:00")

    def tearDown(self):
        self.db.close()

    def test_unregistered_user_rejected(self):
        ok, msg, ctx = AttendanceValidationEngine.validate(self.db, 9999999, "login", "2026-07-03")
        self.assertFalse(ok)
        self.assertIn("not registered", msg)

    def test_login_then_double_login_rejected(self):
        ok, _, _ = AttendanceValidationEngine.validate(self.db, self.tid, "login", "2026-07-03")
        self.assertTrue(ok)
        self.db.create_attendance_session(self.tid, "testuser1", "Test User", "2026-07-03", "09:00:00")
        ok, msg, _ = AttendanceValidationEngine.validate(self.db, self.tid, "login", "2026-07-03")
        self.assertFalse(ok)
        self.assertIn("already Logged In", msg)

    def test_logout_before_login_rejected(self):
        ok, msg, _ = AttendanceValidationEngine.validate(self.db, self.tid, "logout", "2026-07-03")
        self.assertFalse(ok)
        self.assertIn("Log Out before Logging In", msg)

    def test_logout_blocked_while_on_break(self):
        self.db.create_attendance_session(self.tid, "testuser1", "Test User", "2026-07-03", "09:00:00")
        self.db.create_break_session(self.tid, "testuser1", "Test User", "2026-07-03", "13:00:00")
        ok, msg, _ = AttendanceValidationEngine.validate(self.db, self.tid, "logout", "2026-07-03")
        self.assertFalse(ok)
        self.assertIn("Lunch Break", msg)

    def test_full_punch_cycle(self):
        # login -> break_in -> break_out -> in -> out -> logout, each step valid
        for action in ("login",):
            ok, _, _ = AttendanceValidationEngine.validate(self.db, self.tid, action, "2026-07-03")
            self.assertTrue(ok)
        self.db.create_attendance_session(self.tid, "testuser1", "Test User", "2026-07-03", "09:00:00")

        ok, _, _ = AttendanceValidationEngine.validate(self.db, self.tid, "break_in", "2026-07-03")
        self.assertTrue(ok)
        brk_id = self.db.create_break_session(self.tid, "testuser1", "Test User", "2026-07-03", "13:00:00")

        ok, _, _ = AttendanceValidationEngine.validate(self.db, self.tid, "break_out", "2026-07-03")
        self.assertTrue(ok)
        self.db.update_break_session(brk_id, "13:30:00", 1800)

        ok, _, _ = AttendanceValidationEngine.validate(self.db, self.tid, "in", "2026-07-03")
        self.assertTrue(ok)
        move_id = self.db.create_in_out_session(self.tid, "testuser1", "Test User", "2026-07-03", "15:00:00")

        ok, _, _ = AttendanceValidationEngine.validate(self.db, self.tid, "out", "2026-07-03")
        self.assertTrue(ok)
        self.db.update_in_out_session(move_id, "15:15:00", 900)

        ok, _, _ = AttendanceValidationEngine.validate(self.db, self.tid, "logout", "2026-07-03")
        self.assertTrue(ok)

    def test_banned_user_rejected(self):
        self.db.update_user_status(self.tid, "banned")
        ok, msg, _ = AttendanceValidationEngine.validate(self.db, self.tid, "login", "2026-07-03")
        self.assertFalse(ok)
        self.assertIn("BANNED", msg)


class AutoCloseLeftoverTests(unittest.TestCase):
    def setUp(self):
        self.db = make_temp_db()
        self.tid = 2002
        self.db.register_user(self.tid, "testuser2", "Test User 2", "employee", "09:00:00", "18:00:00")

    def tearDown(self):
        self.db.close()

    def test_closes_yesterday_active_session(self):
        self.db.create_attendance_session(self.tid, "testuser2", "Test User 2", "2026-07-02", "09:00:00")
        auto_close_leftover_sessions(self.db, self.tid, "2026-07-03", sheets_sync_mgr=None)

        active = self.db.get_active_attendance_session(self.tid)
        self.assertIsNone(active)

        sessions = self.db.get_attendance_sessions_by_date(self.tid, "2026-07-02")
        self.assertEqual(sessions[0]["status"], "completed")
        self.assertEqual(sessions[0]["logout_time"], "23:59:59")
        self.assertEqual(sessions[0]["duration"], calculate_time_difference("09:00:00", "23:59:59"))

    def test_does_not_touch_todays_active_session(self):
        self.db.create_attendance_session(self.tid, "testuser2", "Test User 2", "2026-07-03", "09:00:00")
        auto_close_leftover_sessions(self.db, self.tid, "2026-07-03", sheets_sync_mgr=None)
        active = self.db.get_active_attendance_session(self.tid)
        self.assertIsNotNone(active)
        self.assertEqual(active["status"], "active")

    def test_notifies_sheets_sync_when_provided(self):
        self.db.create_attendance_session(self.tid, "testuser2", "Test User 2", "2026-07-02", "09:00:00")
        fake_sync = MagicMock()
        auto_close_leftover_sessions(self.db, self.tid, "2026-07-03", sheets_sync_mgr=fake_sync)
        fake_sync.sync_session_end.assert_called_once()


class ShiftLookupNoLeakTests(unittest.TestCase):
    """Regression test for the connection leak in get_employee_shift()."""

    def setUp(self):
        self.db = make_temp_db()
        self.db.register_user(3003, "nightowl", "Night Owl", "employee", "20:30:00", "08:30:00")

    def tearDown(self):
        self.db.close()

    def test_uses_provided_db_without_opening_new_connection(self):
        start, end = get_employee_shift("nightowl", self.db)
        self.assertEqual((start, end), ("20:30:00", "08:30:00"))

    def test_fallback_path_closes_its_own_connection(self):
        original_path = config.DB_PATH
        try:
            config.DB_PATH = self.db.db_path
            # No db passed -> function must open AND close its own temp connection.
            start, end = get_employee_shift("nightowl")
            self.assertEqual((start, end), ("20:30:00", "08:30:00"))
        finally:
            config.DB_PATH = original_path

    def test_unknown_username_falls_back_to_default(self):
        start, end = get_employee_shift("someone_not_in_db_or_hardcoded_list", self.db)
        self.assertEqual((start, end), ("09:00:00", "18:00:00"))


class ReporterSummaryTests(unittest.TestCase):
    def setUp(self):
        self.db = make_temp_db()
        self.tid = 5005
        self.db.register_user(self.tid, "reportuser", "Report User", "employee", "09:00:00", "18:00:00")

    def tearDown(self):
        self.db.close()

    def test_completed_day_net_hours(self):
        self.db.create_attendance_session(self.tid, "reportuser", "Report User", "2026-07-01", "09:00:00")
        att = self.db.get_active_attendance_session(self.tid)
        self.db.update_attendance_session(att["id"], "18:00:00", 9 * 3600)

        brk_id = self.db.create_break_session(self.tid, "reportuser", "Report User", "2026-07-01", "13:00:00")
        self.db.update_break_session(brk_id, "13:30:00", 1800)

        summary = AttendanceReporter.get_employee_daily_summary(self.db, self.tid, "2026-07-01")
        self.assertEqual(summary["total_login_seconds"], 9 * 3600)
        self.assertEqual(summary["total_break_seconds"], 1800)
        self.assertEqual(summary["net_working_seconds"], 9 * 3600 - 1800)

    def test_absent_day_reports_na(self):
        summary = AttendanceReporter.get_employee_daily_summary(self.db, self.tid, "2026-01-01")
        self.assertEqual(summary["login_time"], "N/A")
        self.assertEqual(summary["net_working_seconds"], 0)


class KeyboardTests(unittest.TestCase):
    def _button_texts(self, markup):
        return {btn.text for row in markup.keyboard for btn in row}

    def test_keyboard_has_only_punch_buttons(self):
        kb = BotKeyboards.get_attendance_keyboard()
        texts = self._button_texts(kb)
        self.assertEqual(
            texts,
            {"Login.", "Logout.", "Out.", "IN.", "Lunch Out.", "Lunch In."}
        )


class BotHandlerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """End-to-end tests of BotHandlerManager against a temp DB with a mocked Telegram Update."""

    async def asyncSetUp(self):
        self.db = make_temp_db()
        self.tid = 6006
        self.db.register_user(self.tid, "handleruser", "Handler User", "employee", "09:00:00", "18:00:00")

        from bot.handlers import BotHandlerManager
        self.sheets_sync = MagicMock()
        self.sheets_sync.sync_session_start = MagicMock(return_value=True)
        self.sheets_sync.sync_session_end = MagicMock(return_value=True)
        self.manager = BotHandlerManager(self.db, self.sheets_sync)

    async def asyncTearDown(self):
        self.db.close()

    def _make_update(self, text):
        update = MagicMock()
        update.effective_user.id = self.tid
        update.effective_user.username = "handleruser"
        update.effective_chat.type = "private"
        update.message.text = text
        update.message.reply_text = AsyncMock()
        update.message.delete = AsyncMock()
        update.get_bot.return_value.send_message = AsyncMock()
        return update

    async def test_login_sends_confirmation_and_creates_session(self):
        update = self._make_update("Login.")
        context = MagicMock()
        await self.manager.handle_message(update, context)

        active = self.db.get_active_attendance_session(self.tid)
        self.assertIsNotNone(active)
        update.message.reply_text.assert_called()
        args, kwargs = update.message.reply_text.call_args_list[0]
        text = args[0] if args else kwargs.get("text", "")
        self.assertIn("Login Recorded", text)

    async def test_break_flow_sends_countdown_only(self):
        self.db.create_attendance_session(self.tid, "handleruser", "Handler User",
                                           __import__("reports.reporter", fromlist=["get_current_date_str"]).get_current_date_str(),
                                           "09:00:00")
        update = self._make_update("Lunch Out.")
        context = MagicMock()
        await self.manager.handle_message(update, context)
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        self.assertIn("Time Remaining", args[0] if args else kwargs.get("text", ""))

    async def test_unregistered_user_first_message_registers_them(self):
        # In a private chat, an unregistered user's first free-text message is
        # treated as their full-name registration, not rejected.
        update = self._make_update("Brand New Employee")
        update.effective_user.id = 999888777
        update.effective_user.username = "brandnewuser"
        context = MagicMock()
        await self.manager.handle_message(update, context)

        self.assertIsNotNone(self.db.get_user(999888777))
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        text = args[0] if args else kwargs.get("text", "")
        self.assertIn("Registration Successful", text)

    async def test_unregistered_user_in_group_chat_is_silenced(self):
        # In a group chat, unregistered users must DM the bot instead of
        # accidentally "registering" with arbitrary group chatter.
        update = self._make_update("Hello everyone")
        update.effective_user.id = 999888778
        update.effective_user.username = "brandnewuser2"
        update.effective_chat.type = "group"
        context = MagicMock()
        await self.manager.handle_message(update, context)

        self.assertIsNone(self.db.get_user(999888778))
        update.message.reply_text.assert_not_called()
        update.message.delete.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
