from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseDatabase(ABC):
    """
    Abstract Base Class outlining the interface for the database adapter.
    This enables database swaps (SQLite -> MySQL) without changing bot business logic.
    """

    @abstractmethod
    def connect(self) -> Any:
        """Establish connection to the database."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close connection to the database."""
        pass

    @abstractmethod
    def execute_schema(self, schema_file: str) -> None:
        """Execute standard SQL schema setup script."""
        pass

    # --- User Management ---
    @abstractmethod
    def register_user(self, telegram_id: int, username: Optional[str], full_name: str, role: str = 'employee') -> bool:
        """Register a new employee/admin."""
        pass

    @abstractmethod
    def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Fetch user by Telegram ID."""
        pass

    @abstractmethod
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Fetch all registered users."""
        pass

    @abstractmethod
    def update_user_status(self, telegram_id: int, status: str) -> bool:
        """Update a user's status (e.g. 'active' or 'banned')."""
        pass

    # --- Attendance Session (Login / Logout) ---
    @abstractmethod
    def create_attendance_session(self, telegram_id: int, username: Optional[str], name: str, date: str, login_time: str) -> int:
        """Create a new attendance session when employee logs in. Returns session ID."""
        pass

    @abstractmethod
    def update_attendance_session(self, session_id: int, logout_time: str, duration: int) -> bool:
        """Close the attendance session on logout. Sets logout_time and duration."""
        pass

    @abstractmethod
    def get_active_attendance_session(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get currently active (non-logged-out) attendance session for an employee."""
        pass

    @abstractmethod
    def get_attendance_sessions_by_date(self, telegram_id: int, date: str) -> List[Dict[str, Any]]:
        """Get all attendance sessions of an employee for a specific date."""
        pass

    # --- Break Session (Break In / Break Out) ---
    @abstractmethod
    def create_break_session(self, telegram_id: int, username: Optional[str], name: str, date: str, break_in_time: str) -> int:
        """Start a break session. Returns session ID."""
        pass

    @abstractmethod
    def update_break_session(self, session_id: int, break_out_time: str, duration: int) -> bool:
        """End a break session. Sets break_out_time and duration."""
        pass

    @abstractmethod
    def get_active_break_session(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get currently active break session for an employee."""
        pass

    @abstractmethod
    def get_break_sessions_by_date(self, telegram_id: int, date: str) -> List[Dict[str, Any]]:
        """Get all break sessions of an employee for a specific date."""
        pass

    # --- Movement Session (In / Out) ---
    @abstractmethod
    def create_in_out_session(self, telegram_id: int, username: Optional[str], name: str, date: str, in_time: str) -> int:
        """Start a movement/field visit. Returns session ID."""
        pass

    @abstractmethod
    def update_in_out_session(self, session_id: int, out_time: str, duration: int) -> bool:
        """End a movement/field visit. Sets out_time and duration."""
        pass

    @abstractmethod
    def get_active_in_out_session(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get currently active movement session for an employee."""
        pass

    @abstractmethod
    def get_in_out_sessions_by_date(self, telegram_id: int, date: str) -> List[Dict[str, Any]]:
        """Get all movement sessions of an employee for a specific date."""
        pass

    # --- Early Logout Requests ---
    @abstractmethod
    def create_early_logout_request(self, telegram_id: int, username: Optional[str], name: str, date: str, logout_time: str, reason: str) -> int:
        """Create a new early logout request. Returns request ID."""
        pass

    @abstractmethod
    def get_early_logout_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        """Get an early logout request by ID."""
        pass

    @abstractmethod
    def get_early_logout_request_by_date(self, telegram_id: int, date: str) -> Optional[Dict[str, Any]]:
        """Get early logout request for a specific employee and date."""
        pass

    @abstractmethod
    def get_all_early_logout_requests(self) -> List[Dict[str, Any]]:
        """Fetch all early logout requests (newest first)."""
        pass

    @abstractmethod
    def update_early_logout_request_status(self, request_id: int, status: str) -> bool:
        """Update request status (approved, rejected, pending)."""
        pass

    @abstractmethod
    def set_attendance_half_day(self, telegram_id: int, date: str, is_half_day: int) -> bool:
        """Mark an attendance session as a half day."""
        pass

    # --- Fine Management ---
    @abstractmethod
    def set_attendance_fine(self, session_id: int, fine_applied: int, fine_amount: float, fine_reason: Optional[str]) -> bool:
        """Toggle fine status and amount for a specific attendance session."""
        pass

    @abstractmethod
    def create_fine(self, telegram_id: int, date: str, amount: float, reason: Optional[str]) -> bool:
        """Create or update a fine record for a specific employee and date."""
        pass

    @abstractmethod
    def delete_fine(self, telegram_id: int, date: str) -> bool:
        """Delete a fine record for a specific employee and date."""
        pass

    @abstractmethod
    def get_fines_by_employee(self, telegram_id: int) -> List[Dict[str, Any]]:
        """Get all fines for an employee."""
        pass

    @abstractmethod
    def get_all_fines(self) -> List[Dict[str, Any]]:
        """Get all system fines."""
        pass

