"""
bot/permission_handler.py
=========================
Multi-step ConversationHandler for the Permission Request feature.

Flow:
  Employee taps "Permission Request 📋"
    → Bot opens a PRIVATE DM conversation (never in group chat)
    → Step 1: Choose request type (inline keyboard)
    → Step 2: Enter start time  (e.g. 14:30)
    → Step 3: Enter end time    (e.g. 16:00)
    → Step 4: Enter reason text
    → Step 5: Confirm summary  (Confirm / Cancel inline buttons)
    → Saved to DB → admin(s) notified with Approve / Reject buttons

Admin callback:
  pr_approve_{id}  →  approve the request, notify employee
  pr_reject_{id}   →  reject the request, notify employee
"""

import re
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

import config
from reports.reporter import get_current_date_str, time_to_seconds, format_seconds

# ------------------------------------------------------------------
# Conversation states
# ------------------------------------------------------------------
(
    SELECT_TYPE,
    ENTER_START_TIME,
    ENTER_END_TIME,
    ENTER_REASON,
    CONFIRM,
) = range(5)

# ------------------------------------------------------------------
# Human-readable labels for each request type
# ------------------------------------------------------------------
REQUEST_TYPE_LABELS = {
    "short_leave":       "🏖️ Short Leave",
    "late_arrival":      "🕒 Late Arrival",
    "early_departure":   "🚶 Early Departure",
}

# ------------------------------------------------------------------
# Helper: parse a time string entered by the employee
# ------------------------------------------------------------------
def _parse_time(raw: str) -> Optional[str]:
    """
    Accept HH:MM or HH:MM:SS formats.
    Returns a normalised HH:MM:SS string or None if invalid.
    """
    raw = raw.strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(raw, fmt)
            return t.strftime("%H:%M:%S")
        except ValueError:
            pass
    return None


# ------------------------------------------------------------------
# STEP 0 – Entry point: bot taps "Permission Request 📋"
# ------------------------------------------------------------------
async def start_permission_request(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Entry point: show the type-selection keyboard."""
    user = update.effective_user
    if not user or not update.message:
        return ConversationHandler.END

    # This flow collects private info (reason, times) — never run it in a group chat.
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        try:
            await update.message.delete()
        except Exception:
            pass
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text="📋 Please use *Permission Request* here in DM, not in the group chat.",
                parse_mode="Markdown",
            )
        except Exception:
            pass
        return ConversationHandler.END

    # Only allow registered, non-banned users
    db = context.bot_data["db"]
    db_user = db.get_user(user.id)
    if not db_user:
        await update.message.reply_text(
            "⚠️ You must register first before submitting permission requests."
        )
        return ConversationHandler.END

    if db_user.get("status") == "banned":
        await update.message.reply_text(
            "❌ Access Denied: You are BANNED from the system."
        )
        return ConversationHandler.END

    # Build inline type-selection keyboard
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🏖️ Short Leave", callback_data="ptype_short_leave"),
             InlineKeyboardButton("🕒 Late Arrival", callback_data="ptype_late_arrival")],
            [InlineKeyboardButton("🚶 Early Departure", callback_data="ptype_early_departure")],
            [InlineKeyboardButton("❌ Cancel", callback_data="ptype_cancel")],
        ]
    )

    await update.message.reply_text(
        "📋 *Permission Request*\n\n"
        "Please select the type of permission you need:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return SELECT_TYPE


# ------------------------------------------------------------------
# STEP 1 – Select type (callback from inline keyboard)
# ------------------------------------------------------------------
async def handle_type_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """User picks a permission type from the inline keyboard."""
    query = update.callback_query
    await query.answer()

    data = query.data  # e.g. "ptype_short_leave"

    if data == "ptype_cancel":
        await query.edit_message_text("❌ Permission request cancelled.")
        return ConversationHandler.END

    request_type = data.replace("ptype_", "")
    label = REQUEST_TYPE_LABELS.get(request_type, "Other")

    context.user_data["perm_type"] = request_type
    context.user_data["perm_type_label"] = label

    await query.edit_message_text(
        f"📋 *Permission Request — {label}*\n\n"
        "⏰ What time does your permission *start*?\n"
        "_(Enter in HH:MM format, e.g. `14:30`)_",
        parse_mode="Markdown",
    )
    return ENTER_START_TIME


# ------------------------------------------------------------------
# STEP 2 – Start time
# ------------------------------------------------------------------
async def handle_start_time(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Collect start time from free-text input."""
    raw = update.message.text.strip()
    parsed = _parse_time(raw)

    if not parsed:
        await update.message.reply_text(
            "⚠️ Invalid time format. Please enter the start time as `HH:MM` "
            "(e.g. `14:30`).",
            parse_mode="Markdown",
        )
        return ENTER_START_TIME

    context.user_data["perm_start"] = parsed
    await update.message.reply_text(
        f"✅ Start time: `{parsed}`\n\n"
        "⏰ What time does your permission *end*?\n"
        "_(Enter in HH:MM format, e.g. `16:00`)_",
        parse_mode="Markdown",
    )
    return ENTER_END_TIME


# ------------------------------------------------------------------
# STEP 3 – End time
# ------------------------------------------------------------------
async def handle_end_time(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Collect end time; validate it is after start time."""
    raw = update.message.text.strip()
    parsed = _parse_time(raw)

    if not parsed:
        await update.message.reply_text(
            "⚠️ Invalid time format. Please enter the end time as `HH:MM`.",
            parse_mode="Markdown",
        )
        return ENTER_END_TIME

    start = context.user_data.get("perm_start", "00:00:00")
    start_sec = time_to_seconds(start)
    end_sec = time_to_seconds(parsed)

    # Handle overnight shifts: allow end < start
    if end_sec == start_sec:
        await update.message.reply_text(
            "⚠️ End time cannot be the same as start time. Please try again.",
            parse_mode="Markdown",
        )
        return ENTER_END_TIME

    # Compute duration
    if end_sec > start_sec:
        duration_sec = end_sec - start_sec
    else:
        # Overnight wrap
        duration_sec = (86400 - start_sec) + end_sec

    context.user_data["perm_end"] = parsed
    context.user_data["perm_duration"] = duration_sec

    await update.message.reply_text(
        f"✅ End time: `{parsed}` _(Duration: {format_seconds(duration_sec)})_\n\n"
        "📝 Please briefly describe the *reason* for your permission request:",
        parse_mode="Markdown",
    )
    return ENTER_REASON


# ------------------------------------------------------------------
# STEP 4 – Reason
# ------------------------------------------------------------------
async def handle_reason(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Collect reason text; enforce minimum length."""
    reason = update.message.text.strip()

    if len(reason) < 5:
        await update.message.reply_text(
            "⚠️ Please provide a more descriptive reason (at least 5 characters)."
        )
        return ENTER_REASON

    context.user_data["perm_reason"] = reason

    # Build confirmation summary
    label = context.user_data.get("perm_type_label", "")
    start = context.user_data.get("perm_start", "")
    end = context.user_data.get("perm_end", "")
    duration = context.user_data.get("perm_duration", 0)
    today = get_current_date_str()

    confirm_kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Submit Request", callback_data="perm_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="perm_cancel"),
            ]
        ]
    )

    await update.message.reply_text(
        f"📋 *Permission Request Summary*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Type:* {label}\n"
        f"📅 *Date:* `{today}`\n"
        f"⏰ *Time:* `{start}` → `{end}`\n"
        f"⏱️ *Duration:* `{format_seconds(duration)}`\n"
        f"📝 *Reason:* {reason}\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"Do you want to submit this request?",
        parse_mode="Markdown",
        reply_markup=confirm_kb,
    )
    return CONFIRM


# ------------------------------------------------------------------
# STEP 5 – Confirmation
# ------------------------------------------------------------------
async def handle_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Final step: save to DB and notify admins."""
    query = update.callback_query
    await query.answer()

    if query.data == "perm_cancel":
        await query.edit_message_text("❌ Permission request cancelled.")
        context.user_data.clear()
        return ConversationHandler.END

    user = update.effective_user
    db = context.bot_data["db"]
    db_user = db.get_user(user.id)

    if not db_user:
        await query.edit_message_text("⚠️ Registration error. Please try again.")
        return ConversationHandler.END

    today = get_current_date_str()
    request_type = context.user_data.get("perm_type", "other")
    label = context.user_data.get("perm_type_label", "Other")
    start = context.user_data.get("perm_start", "")
    end = context.user_data.get("perm_end", "")
    duration_sec = context.user_data.get("perm_duration", 0)
    reason = context.user_data.get("perm_reason", "")

    try:
        request_id = db.create_permission_request(
            telegram_id=user.id,
            username=user.username,
            name=db_user["full_name"],
            date=today,
            request_type=request_type,
            start_time=start,
            end_time=end,
            duration_seconds=duration_sec,
            reason=reason,
        )
    except Exception as e:
        print(f"❌ Error creating permission request: {e}")
        await query.edit_message_text(
            "⚠️ A database error occurred. Please try again later."
        )
        return ConversationHandler.END

    # Confirm to employee
    await query.edit_message_text(
        f"📩 *Permission Request Submitted!*\n\n"
        f"📌 Type: {label}\n"
        f"📅 Date: `{today}`\n"
        f"⏰ Time: `{start}` → `{end}`\n"
        f"📝 Reason: {reason}\n\n"
        f"Your request has been sent to the administrator for review.\n"
        f"_You will be notified once a decision is made._",
        parse_mode="Markdown",
    )

    # Notify each admin with Approve / Reject inline buttons
    admin_msg = (
        f"📩 *New Permission Request* (ID: #{request_id})\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Employee: *{db_user['full_name']}* (@{user.username or 'NoUsername'})\n"
        f"📌 Type: {label}\n"
        f"📅 Date: `{today}`\n"
        f"⏰ Time: `{start}` → `{end}`\n"
        f"⏱️ Duration: `{format_seconds(duration_sec)}`\n"
        f"📝 Reason: {reason}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Please take action below:"
    )

    approval_kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Approve", callback_data=f"pr_approve_{request_id}"
                ),
                InlineKeyboardButton(
                    "❌ Reject", callback_data=f"pr_reject_{request_id}"
                ),
            ]
        ]
    )

    for admin_id in config.ADMIN_TELEGRAM_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_msg,
                parse_mode="Markdown",
                reply_markup=approval_kb,
            )
        except Exception as notify_err:
            print(f"⚠️ Could not notify admin {admin_id}: {notify_err}")

    context.user_data.clear()
    return ConversationHandler.END


# ------------------------------------------------------------------
# Cancel fallback (user sends /cancel mid-flow)
# ------------------------------------------------------------------
async def cancel_permission(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Allow the user to abort the flow at any stage by sending /cancel."""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Permission request cancelled. You can start again anytime."
    )
    return ConversationHandler.END


# ------------------------------------------------------------------
# Admin approval callback (pr_approve_{id} / pr_reject_{id})
# ------------------------------------------------------------------
async def handle_approval_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handles admin Approve / Reject inline button presses.
    Updates DB, notifies the employee, edits the admin message.
    """
    query = update.callback_query
    await query.answer()

    admin_user = update.effective_user
    db = context.bot_data["db"]

    data = query.data  # e.g. "pr_approve_42" or "pr_reject_42"
    if data.startswith("pr_approve_"):
        action = "approved"
        request_id = int(data.replace("pr_approve_", ""))
    elif data.startswith("pr_reject_"):
        action = "rejected"
        request_id = int(data.replace("pr_reject_", ""))
    else:
        return

    # Fetch the request
    req = db.get_permission_request(request_id)
    if not req:
        await query.edit_message_text(
            f"⚠️ Permission request #{request_id} not found."
        )
        return

    if req["status"] != "pending":
        # Already decided — show current state
        await query.edit_message_text(
            f"ℹ️ Permission request #{request_id} was already "
            f"*{req['status']}*.",
            parse_mode="Markdown",
        )
        return

    # Update status in DB
    approver_name = (
        admin_user.full_name
        if admin_user and admin_user.full_name
        else f"Admin ({admin_user.id if admin_user else 'unknown'})"
    )
    db.update_permission_request_status(
        request_id=request_id,
        status=action,
        approver_id=admin_user.id if admin_user else None,
        approver_name=approver_name,
    )

    # If approved, check if we should reverse any half-day fine
    if action == "approved":
        _maybe_reverse_fine(db, req)

    # Edit the admin's message to show outcome
    label = REQUEST_TYPE_LABELS.get(req["request_type"], "Request")
    action_emoji = "✅" if action == "approved" else "❌"
    decided_word = "APPROVED" if action == "approved" else "REJECTED"

    await query.edit_message_text(
        f"📩 Permission Request #{request_id}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Employee: *{req['name']}* (@{req['username'] or 'NoUsername'})\n"
        f"📌 Type: {label}\n"
        f"📅 Date: `{req['date']}`\n"
        f"⏰ Time: `{req['start_time']}` → `{req['end_time']}`\n"
        f"📝 Reason: {req['reason']}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"{action_emoji} *{decided_word}* by {approver_name}",
        parse_mode="Markdown",
    )

    # Notify the employee
    decided_at_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    action_emoji = "✅" if action == "approved" else "❌"
    decided_word = "APPROVED" if action == "approved" else "REJECTED"

    employee_msg = (
        f"{action_emoji} *Permission Request {decided_word}*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Type: {label}\n"
        f"📅 Request Date: `{req['date']}`\n"
        f"⏰ Time Range: `{req['start_time']}` → `{req['end_time']}`\n"
        f"📝 Reason: {req['reason']}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"{action_emoji} *Status: {decided_word}*\n"
        f"👤 {'Approved' if action == 'approved' else 'Reviewed'} by: {approver_name}\n"
        f"🕐 Decided at: `{decided_at_str[:16]}`\n\n"
        + (
            "_Your approved hours have been credited to your attendance record._"
            if action == "approved"
            else "_If you need further assistance, please contact your supervisor._"
        )
    )

    notification_success = False
    try:
        await context.bot.send_message(
            chat_id=req["telegram_id"],
            text=employee_msg,
            parse_mode="Markdown",
        )
        notification_success = True
    except Exception as e:
        print(f"⚠️ Could not notify employee {req['telegram_id']}: {e}")

    db.update_permission_notification_status(request_id, "sent" if notification_success else "failed")


def _maybe_reverse_fine(db, req: dict) -> None:
    """
    When a permission request is approved, unconditionally:
      1. Remove any outstanding fine for that date from the fines table.
      2. Mark all attendance sessions for that date as Full Day (is_half_day = 0)
         and clear any session-specific late login / break fines.

    Rule: Approved permission → Full Day + fine removed, always.
    """
    try:
        telegram_id = req["telegram_id"]
        date = req["date"]

        # Remove any fine on record for this date
        db.delete_fine(telegram_id, date)

        # Flip all sessions on that date to Full Day and clear fine fields
        conn = db.connect()
        conn.execute(
            """
            UPDATE attendance_sessions 
            SET is_half_day = 0, fine_applied = 0, fine_amount = 0.0, fine_reason = ''
            WHERE telegram_id = ? AND date = ?
            """,
            (telegram_id, date)
        )
        conn.commit()

        print(f"✅ Permission approved: marked Full Day + removed fine for {telegram_id} on {date}")
    except Exception as e:
        print(f"⚠️ _maybe_reverse_fine error: {e}")



# ------------------------------------------------------------------
# Build the ConversationHandler (call this in main.py)
# ------------------------------------------------------------------
def build_permission_conversation_handler() -> ConversationHandler:
    """
    Constructs and returns the ConversationHandler for the permission
    request flow.  Register this in main.py BEFORE the generic
    MessageHandler so it takes priority.
    """
    return ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.TEXT & filters.Regex(r"^Permission Request 📋$"),
                start_permission_request,
            )
        ],
        states={
            SELECT_TYPE: [
                CallbackQueryHandler(handle_type_selection, pattern=r"^ptype_")
            ],
            ENTER_START_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_start_time)
            ],
            ENTER_END_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_end_time)
            ],
            ENTER_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reason)
            ],
            CONFIRM: [
                CallbackQueryHandler(handle_confirmation, pattern=r"^perm_(confirm|cancel)$")
            ],
        },
        fallbacks=[
            MessageHandler(filters.COMMAND & filters.Regex(r"^/cancel"), cancel_permission)
        ],
        # Per-user state; each user gets independent conversation context
        per_user=True,
        per_chat=True,
        name="permission_request_flow",
        persistent=False,
    )
