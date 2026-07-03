"""
Smoke tests for the Flask admin dashboard.

Runs against an throwaway COPY of attendance.db (never the live file), and
patches notify_employee() so no real Telegram messages are ever sent to real
employees during testing. Any employee records created/edited/deleted here
use an obviously-fake negative telegram_id and only touch the DB copy.

Run with:
    PYTHONPATH=. python3 -m unittest tests.test_dashboard_smoke -v
"""
import os
import sys
import shutil
import tempfile
import unittest
from unittest.mock import patch

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# Point DB_PATH at an isolated copy BEFORE config/dashboard.app are imported,
# since both read/open the DB at import time.
_temp_dir = tempfile.mkdtemp(prefix="attendance_dashboard_smoke_")
_temp_db_path = os.path.join(_temp_dir, "smoke_test.db")
_source_db = os.path.join(_PROJECT_ROOT, "attendance.db")
if os.path.exists(_source_db):
    shutil.copy(_source_db, _temp_db_path)
os.environ["DB_PATH"] = _temp_db_path

import config  # noqa: E402
import dashboard.app as dash_app  # noqa: E402


class DashboardSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dash_app.app.testing = True
        cls.client = dash_app.app.test_client()
        # Hard block on any real outbound Telegram call for the whole test class.
        cls._notify_patcher = patch.object(dash_app, "notify_employee", return_value=True)
        cls._notify_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._notify_patcher.stop()
        shutil.rmtree(_temp_dir, ignore_errors=True)

    def test_index_page_loads(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)

    def test_summary_endpoint(self):
        res = self.client.get("/api/summary")
        self.assertEqual(res.status_code, 200)
        self.assertIn("total_employees", res.get_json())

    def test_employees_endpoint(self):
        res = self.client.get("/api/employees")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.get_json(), list)

    def test_shifts_employees_endpoint(self):
        res = self.client.get("/api/shifts/employees")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.get_json(), list)

    def test_requests_endpoint(self):
        res = self.client.get("/api/requests")
        self.assertEqual(res.status_code, 200)

    def test_attendance_daily_endpoint(self):
        res = self.client.get("/api/attendance/daily")
        self.assertEqual(res.status_code, 200)
        self.assertIn("records", res.get_json())

    def test_export_csv(self):
        res = self.client.get("/api/export?format=csv")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res.content_type)

    def test_export_xlsx(self):
        res = self.client.get("/api/export?format=xlsx")
        self.assertEqual(res.status_code, 200)

    def test_export_breaks_excel(self):
        res = self.client.get("/api/export/breaks")
        self.assertEqual(res.status_code, 200)

    def test_employee_crud_roundtrip_on_fake_record(self):
        fake_id = -999000111  # obviously fake, never a real Telegram user id
        create_res = self.client.post("/api/employees", json={
            "full_name": "Smoke Test Employee",
            "username": "smoketestuser",
            "telegram_id": fake_id,
            "shift_start": "09:00:00",
            "shift_end": "18:00:00",
        })
        self.assertEqual(create_res.status_code, 200, create_res.get_json())

        detail_res = self.client.get(f"/api/employee/{fake_id}")
        self.assertEqual(detail_res.status_code, 200)
        self.assertEqual(detail_res.get_json()["profile"]["full_name"], "Smoke Test Employee")

        edit_res = self.client.put(f"/api/employees/{fake_id}", json={
            "full_name": "Smoke Test Employee Updated",
            "shift_start": "09:00:00",
            "shift_end": "18:00:00",
        })
        self.assertEqual(edit_res.status_code, 200, edit_res.get_json())

        ban_res = self.client.post(f"/api/employees/{fake_id}/status", json={"status": "banned"})
        self.assertEqual(ban_res.status_code, 200)
        dash_app.notify_employee.assert_called()

        unban_res = self.client.post(f"/api/employees/{fake_id}/status", json={"status": "active"})
        self.assertEqual(unban_res.status_code, 200)

        fine_res = self.client.get(f"/api/employee/{fake_id}")
        att_logs = fine_res.get_json()["attendance_logs"]
        if att_logs:
            sess_id = att_logs[0]["id"]
            fine_apply_res = self.client.post(f"/api/attendance/{sess_id}/fine", json={
                "fine_applied": True, "fine_amount": 100.0, "fine_reason": "Smoke test"
            })
            self.assertEqual(fine_apply_res.status_code, 200)

        delete_res = self.client.delete(f"/api/employees/{fake_id}")
        self.assertEqual(delete_res.status_code, 200)

        gone_res = self.client.get(f"/api/employee/{fake_id}")
        self.assertEqual(gone_res.status_code, 404)


class DashboardAuthGateTests(unittest.TestCase):
    """Verifies the opt-in HTTP Basic Auth gate added for public hosting."""

    def setUp(self):
        dash_app.app.testing = True
        self.client = dash_app.app.test_client()
        self._orig_password = dash_app.DASHBOARD_PASSWORD
        self._orig_username = dash_app.DASHBOARD_USERNAME
        dash_app.DASHBOARD_USERNAME = "admin"
        dash_app.DASHBOARD_PASSWORD = "s3cr3t"

    def tearDown(self):
        dash_app.DASHBOARD_USERNAME = self._orig_username
        dash_app.DASHBOARD_PASSWORD = self._orig_password

    def test_unauthenticated_request_rejected(self):
        res = self.client.get("/api/summary")
        self.assertEqual(res.status_code, 401)

    def test_wrong_credentials_rejected(self):
        res = self.client.get(
            "/api/summary",
            headers={"Authorization": "Basic " + __import__("base64").b64encode(b"admin:wrong").decode()},
        )
        self.assertEqual(res.status_code, 401)

    def test_correct_credentials_allowed(self):
        res = self.client.get(
            "/api/summary",
            headers={"Authorization": "Basic " + __import__("base64").b64encode(b"admin:s3cr3t").decode()},
        )
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
