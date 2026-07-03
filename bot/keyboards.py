from telegram import ReplyKeyboardMarkup, KeyboardButton
from typing import List

class BotKeyboards:
    """
    Utility class to generate bot ReplyKeyboardMarkups.
    Keyboards are persistent physical buttons appearing below the chat entry text.
    """

    @staticmethod
    def get_attendance_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
        """
        Returns the persistent reply keyboard for employee attendance tracking.
        Enables one-tap punching.
        """
        keyboard = [
            [
                KeyboardButton("Login."),
                KeyboardButton("Logout.")
            ],
            [
                KeyboardButton("Out."),
                KeyboardButton("IN.")
            ],
            [
                KeyboardButton("Lunch Out."),
                KeyboardButton("Lunch In.")
            ],
            [
                KeyboardButton("My Summary 📊"),
                KeyboardButton("Permission Request 📋")
            ]
        ]

        if is_admin:
            keyboard.append([KeyboardButton("Admin Report 📈")])

        return ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True,
            one_time_keyboard=False,
            is_persistent=True
        )

    @staticmethod
    def get_registration_keyboard() -> ReplyKeyboardMarkup:
        """
        Keyboard helper shown during registration.
        Allows the user to initiate registration.
        """
        keyboard = [
            [KeyboardButton("/start")]
        ]
        return ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True,
            one_time_keyboard=True
        )
